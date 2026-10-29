"""
Where Faraday keeps things on disk.

* App data (settings, PIN, access log, recent vaults): ``%LOCALAPPDATA%\\FaradayVault``
  on Windows, ``$XDG_CONFIG_HOME/FaradayVault`` elsewhere. ``FARADAY_APPDATA``
  overrides it, which tests and scratch runs use to stay away from real data.
* Default vault folder: ``Documents/Faraday`` (the user's Documents folder,
  wherever Windows has it redirected). ``FARADAY_VAULTS_DIR`` overrides it.
  3.0 used ``./vaults`` in the launch folder; vaults there still open from the
  recent list or by browsing to them.
"""

import os
from pathlib import Path


def app_data_dir() -> Path:
    override = os.environ.get("FARADAY_APPDATA")
    if override:
        path = Path(override)
    elif os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~\\AppData\\Local")
        path = Path(base) / "FaradayVault"
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
        path = Path(base) / "FaradayVault"
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return path


def documents_dir() -> Path:
    """The user's Documents folder (follows OneDrive or folder redirection on Windows)."""
    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes
            buf = ctypes.create_unicode_buffer(wintypes.MAX_PATH)
            if ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buf) == 0 and buf.value:  # CSIDL_PERSONAL
                return Path(buf.value)
        except Exception:
            pass
    return Path(os.path.expanduser("~")) / "Documents"


def default_vaults_dir(create: bool = True) -> Path:
    override = os.environ.get("FARADAY_VAULTS_DIR")
    path = Path(override) if override else documents_dir() / "Faraday"
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path
