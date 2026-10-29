"""
The only object the Qt GUI uses to touch a vault.

* Every operation that derives a key or writes to disk runs on VAULT_POOL
  (one thread, so operations never overlap) and reports back on the GUI thread.
* Views get secret-free ``EntrySummary`` rows; secret values are read on
  demand with ``value()`` and never cached by the service.
* ``lock()`` clears everything immediately and emits ``locked``.
"""

import os
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Dict, List, Optional

from PySide6.QtCore import QObject, Signal

from ... import recent
from ...models.entry import BaseEntry
from ...models.opaque_entry import OpaqueEntry
from ...models.schema import REGISTRY, entry_subtitle, entry_title, is_secret, spec_for, to_text
from ...vault.crypto import get_argon2_params
from ...vault.manager import VaultManager
from .workers import VAULT_POOL, run_async

KDF_LEVELS = {
    "standard": ("Standard", "About half a second to unlock on a typical PC."),
    "high": ("High", "Roughly twice as slow to unlock, twice as slow to attack."),
    "maximum": ("Maximum", "Several seconds to unlock; for very sensitive vaults."),
}


@dataclass(frozen=True)
class EntrySummary:
    entry_id: str
    type_id: str
    title: str
    subtitle: str
    modified: Optional[datetime]
    created: Optional[datetime]
    search_text: str
    opaque: bool = False


def summarize(entry: BaseEntry) -> EntrySummary:
    from ...models.schema import entry_matches  # noqa: F401  (same rules as search)
    spec = spec_for(entry)
    parts = [entry_title(entry), entry_subtitle(entry)]
    if spec:
        parts.append(spec.label)
        parts += [to_text(f, getattr(entry, f.key, None)) for f in spec.fields
                  if f.searchable and not is_secret(spec.type_id, f)]
    else:
        parts.append(entry.get_entry_type())
    return EntrySummary(
        entry_id=entry.entry_id,
        type_id=entry.get_entry_type() if spec else "_opaque",
        title=entry_title(entry),
        subtitle=entry_subtitle(entry),
        modified=getattr(entry, "modified", None),
        created=getattr(entry, "created", None),
        search_text=" ".join(p for p in parts if p).lower(),
        opaque=isinstance(entry, OpaqueEntry),
    )


Done = Optional[Callable[[object], None]]
Fail = Optional[Callable[[BaseException], None]]


class VaultService(QObject):
    unlocked = Signal(str)
    locked = Signal(str)
    entriesChanged = Signal()
    busyChanged = Signal(bool)

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self._manager: Optional[VaultManager] = None
        self._busy = 0

    # ---------------------------------------------------------------- state

    @property
    def is_unlocked(self) -> bool:
        return self._manager is not None and not self._manager.is_locked

    @property
    def path(self) -> Optional[str]:
        return self._manager.vault_path if self._manager else None

    @property
    def manager(self) -> Optional[VaultManager]:
        return self._manager if self.is_unlocked else None

    def _run(self, fn, on_done: Done, on_error: Fail, changes: bool = False):
        self._busy += 1
        if self._busy == 1:
            self.busyChanged.emit(True)

        def finish():
            self._busy -= 1
            if self._busy == 0:
                self.busyChanged.emit(False)

        def done(result):
            finish()
            if changes and self.is_unlocked:
                self.entriesChanged.emit()
            if on_done:
                on_done(result)

        def failed(exc):
            finish()
            if on_error:
                on_error(exc)

        run_async(fn, done, failed, pool=VAULT_POOL)

    def _new_manager(self, path: str, password: bytes) -> VaultManager:
        return VaultManager(
            path, password,
            auto_lock_seconds=None,  # the GUI tracks idle time itself
            backup_keep_recent=self.settings.backup_keep_recent,
            backup_keep_daily=self.settings.backup_keep_daily,
        )

    # ---------------------------------------------------------------- open / create / lock

    def open(self, path: str, password: bytes, on_done: Done = None, on_error: Fail = None):
        if self.is_unlocked:
            self.lock("switch_vault")
        manager = self._new_manager(path, password)

        def work():
            manager.unlock_vault()
            return manager

        def done(m):
            self._manager = m
            recent.add_recent(m.vault_path)
            self.unlocked.emit(m.vault_path)
            if on_done:
                on_done(m.vault_path)
        self._run(work, done, on_error)

    def create(self, path: str, password: bytes, level: str = "standard",
               on_done: Done = None, on_error: Fail = None):
        if self.is_unlocked:
            self.lock("switch_vault")
        manager = self._new_manager(path, password)

        def work():
            manager.create_vault(kdf_params=get_argon2_params(level))
            return manager

        def done(m):
            self._manager = m
            recent.add_recent(m.vault_path)
            self.unlocked.emit(m.vault_path)
            if on_done:
                on_done(m.vault_path)
        self._run(work, done, on_error)

    def lock(self, reason: str = "manual") -> None:
        manager, self._manager = self._manager, None
        if manager is not None and not manager.is_locked:
            manager.lock_vault(reason=reason)  # waits for any in-flight save
            self.locked.emit(reason)

    # ---------------------------------------------------------------- reading

    def summaries(self, type_id: Optional[str] = None) -> List[EntrySummary]:
        if not self.is_unlocked:
            return []
        entries = self._manager.list_entries(include_opaque=True)
        rows = [summarize(e) for e in entries]
        if type_id:
            rows = [r for r in rows if r.type_id == type_id]
        rows.sort(key=lambda r: (r.title or "").lower())
        return rows

    def counts(self) -> Dict[str, int]:
        counts = {t: 0 for t in REGISTRY}
        for r in self.summaries():
            counts[r.type_id] = counts.get(r.type_id, 0) + 1
        return counts

    def entry(self, entry_id: str) -> Optional[BaseEntry]:
        """The live entry object. Treat it as read-only; edits go through update()."""
        return self._manager.get_entry(entry_id) if self.is_unlocked else None

    def value(self, entry_id: str, key: str) -> str:
        entry = self.entry(entry_id)
        spec = spec_for(entry) if entry else None
        if not spec:
            return ""
        return to_text(spec.field(key), getattr(entry, key, None))

    def entries(self, type_id: str) -> List[BaseEntry]:
        """Entries of one type, for health checks. Never hand these to widgets that keep them."""
        return self._manager.list_entries(type_id) if self.is_unlocked else []

    def backups(self):
        m = self.manager
        return m.backups.list() if m and m.backups else []

    # ---------------------------------------------------------------- writing (async)

    def add(self, entry: BaseEntry, on_done: Done = None, on_error: Fail = None):
        m = self._manager
        self._run(lambda: (m.add_entry(entry), entry.entry_id)[1], on_done, on_error, changes=True)

    def update(self, entry: BaseEntry, on_done: Done = None, on_error: Fail = None):
        m = self._manager
        self._run(lambda: (m.update_entry(entry), entry.entry_id)[1], on_done, on_error, changes=True)

    def delete(self, entry_id: str, on_done: Done = None, on_error: Fail = None):
        m = self._manager
        self._run(lambda: m.delete_entry(entry_id), on_done, on_error, changes=True)

    def add_document(self, source: str, category: str, note: str, on_done: Done = None, on_error: Fail = None):
        m = self._manager
        self._run(lambda: m.add_document(source, category=category, site_note=note).entry_id,
                  on_done, on_error, changes=True)

    def export_document(self, entry_id: str, dest: str, on_done: Done = None, on_error: Fail = None):
        m = self._manager
        self._run(lambda: m.export_document(entry_id, dest), on_done, on_error)

    def export_full_backup(self, dest_dir: str, on_done: Done = None, on_error: Fail = None):
        m = self._manager
        self._run(lambda: m.export_full_backup(dest_dir), on_done, on_error)

    def import_entries(self, entries, attachments, on_done: Done = None, on_error: Fail = None):
        m = self._manager
        self._run(lambda: m.import_entries(entries, attachments), on_done, on_error, changes=True)

    def export_archive(self, path: str, password: bytes, on_done: Done = None, on_error: Fail = None):
        """Write every entry and document into a password-protected ``.faraday`` archive."""
        from ...transfer.archive import write_archive
        m = self._manager

        def work():
            records, files = m.export_records()
            write_archive(path, records, files, password)
            return path
        self._run(work, on_done, on_error)

    def restore_backup(self, backup_path: str, password: bytes, on_done: Done = None, on_error: Fail = None):
        """Restore a snapshot. The vault locks afterwards (reason ``restored_backup``)."""
        m = self._manager

        def done(count):
            if self._manager is m:
                self._manager = None
                self.locked.emit("restored_backup")
            if on_done:
                on_done(count)
        self._run(lambda: m.restore_backup(backup_path, password), done, on_error)

    def verify_password(self, password: bytes, on_done: Done = None, on_error: Fail = None):
        m = self._manager
        if m is None:
            if on_done:
                on_done(False)
            return
        # Not on VAULT_POOL: verification reads nothing from disk and must not
        # queue behind a slow save.
        run_async(lambda: m.verify_password(password), on_done, on_error)

    def vault_name(self) -> str:
        return os.path.basename(self.path or "")
