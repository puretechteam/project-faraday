"""
Exclusive lock on ``{vault}.lock`` so two Faraday processes (or a GUI and the
CLI) can never write the same vault at once. The OS drops the lock if the
process dies, so a leftover lock file is never stale.
"""

import os
from typing import Optional

from .errors import VaultInUseError


class VaultFileLock:
    def __init__(self, vault_path: str):
        self.path = os.path.abspath(vault_path) + ".lock"
        self._fh = None

    @property
    def held(self) -> bool:
        return self._fh is not None

    def acquire(self) -> None:
        if self._fh is not None:
            return
        fh = open(self.path, "a+b")
        try:
            if os.name == "nt":
                import msvcrt
                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            fh.close()
            raise VaultInUseError(
                f"Vault is open in another Faraday window or CLI: {os.path.basename(self.path[:-5])}"
            )
        self._fh = fh

    def release(self) -> None:
        fh: Optional[object] = self._fh
        if fh is None:
            return
        self._fh = None
        try:
            if os.name == "nt":
                import msvcrt
                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        finally:
            fh.close()
        # Only tidy up on Windows, where the delete fails if anyone else has the
        # file open. On POSIX, unlinking a flock file lets two processes lock
        # different inodes, so the file is left in place there.
        if os.name == "nt":
            try:
                os.remove(self.path)
            except OSError:
                pass
