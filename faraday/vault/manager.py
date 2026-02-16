"""
Vault manager for file I/O and vault operations.
Implements safe failure rules: abort immediately on decryption/auth failure.
"""

import os
import time
from typing import Dict, List, Optional, Any
from cryptography.exceptions import InvalidTag
import threading

from .crypto import VaultCrypto, VAULT_FORMAT_VERSION, ARGON2_TIME_COST, ARGON2_MEMORY_COST, ARGON2_PARALLELISM
from .storage import serialize_vault_data, deserialize_vault_data, create_vault_header, parse_vault_header
from .security import secure_delete_temp_file, set_vault_permissions, verify_vault_permissions
from ..models.entry import BaseEntry
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


class VaultManager:
    """Manages vault file operations and entry storage."""
    
    AUTO_LOCK_TIMEOUT = 300  # 5 minutes
    
    def __init__(self, vault_path: str, password: bytes):
        """Initialize vault manager."""
        self.vault_path = vault_path
        self.crypto = VaultCrypto(password)
        self.master_key: Optional[bytes] = None
        self.is_locked = True
        self.last_activity = time.time()
        self._lock = threading.Lock()
        self._entries: Dict[str, BaseEntry] = {}
        self._auto_lock_thread: Optional[threading.Thread] = None
        self._stop_auto_lock = threading.Event()
        self._attachment_storage: Optional[AttachmentStorage] = None
    
    def create_vault(self):
        """Create a new vault file. Raises FileExistsError if vault file already exists."""
        if os.path.exists(self.vault_path):
            raise FileExistsError(f"Vault file already exists: {self.vault_path}")
        salt = self.crypto.generate_salt()
        self.master_key = self.crypto.derive_master_key(salt)
        plaintext = serialize_vault_data({"entries": []})
        nonce, ciphertext = self.crypto.encrypt_aes_gcm(plaintext, self.master_key)
        header = create_vault_header(VAULT_FORMAT_VERSION, salt, {"time_cost": ARGON2_TIME_COST, "memory_cost": ARGON2_MEMORY_COST, "parallelism": ARGON2_PARALLELISM})
        header_bytes = serialize_vault_data(header)
        with open(self.vault_path, 'wb') as f:
            f.write(len(header_bytes).to_bytes(4, 'big'))
            f.write(header_bytes)
            f.write(nonce)
            f.write(ciphertext)
        set_vault_permissions(self.vault_path)
        self._init_attachment_storage()
        self.is_locked = False
        self._start_auto_lock()
    
    def unlock_vault(self) -> bool:
        """Unlock vault by reading and decrypting vault file. Raises FileNotFoundError, ValueError, or InvalidTag."""
        if not os.path.exists(self.vault_path):
            raise FileNotFoundError(f"Vault file not found: {self.vault_path}")
        is_secure, warning = verify_vault_permissions(self.vault_path)
        if not is_secure and warning:
            import warnings
            warnings.warn(f"Security warning: {warning}", UserWarning)
        with open(self.vault_path, 'rb') as f:
            header_len_bytes = f.read(4)
            if len(header_len_bytes) != 4:
                raise ValueError("Invalid vault file: cannot read header length")
            header_len = int.from_bytes(header_len_bytes, 'big')
            header_bytes = f.read(header_len)
            if len(header_bytes) != header_len:
                raise ValueError("Invalid vault file: cannot read header")
            header = parse_vault_header(header_bytes)
            if header["version"] != VAULT_FORMAT_VERSION:
                raise ValueError(f"Unsupported vault version: {header['version']}")
            nonce = f.read(12)
            if len(nonce) != 12:
                raise ValueError("Invalid vault file: cannot read nonce")
            ciphertext = f.read()
            if len(ciphertext) == 0:
                raise ValueError("Invalid vault file: empty ciphertext")
        salt = header["salt"]
        kdf_params = header.get("kdf_params", {})
        time_cost = kdf_params.get("time_cost", ARGON2_TIME_COST)
        memory_cost = kdf_params.get("memory_cost", ARGON2_MEMORY_COST)
        parallelism = kdf_params.get("parallelism", ARGON2_PARALLELISM)
        self.master_key = self.crypto.derive_master_key(salt, time_cost=time_cost, memory_cost=memory_cost, parallelism=parallelism)
        try:
            plaintext = self.crypto.decrypt_aes_gcm(nonce, ciphertext, self.master_key)
        except InvalidTag:
            self.master_key = None
            raise InvalidTag("Authentication failed: vault may be corrupted or password incorrect")
        vault_data = deserialize_vault_data(plaintext)
        self._entries = {}
        for entry_data in vault_data.get("entries", []):
            entry = self._entry_from_dict(entry_data)
            self._entries[entry.entry_id] = entry
        # Initialize attachment storage after unlocking
        self._init_attachment_storage()
        self.is_locked = False
        self._update_activity()
        self._start_auto_lock()
        return True
    
    def lock_vault(self):
        """Lock vault and clear sensitive data from memory."""
        self._stop_auto_lock.set()
        if self._auto_lock_thread:
            self._auto_lock_thread.join(timeout=1.0)
        if self.master_key:
            key_array = bytearray(self.master_key)
            for _ in range(3):  # Multiple overwrite passes
                for i in range(len(key_array)):
                    key_array[i] = 0
            self.master_key = None
        self.crypto.clear_memory(passes=3)
        self._entries.clear()
        self._attachment_storage = None
        self.is_locked = True
    
    def save_vault(self):
        """Save current vault state to file. Raises RuntimeError if vault is locked."""
        if self.is_locked:
            raise RuntimeError("Vault is locked")
        if self.master_key is None:
            raise RuntimeError("Master key not available")
        plaintext = serialize_vault_data({"entries": [entry.to_dict() for entry in self._entries.values()]})
        with open(self.vault_path, 'rb') as f:
            header_len = int.from_bytes(f.read(4), 'big')
            header = parse_vault_header(f.read(header_len))
            salt = header["salt"]
            kdf_params = header.get("kdf_params", {})
            time_cost = kdf_params.get("time_cost", ARGON2_TIME_COST)
            memory_cost = kdf_params.get("memory_cost", ARGON2_MEMORY_COST)
            parallelism = kdf_params.get("parallelism", ARGON2_PARALLELISM)
        nonce, ciphertext = self.crypto.encrypt_aes_gcm(plaintext, self.master_key)
        header = create_vault_header(VAULT_FORMAT_VERSION, salt, {"time_cost": time_cost, "memory_cost": memory_cost, "parallelism": parallelism})
        header_bytes = serialize_vault_data(header)
        temp_path = self.vault_path + ".tmp"
        try:
            with open(temp_path, 'wb') as f:
                f.write(len(header_bytes).to_bytes(4, 'big'))
                f.write(header_bytes)
                f.write(nonce)
                f.write(ciphertext)
            os.replace(temp_path, self.vault_path)
            set_vault_permissions(self.vault_path)
        except Exception:
            if os.path.exists(temp_path):
                secure_delete_temp_file(temp_path)
            raise
        self._update_activity()
    
    def add_entry(self, entry: BaseEntry):
        """Add entry to vault. Raises RuntimeError if vault is locked."""
        if self.is_locked:
            raise RuntimeError("Vault is locked")
        entry.update_modified()
        self._entries[entry.entry_id] = entry
        self.save_vault()
        self._update_activity()
    
    def get_entry(self, entry_id: str) -> Optional[BaseEntry]:
        """Get entry by ID. Raises RuntimeError if vault is locked."""
        if self.is_locked:
            raise RuntimeError("Vault is locked")
        self._update_activity()
        return self._entries.get(entry_id)
    
    def list_entries(self, entry_type: Optional[str] = None) -> List[BaseEntry]:
        """List all entries, optionally filtered by type. Raises RuntimeError if vault is locked."""
        if self.is_locked:
            raise RuntimeError("Vault is locked")
        self._update_activity()
        entries = list(self._entries.values())
        if entry_type:
            entries = [e for e in entries if e.get_entry_type() == entry_type]
        return entries
    
    def delete_entry(self, entry_id: str) -> bool:
        """Delete entry by ID. Returns True if deleted, False if not found. Raises RuntimeError if vault is locked."""
        if self.is_locked:
            raise RuntimeError("Vault is locked")
        if entry_id in self._entries:
            entry = self._entries[entry_id]
            # Clean up attachment if this is a document entry
            if isinstance(entry, DocumentEntry) and self._attachment_storage:
                try:
                    self._attachment_storage.delete_file(entry.file_reference)
                except Exception:
                    pass  # Ignore errors during cleanup
            del self._entries[entry_id]
            self.save_vault()
            self._update_activity()
            return True
        return False
    
    def _entry_from_dict(self, data: dict) -> BaseEntry:
        """Create entry object from dictionary using registry."""
        entry_type = data.get("type")
        entry_class = ENTRY_TYPE_REGISTRY.get(entry_type)
        if entry_class is None:
            raise ValueError(f"Unknown entry type: {entry_type}")
        return entry_class.from_dict(data)
    
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
    
    def _update_activity(self):
        """Update last activity timestamp."""
        with self._lock:
            self.last_activity = time.time()
    
    def _start_auto_lock(self):
        """Start auto-lock thread."""
        self._stop_auto_lock.clear()
        if self._auto_lock_thread is None or not self._auto_lock_thread.is_alive():
            self._auto_lock_thread = threading.Thread(target=self._auto_lock_worker, daemon=True)
            self._auto_lock_thread.start()
    
    def _auto_lock_worker(self):
        """Auto-lock worker thread."""
        while not self._stop_auto_lock.is_set():
            time.sleep(10)
            if self.is_locked:
                break
            with self._lock:
                if time.time() - self.last_activity >= self.AUTO_LOCK_TIMEOUT:
                    self.lock_vault()
                    break
