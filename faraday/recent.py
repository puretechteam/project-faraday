"""
Recently opened vaults, stored in the app data folder.

3.0 kept this list in ``.faraday_vault_history.json`` in whatever folder the
app was launched from. On first use the old file there is imported once and
left in place.
"""

import json
import os
from typing import List

from .paths import app_data_dir
from .vault.atomic import atomic_write_bytes

MAX_RECENT = 10
LEGACY_FILE = ".faraday_vault_history.json"


def _path():
    return app_data_dir() / "recent_vaults.json"


def _read(path) -> List[str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if isinstance(data, dict):
        data = data.get("recent_vaults") or data.get("vaults") or []
    return [p for p in data if isinstance(p, str)] if isinstance(data, list) else []


def _write(paths: List[str]) -> None:
    try:
        atomic_write_bytes(str(_path()), json.dumps(paths[:MAX_RECENT], indent=2).encode("utf-8"))
    except OSError:
        pass


def load_recent(existing_only: bool = True) -> List[str]:
    path = _path()
    if path.exists():
        paths = _read(path)
    else:
        from pathlib import Path
        paths = _read(Path(os.getcwd()) / LEGACY_FILE)
        _write(paths)
    seen, result = set(), []
    for p in paths:
        key = os.path.normcase(os.path.abspath(p))
        if key in seen:
            continue
        seen.add(key)
        if existing_only and not os.path.isfile(p):
            continue
        result.append(p)
    return result[:MAX_RECENT]


def add_recent(vault_path: str) -> None:
    vault_path = os.path.abspath(vault_path)
    key = os.path.normcase(vault_path)
    paths = [p for p in load_recent(existing_only=False) if os.path.normcase(os.path.abspath(p)) != key]
    _write([vault_path] + paths)


def remove_recent(vault_path: str) -> None:
    key = os.path.normcase(os.path.abspath(vault_path))
    _write([p for p in load_recent(existing_only=False) if os.path.normcase(os.path.abspath(p)) != key])
