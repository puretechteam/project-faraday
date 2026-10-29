"""
Rolling encrypted backups of a vault file.

Before every save the manager hands the bytes currently on disk to
``BackupStore.snapshot_bytes``; they land in ``{vault}.backups/`` as
``{stem}.{UTC timestamp}.vault``. Snapshots are the same encrypted bytes as
the vault, so they need no extra protection. Retention keeps the newest
``keep_recent`` snapshots plus the newest snapshot of each of the last
``keep_daily`` days.

Snapshots cover the vault file only. Document attachments are never rewritten
in place, so ``export_full`` is the way to take a complete copy.
"""

import hashlib
import os
import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from .atomic import atomic_write_bytes

_STAMP = "%Y%m%dT%H%M%S%fZ"


@dataclass
class BackupInfo:
    path: str
    created: datetime  # UTC, timezone-aware
    size: int


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class BackupStore:
    def __init__(self, vault_path: str, keep_recent: int = 10, keep_daily: int = 14):
        self.vault_path = os.path.abspath(vault_path)
        self.directory = self.vault_path + ".backups"
        self.keep_recent = max(1, int(keep_recent))
        self.keep_daily = max(0, int(keep_daily))
        base = os.path.basename(self.vault_path)
        self._stem = base[:-6] if base.lower().endswith(".vault") else base

    def snapshot_bytes(self, data: bytes, now: Optional[datetime] = None) -> str:
        """Store ``data`` as a new snapshot and prune old ones. Returns the snapshot path."""
        os.makedirs(self.directory, exist_ok=True)
        now = now or datetime.now(timezone.utc)
        path = os.path.join(self.directory, f"{self._stem}.{now.strftime(_STAMP)}.vault")
        n = 1
        while os.path.exists(path):
            path = os.path.join(self.directory, f"{self._stem}.{now.strftime(_STAMP)}-{n}.vault")
            n += 1
        atomic_write_bytes(path, data, overwrite=False)
        self.prune(now=now)
        return path

    def snapshot(self) -> Optional[str]:
        """Snapshot the vault file as it is on disk now. Returns None if it does not exist."""
        if not os.path.exists(self.vault_path):
            return None
        with open(self.vault_path, "rb") as fh:
            return self.snapshot_bytes(fh.read())

    def list(self) -> List[BackupInfo]:
        """All snapshots, newest first."""
        if not os.path.isdir(self.directory):
            return []
        prefix = self._stem + "."
        found = []
        for name in os.listdir(self.directory):
            if not (name.startswith(prefix) and name.endswith(".vault")):
                continue
            stamp = name[len(prefix):-6].split("-")[0]
            try:
                created = datetime.strptime(stamp, _STAMP).replace(tzinfo=timezone.utc)
            except ValueError:
                continue
            path = os.path.join(self.directory, name)
            try:
                size = os.path.getsize(path)
            except OSError:
                continue
            found.append(BackupInfo(path=path, created=created, size=size))
        found.sort(key=lambda b: (b.created, b.path), reverse=True)
        return found

    def prune(self, now: Optional[datetime] = None) -> List[str]:
        """Apply retention. Returns the paths removed."""
        backups = self.list()
        now = now or datetime.now(timezone.utc)
        keep = {b.path for b in backups[: self.keep_recent]}
        if self.keep_daily:
            cutoff = (now - timedelta(days=self.keep_daily)).date()
            seen_days = set()
            for b in backups:  # newest first, so the first seen per day is the newest
                day = b.created.date()
                if day > cutoff and day not in seen_days:
                    seen_days.add(day)
                    keep.add(b.path)
        removed = []
        for b in backups:
            if b.path not in keep:
                try:
                    os.remove(b.path)
                    removed.append(b.path)
                except OSError:
                    pass
        return removed

    def export_full(self, dest_dir: str, vault_bytes: Optional[bytes] = None) -> str:
        """Copy the vault and its attachments into a new folder under ``dest_dir``.

        The copy is staged in a temporary folder, every file is hash-checked
        against its source, and only then is the folder renamed into place.
        Returns the final folder path.
        """
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        final = os.path.join(os.path.abspath(dest_dir), f"{self._stem}-backup-{stamp}")
        if os.path.exists(final):
            raise FileExistsError(f"Backup folder already exists: {final}")
        staging = final + ".partial"
        if os.path.exists(staging):
            shutil.rmtree(staging)
        os.makedirs(staging)
        try:
            vault_name = os.path.basename(self.vault_path)
            if vault_bytes is None:
                with open(self.vault_path, "rb") as fh:
                    vault_bytes = fh.read()
            dest_vault = os.path.join(staging, vault_name)
            atomic_write_bytes(dest_vault, vault_bytes, overwrite=False)
            if _sha256_file(dest_vault) != hashlib.sha256(vault_bytes).hexdigest():
                raise IOError("Backup verification failed for the vault file")
            attachments = self.vault_path + ".attachments"
            if os.path.isdir(attachments):
                dest_att = os.path.join(staging, vault_name + ".attachments")
                os.makedirs(dest_att)
                for name in sorted(os.listdir(attachments)):
                    src = os.path.join(attachments, name)
                    if not os.path.isfile(src):
                        continue
                    dst = os.path.join(dest_att, name)
                    shutil.copy2(src, dst)
                    if _sha256_file(src) != _sha256_file(dst):
                        raise IOError(f"Backup verification failed for attachment {name}")
            os.rename(staging, final)
        except BaseException:
            shutil.rmtree(staging, ignore_errors=True)
            raise
        return final
