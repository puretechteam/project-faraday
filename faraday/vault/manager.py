"""
Vault manager for file I/O and vault operations.
Implements safe failure rules: abort immediately on decryption/auth failure.

Data-safety rules this module enforces:

* Saves are atomic (temp file + fsync + replace) and use the salt and KDF
  parameters captured at unlock, never values re-read from disk.
* Before every save the bytes currently on disk are kept as a rolling
  encrypted snapshot in ``{vault}.backups/``.
* If the file on disk changed since this manager last read or wrote it, the
  save is refused rather than overwriting someone else's changes.
* An exclusive ``{vault}.lock`` stops two processes from writing one vault.
* A failed save rolls the in-memory entries back to what is on disk.
* Fields and entry types this build does not understand are preserved.
"""

import hashlib
import hmac
import os
import threading
import time
from typing import Callable, Dict, List, Optional

from cryptography.exceptions import InvalidTag

from faraday import access_log

from .atomic import atomic_write_bytes
from .backups import BackupStore
from .crypto import VaultCrypto, ARGON2_TIME_COST, ARGON2_MEMORY_COST, ARGON2_PARALLELISM
from .errors import (
    AttachmentIntegrityError,
    AttachmentsPresentError,
    VaultChangedOnDiskError,
    VaultLockedError,
    VaultReadOnlyError,
)
from .fileformat import build_vault_bytes, parse_vault_bytes
from .filelock import VaultFileLock
from .storage import serialize_vault_data, deserialize_vault_data
from .security import set_vault_permissions, verify_vault_permissions
from ..models.entry import BaseEntry
from ..models.opaque_entry import OpaqueEntry
from ..models.crypto_entry import CryptoEntry
from ..models.credential_entry import CredentialEntry
from ..models.secure_note_entry import SecureNoteEntry
from ..models.card_entry import CardEntry
from ..models.identity_entry import IdentityEntry
from ..models.two_factor_entry import TwoFactorEntry
from ..models.wifi_entry import WifiEntry
from ..models.document_entry import DocumentEntry
from ..models.api_key_entry import ApiKeyEntry
from ..models.emergency_contact_entry import EmergencyContactEntry
from .attachments import AttachmentStorage


def _safe_log(event, *, vault_path=None, reason=None, source="gui"):
    """Record an access-log event, never raising regardless of logging failure."""
    try:
        access_log.record(event, vault_path=vault_path, reason=reason, source=source)
    except Exception:
        pass


# Entry type registry for deserialization
ENTRY_TYPE_REGISTRY = {
    "crypto": CryptoEntry,
    "credential": CredentialEntry,
    "secure_note": SecureNoteEntry,
    "card": CardEntry,
    "identity": IdentityEntry,
    "two_factor": TwoFactorEntry,
    "wifi": WifiEntry,
    "document": DocumentEntry,
    "api_key": ApiKeyEntry,
    "emergency_contact": EmergencyContactEntry,
}

DEFAULT_KDF_PARAMS = {
    "time_cost": ARGON2_TIME_COST,
    "memory_cost": ARGON2_MEMORY_COST,
    "parallelism": ARGON2_PARALLELISM,
}

_DEFAULT = object()


def _fingerprint(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class VaultManager:
    """Manages vault file operations and entry storage."""

    AUTO_LOCK_TIMEOUT = 300  # 5 minutes

    def __init__(
        self,
        vault_path: str,
        password: bytes,
        *,
        auto_lock_seconds=_DEFAULT,
        read_only: bool = False,
        backups: bool = True,
        backup_keep_recent: int = 10,
        backup_keep_daily: int = 14,
    ):
        """Initialize vault manager.

        ``auto_lock_seconds`` defaults to AUTO_LOCK_TIMEOUT; pass None to turn
        the background auto-lock thread off (the Qt GUI tracks idle itself).
        ``read_only`` skips the file lock and refuses every save.
        """
        self.vault_path = os.path.abspath(vault_path)
        self.crypto = VaultCrypto(password)
        self.master_key: Optional[bytes] = None
        self.is_locked = True
        self.read_only = read_only
        self.auto_lock_seconds = self.AUTO_LOCK_TIMEOUT if auto_lock_seconds is _DEFAULT else auto_lock_seconds
        self.last_activity = time.time()
        self._lock = threading.RLock()
        self._entries: Dict[str, BaseEntry] = {}
        self._auto_lock_thread: Optional[threading.Thread] = None
        self._stop_auto_lock = threading.Event()
        self._attachment_storage: Optional[AttachmentStorage] = None
        self._salt: Optional[bytes] = None
        self._kdf_params: Optional[Dict[str, int]] = None
        self._fingerprint: Optional[str] = None
        self._file_lock = VaultFileLock(self.vault_path)
        self._lock_listeners: List[Callable[[str], None]] = []
        self.backups = (
            BackupStore(self.vault_path, keep_recent=backup_keep_recent, keep_daily=backup_keep_daily)
            if backups else None
        )

    # ------------------------------------------------------------------ lifecycle

    def create_vault(self, kdf_params: Optional[Dict[str, int]] = None):
        """Create a new vault file. Raises FileExistsError if vault file already exists."""
        if os.path.exists(self.vault_path):
            raise FileExistsError(f"Vault file already exists: {self.vault_path}")
        if self.read_only:
            raise VaultReadOnlyError("Cannot create a vault in read-only mode")
        params = dict(DEFAULT_KDF_PARAMS)
        params.update(kdf_params or {})
        self._file_lock.acquire()
        try:
            salt = self.crypto.generate_salt()
            master_key = self.crypto.derive_master_key(salt, **params)
            plaintext = serialize_vault_data({"entries": []})
            nonce, ciphertext = self.crypto.encrypt_aes_gcm(plaintext, master_key)
            data = build_vault_bytes(salt, params, nonce, ciphertext)
            atomic_write_bytes(self.vault_path, data, overwrite=False)
        except BaseException:
            self._file_lock.release()
            raise
        self._apply_permissions()
        with self._lock:
            self.master_key = master_key
            self._salt = salt
            self._kdf_params = params
            self._fingerprint = _fingerprint(data)
            self._entries = {}
            self._init_attachment_storage()
            self.is_locked = False
        _safe_log("vault_created", vault_path=self.vault_path, source="core")
        self._update_activity()
        self._start_auto_lock()

    def unlock_vault(self) -> bool:
        """Unlock vault by reading and decrypting vault file.

        Raises FileNotFoundError, ValueError (damaged file), InvalidTag (wrong
        password or tampered file) or VaultInUseError (open elsewhere).
        """
        if not os.path.exists(self.vault_path):
            _safe_log("unlock_failed", vault_path=self.vault_path, reason="vault_missing", source="core")
            raise FileNotFoundError(f"Vault file not found: {self.vault_path}")
        is_secure, warning = verify_vault_permissions(self.vault_path)
        if not is_secure and warning:
            import warnings
            warnings.warn(f"Security warning: {warning}", UserWarning)
        if not self.read_only:
            self._file_lock.acquire()
        try:
            with open(self.vault_path, "rb") as f:
                data = f.read()
            try:
                vf = parse_vault_bytes(data)
            except ValueError:
                _safe_log("unlock_failed", vault_path=self.vault_path, reason="vault_damaged", source="core")
                raise
            params = vf.kdf_params
            master_key = self.crypto.derive_master_key(vf.salt, **params)
            try:
                plaintext = self.crypto.decrypt_aes_gcm(vf.nonce, vf.ciphertext, master_key)
            except InvalidTag:
                _safe_log("unlock_failed", vault_path=self.vault_path, reason="bad_password_or_corrupt", source="core")
                raise InvalidTag("Authentication failed: vault may be corrupted or password incorrect")
            vault_data = deserialize_vault_data(plaintext)
            entries: Dict[str, BaseEntry] = {}
            for entry_data in vault_data.get("entries", []):
                entry = self._entry_from_dict(entry_data)
                entries[entry.entry_id] = entry
        except BaseException:
            self._file_lock.release()
            raise
        with self._lock:
            self.master_key = master_key
            self._salt = vf.salt
            self._kdf_params = params
            self._fingerprint = _fingerprint(data)
            self._entries = entries
            self._init_attachment_storage()
            self.is_locked = False
        _safe_log("unlock_succeeded", vault_path=self.vault_path, source="core")
        self._update_activity()
        self._start_auto_lock()
        return True

    def verify_password(self, candidate: bytes) -> bool:
        """Check a candidate master password against the currently unlocked vault.

        Derives a key from ``candidate`` with the salt and Argon2id settings
        captured at unlock and compares it in constant time against the
        in-memory master key. Nothing is read from disk and no state changes.
        Any failure returns False instead of raising.
        """
        try:
            with self._lock:
                if self.is_locked or self.master_key is None or self._salt is None:
                    return False
                salt, params, master_key = self._salt, dict(self._kdf_params), bytes(self.master_key)
            if isinstance(candidate, str):
                candidate = candidate.encode("utf-8")
            if not isinstance(candidate, (bytes, bytearray)) or len(candidate) == 0:
                return False
            probe = VaultCrypto(bytes(candidate))
            try:
                derived = probe.derive_master_key(salt, **params)
                return hmac.compare_digest(bytes(derived), master_key)
            finally:
                try:
                    probe.clear_memory(passes=3)
                except Exception:
                    pass
        except Exception:
            return False

    @property
    def kdf_params(self) -> Optional[Dict[str, int]]:
        """Argon2id settings of the unlocked vault (None while locked)."""
        return dict(self._kdf_params) if self._kdf_params else None

    def add_lock_listener(self, callback: Callable[[str], None]) -> None:
        """Call ``callback(reason)`` after the vault locks (from whichever thread locked it)."""
        self._lock_listeners.append(callback)

    def lock_vault(self, reason: str = "manual"):
        """Lock vault and clear sensitive data from memory."""
        self._stop_auto_lock.set()
        # Join outside the mutex: the worker takes it before locking.
        worker = self._auto_lock_thread
        if worker and worker is not threading.current_thread():
            worker.join(timeout=1.0)
        with self._lock:
            was_unlocked = not self.is_locked
            # master_key goes first so no save can run against cleared entries.
            if self.master_key:
                key_array = bytearray(self.master_key)
                for _ in range(3):
                    for i in range(len(key_array)):
                        key_array[i] = 0
                self.master_key = None
            self.is_locked = True
            self.crypto.clear_memory(passes=3)
            self._entries.clear()
            self._attachment_storage = None
            self._salt = None
            self._kdf_params = None
            self._fingerprint = None
            self._file_lock.release()
        _safe_log("vault_locked", vault_path=self.vault_path, reason=reason, source="core")
        if was_unlocked:
            for callback in list(self._lock_listeners):
                try:
                    callback(reason)
                except Exception:
                    pass

    # ------------------------------------------------------------------ saving

    def _require_unlocked(self):
        if self.is_locked or self.master_key is None:
            raise VaultLockedError("Vault is locked")

    def _serialize_entries(self) -> bytes:
        return serialize_vault_data({"entries": [self._entry_to_dict(e) for e in self._entries.values()]})

    def _read_disk(self) -> bytes:
        try:
            with open(self.vault_path, "rb") as f:
                return f.read()
        except FileNotFoundError:
            raise VaultChangedOnDiskError("The vault file is missing on disk; refusing to recreate it")

    def _check_disk_unchanged(self) -> bytes:
        current = self._read_disk()
        if _fingerprint(current) != self._fingerprint:
            raise VaultChangedOnDiskError(
                "The vault file was changed by another program since it was opened; refusing to overwrite it"
            )
        return current

    def _write_vault(self, plaintext: bytes, salt: bytes, params: Dict[str, int], master_key: bytes) -> None:
        current = self._check_disk_unchanged()
        if self.backups is not None:
            self.backups.snapshot_bytes(current)
        nonce, ciphertext = self.crypto.encrypt_aes_gcm(plaintext, master_key)
        data = build_vault_bytes(salt, params, nonce, ciphertext)
        atomic_write_bytes(self.vault_path, data)
        self._fingerprint = _fingerprint(data)
        self._apply_permissions()

    def save_vault(self):
        """Save current vault state to file. Raises VaultLockedError if vault is locked."""
        with self._lock:
            self._require_unlocked()
            if self.read_only:
                raise VaultReadOnlyError("Vault is open read-only")
            self._write_vault(self._serialize_entries(), self._salt, self._kdf_params, self.master_key)
        self._update_activity()

    def _apply_permissions(self):
        try:
            set_vault_permissions(self.vault_path)
        except Exception:
            pass  # the data is already safely on disk

    def _mutate(self, change: Callable[[], None]) -> None:
        """Apply ``change`` to the entries, save, and roll back if the save fails."""
        with self._lock:
            self._require_unlocked()
            before = dict(self._entries)
            change()
            try:
                self.save_vault()
            except BaseException:
                self._entries = before
                raise

    # ------------------------------------------------------------------ entries

    def add_entry(self, entry: BaseEntry):
        """Add an entry, or replace the entry with the same id.

        Replacing keeps the original ``created`` time and any fields this
        build does not know about. Prefer update_entry for edits.
        """
        if isinstance(entry, OpaqueEntry):
            raise ValueError("Unreadable entries cannot be saved from this version")

        def change():
            existing = self._entries.get(entry.entry_id)
            if existing is not None:
                self._carry_over(existing, entry)
            entry.update_modified()
            self._entries[entry.entry_id] = entry

        self._mutate(change)
        self._update_activity()

    def update_entry(self, entry: BaseEntry):
        """Replace an existing entry, keeping its id, created time and unknown fields."""
        def change():
            existing = self._entries.get(entry.entry_id)
            if existing is None:
                raise KeyError(f"Entry not found: {entry.entry_id}")
            if isinstance(existing, OpaqueEntry) or isinstance(entry, OpaqueEntry):
                raise ValueError("Unreadable entries cannot be edited from this version")
            if existing.get_entry_type() != entry.get_entry_type():
                raise ValueError("An entry cannot change its type")
            self._carry_over(existing, entry)
            entry.update_modified()
            self._entries[entry.entry_id] = entry

        self._mutate(change)
        self._update_activity()

    @staticmethod
    def _carry_over(existing: BaseEntry, entry: BaseEntry) -> None:
        entry.created = existing.created
        extra = dict(getattr(existing, "_extra", {}) or {})
        extra.update(getattr(entry, "_extra", {}) or {})
        entry._extra = extra

    def get_entry(self, entry_id: str) -> Optional[BaseEntry]:
        """Get entry by ID. Raises VaultLockedError if vault is locked."""
        with self._lock:
            self._require_unlocked()
            entry = self._entries.get(entry_id)
        self._update_activity()
        return entry

    def list_entries(self, entry_type: Optional[str] = None, include_opaque: bool = False) -> List[BaseEntry]:
        """List entries, optionally filtered by type.

        Unreadable entries are left out unless ``include_opaque`` is set, so
        callers that expect a concrete model class never receive one.
        """
        with self._lock:
            self._require_unlocked()
            entries = list(self._entries.values())
        self._update_activity()
        if not include_opaque:
            entries = [e for e in entries if not isinstance(e, OpaqueEntry)]
        if entry_type:
            entries = [e for e in entries if e.get_entry_type() == entry_type]
        return entries

    def delete_entry(self, entry_id: str) -> bool:
        """Delete entry by ID. Returns True if deleted, False if not found.

        A document's attachment is wiped only after the vault has been saved
        without the entry, so a failed save never leaves a dangling reference.
        """
        with self._lock:
            self._require_unlocked()
            entry = self._entries.get(entry_id)
            if entry is None:
                return False
            self._mutate(lambda: self._entries.pop(entry_id))
            storage = self._attachment_storage
        if isinstance(entry, DocumentEntry) and storage:
            try:
                storage.delete_file(entry.file_reference)
            except Exception:
                pass  # an orphaned encrypted file is harmless
        self._update_activity()
        return True

    def search(self, query: str, entry_type: Optional[str] = None) -> List[BaseEntry]:
        """Entries whose non-secret fields contain ``query`` (case-insensitive)."""
        from ..models.schema import entry_matches
        return [e for e in self.list_entries(entry_type, include_opaque=True) if entry_matches(e, query)]

    # ------------------------------------------------------------------ documents

    def add_document(self, source_path: str, category: str = "General", site_note: str = "",
                     mime_type: Optional[str] = None) -> DocumentEntry:
        """Encrypt ``source_path`` into the attachment store and add a document entry for it."""
        import mimetypes
        with self._lock:
            self._require_unlocked()
            if self.read_only:
                raise VaultReadOnlyError("Vault is open read-only")
            storage = self.get_attachment_storage()
        with open(source_path, "rb") as fh:
            data = fh.read()
        file_uuid, file_hash = storage.store_file(data)
        try:
            entry = DocumentEntry(
                filename=os.path.basename(source_path),
                mime_type=mime_type or mimetypes.guess_type(source_path)[0] or "application/octet-stream",
                file_reference=file_uuid,
                file_size=len(data),
                file_hash=file_hash,
                category=category or "General",
                site_note=site_note,
            )
            self.add_entry(entry)
        except BaseException:
            try:
                storage.delete_file(file_uuid)
            except Exception:
                pass
            raise
        return entry

    def read_document(self, entry_id: str) -> bytes:
        """Decrypt a document attachment and check it against its recorded hash."""
        with self._lock:
            self._require_unlocked()
            entry = self._entries.get(entry_id)
            storage = self.get_attachment_storage()
        if not isinstance(entry, DocumentEntry):
            raise KeyError(f"Document not found: {entry_id}")
        data = storage.retrieve_file(entry.file_reference)
        if hashlib.sha256(data).hexdigest() != entry.file_hash:
            raise AttachmentIntegrityError(f"Attachment for '{entry.filename}' failed its integrity check")
        self._update_activity()
        return data

    def export_document(self, entry_id: str, dest_path: str) -> None:
        """Write a decrypted, hash-verified copy of a document to ``dest_path``."""
        atomic_write_bytes(dest_path, self.read_document(entry_id))

    # ------------------------------------------------------------------ import / export

    def import_entries(self, entries: List[BaseEntry], attachments: Optional[Dict[str, bytes]] = None) -> int:
        """Add many entries with a single save. Returns how many were added.

        Entries whose id already exists get a fresh id. Document entries take
        their file from ``attachments`` (keyed by the entry's original
        ``file_reference``); each file is re-encrypted under this vault's key.
        If anything fails, nothing is added and stored files are removed.
        """
        import uuid
        attachments = attachments or {}
        with self._lock:
            self._require_unlocked()
            if self.read_only:
                raise VaultReadOnlyError("Vault is open read-only")
            storage = self.get_attachment_storage()
            stored: List[str] = []
            try:
                prepared = []
                for entry in entries:
                    if entry.entry_id in self._entries or any(e.entry_id == entry.entry_id for e in prepared):
                        if isinstance(entry, OpaqueEntry):
                            entry.raw["entry_id"] = str(uuid.uuid4())
                            entry.entry_id = entry.raw["entry_id"]
                        else:
                            entry.entry_id = str(uuid.uuid4())
                    if isinstance(entry, DocumentEntry):
                        data = attachments.get(entry.file_reference)
                        if data is None:
                            raise ValueError(f"The file for document '{entry.filename}' is missing from the import")
                        if hashlib.sha256(data).hexdigest() != entry.file_hash:
                            raise AttachmentIntegrityError(f"The file for '{entry.filename}' failed its integrity check")
                        new_ref, _ = storage.store_file(data)
                        stored.append(new_ref)
                        entry.file_reference = new_ref
                    prepared.append(entry)

                def change():
                    for entry in prepared:
                        self._entries[entry.entry_id] = entry
                self._mutate(change)
            except BaseException:
                for ref in stored:
                    try:
                        storage.delete_file(ref)
                    except Exception:
                        pass
                raise
        self._update_activity()
        return len(prepared)

    def export_records(self) -> tuple:
        """All entries as stored dictionaries plus every document's verified file bytes."""
        with self._lock:
            self._require_unlocked()
            entries = list(self._entries.values())
        records = [self._entry_to_dict(e) for e in entries]
        files = {e.file_reference: self.read_document(e.entry_id) for e in entries if isinstance(e, DocumentEntry)}
        return records, files

    # ------------------------------------------------------------------ maintenance

    def has_attachments(self) -> bool:
        with self._lock:
            if any(isinstance(e, DocumentEntry) for e in self._entries.values()):
                return True
        directory = f"{self.vault_path}.attachments"
        return os.path.isdir(directory) and any(n.endswith(".enc") for n in os.listdir(directory))

    def rekey(self, new_password: Optional[bytes] = None, kdf_params: Optional[Dict[str, int]] = None) -> None:
        """Re-encrypt the vault with a fresh salt, optionally a new password and KDF settings.

        Refuses when document attachments exist: their keys derive from the
        master key, and re-encrypting them is not implemented yet.
        """
        with self._lock:
            self._require_unlocked()
            if self.read_only:
                raise VaultReadOnlyError("Vault is open read-only")
            if self.has_attachments():
                raise AttachmentsPresentError(
                    "This vault has document attachments; changing its key would make them unreadable"
                )
            params = dict(self._kdf_params)
            params.update(kdf_params or {})
            crypto = VaultCrypto(new_password) if new_password else self.crypto
            salt = crypto.generate_salt()
            master_key = crypto.derive_master_key(salt, **params)
            self._write_vault(self._serialize_entries(), salt, params, master_key)
            if crypto is not self.crypto:
                self.crypto.clear_memory(passes=3)
                self.crypto = crypto
            self.master_key = master_key
            self._salt = salt
            self._kdf_params = params
            self._init_attachment_storage()
        self._update_activity()

    def restore_backup(self, backup_path: str, password: bytes) -> int:
        """Replace the vault file with a verified snapshot. Returns the snapshot's entry count.

        The snapshot is decrypted with ``password`` first; nothing changes if
        that fails. The current vault is snapshotted before being replaced,
        and the manager is locked afterwards so the caller unlocks afresh.
        """
        with open(backup_path, "rb") as fh:
            data = fh.read()
        vf = parse_vault_bytes(data)
        probe = VaultCrypto(password)
        try:
            key = probe.derive_master_key(vf.salt, **vf.kdf_params)
            plaintext = probe.decrypt_aes_gcm(vf.nonce, vf.ciphertext, key)
        finally:
            probe.clear_memory(passes=3)
        count = len(deserialize_vault_data(plaintext).get("entries", []))
        with self._lock:
            self._require_unlocked()
            if self.read_only:
                raise VaultReadOnlyError("Vault is open read-only")
            current = self._check_disk_unchanged()
            if self.backups is not None:
                self.backups.snapshot_bytes(current)
            atomic_write_bytes(self.vault_path, data)
            self._fingerprint = _fingerprint(data)
        self.lock_vault(reason="restored_backup")
        return count

    def export_full_backup(self, dest_dir: str) -> str:
        """Copy the vault and its attachments into a new, hash-verified folder under ``dest_dir``."""
        with self._lock:
            self._require_unlocked()
            current = self._check_disk_unchanged()
        store = self.backups or BackupStore(self.vault_path)
        return store.export_full(dest_dir, vault_bytes=current)

    # ------------------------------------------------------------------ (de)serialization

    def _entry_from_dict(self, data: dict) -> BaseEntry:
        """Create an entry from its stored dictionary, never losing data.

        Unknown types and malformed known types become OpaqueEntry; fields
        the model does not know are kept in ``entry._extra``.
        """
        if not isinstance(data, dict):
            return OpaqueEntry({"type": "unknown", "value": data}, problem="not a dictionary")
        entry_class = ENTRY_TYPE_REGISTRY.get(data.get("type"))
        if entry_class is None:
            return OpaqueEntry(data, problem="unknown type")
        try:
            entry = entry_class.from_dict(data)
            known = entry.to_dict()
        except Exception as exc:
            return OpaqueEntry(data, problem=f"unreadable fields ({exc.__class__.__name__})")
        entry._extra = {k: v for k, v in data.items() if k not in known}
        return entry

    @staticmethod
    def _entry_to_dict(entry: BaseEntry) -> dict:
        if isinstance(entry, OpaqueEntry):
            return entry.to_dict()
        data = dict(getattr(entry, "_extra", None) or {})
        data.update(entry.to_dict())
        return data

    # ------------------------------------------------------------------ attachments

    def _init_attachment_storage(self):
        """Initialize attachment storage."""
        if self.master_key is None:
            return
        attachments_dir = f"{self.vault_path}.attachments"
        self._attachment_storage = AttachmentStorage(attachments_dir, self.master_key)

    def get_attachment_storage(self) -> Optional[AttachmentStorage]:
        """Get attachment storage instance. Returns None if vault is locked."""
        if self.is_locked or self.master_key is None:
            return None
        if self._attachment_storage is None:
            self._init_attachment_storage()
        return self._attachment_storage

    # ------------------------------------------------------------------ auto-lock

    def _update_activity(self):
        """Update last activity timestamp."""
        self.last_activity = time.time()

    def _start_auto_lock(self):
        """Start the auto-lock thread unless auto-lock is turned off."""
        if not self.auto_lock_seconds:
            return
        self._stop_auto_lock.clear()
        if self._auto_lock_thread is None or not self._auto_lock_thread.is_alive():
            self._auto_lock_thread = threading.Thread(target=self._auto_lock_worker, daemon=True)
            self._auto_lock_thread.start()

    def _auto_lock_worker(self):
        """Auto-lock worker thread."""
        poll = min(10.0, max(0.05, self.auto_lock_seconds / 4))
        while not self._stop_auto_lock.wait(poll):
            if self.is_locked:
                break
            if time.time() - self.last_activity >= self.auto_lock_seconds:
                with self._lock:
                    if self.is_locked:
                        break
                    if time.time() - self.last_activity < self.auto_lock_seconds:
                        continue
                    self.lock_vault(reason="auto_timeout")
                break
