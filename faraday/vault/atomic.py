"""
Crash-safe file writes.

Data is written to a uniquely named temp file next to the target, flushed and
fsynced, then moved into place. A crash at any point leaves either the old file
or the new file, never a truncated mix.
"""

import os
import tempfile
import time

_REPLACE_RETRIES = 5
_RETRY_DELAY = 0.05


def _fsync_dir(directory: str) -> None:
    """Persist the directory entry on POSIX. Windows cannot open directories for fsync."""
    if os.name == "nt":
        return
    try:
        fd = os.open(directory, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def _move_into_place(tmp: str, path: str, overwrite: bool) -> None:
    if overwrite:
        os.replace(tmp, path)
        return
    if os.name == "nt":
        os.rename(tmp, path)  # fails with FileExistsError if path exists
    else:
        os.link(tmp, path)  # fails with FileExistsError if path exists
        os.remove(tmp)


def atomic_write_bytes(path: str, data: bytes, *, overwrite: bool = True) -> None:
    """Write ``data`` to ``path`` atomically.

    With ``overwrite=False`` the call raises FileExistsError instead of
    replacing an existing file. Antivirus and the search indexer briefly hold
    files open on Windows, so a PermissionError on the final move is retried.
    """
    path = os.path.abspath(path)
    directory = os.path.dirname(path)
    fd, tmp = tempfile.mkstemp(prefix=os.path.basename(path) + ".", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        for attempt in range(_REPLACE_RETRIES):
            try:
                _move_into_place(tmp, path, overwrite)
                break
            except PermissionError:
                if attempt == _REPLACE_RETRIES - 1:
                    raise
                time.sleep(_RETRY_DELAY * (attempt + 1))
        _fsync_dir(directory)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
