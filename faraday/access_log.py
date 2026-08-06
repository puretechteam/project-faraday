"""Audit trail for Faraday 3.0.0 vault access events.

This module records an audit trail of attempts to open/use the app and unlock
the vault. It is deliberately free of any tkinter dependency so it can be
imported by the CLI and the vault manager as well as the GUI.

Every disk operation is wrapped so it can NEVER raise and NEVER block an
unlock/lock. A module-level lock guards the read-modify-write and writes are
performed atomically via a temp file + os.replace.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from datetime import datetime
from pathlib import Path

MAX_EVENTS = 1000

# Event written whenever the log is wiped. These markers survive a clear so the
# history of which vault cleared the log (and when) can never be erased
# silently.
CLEAR_EVENT = "log_cleared"

_write_lock = threading.Lock()


def app_data_dir() -> Path:
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA")
        if not base:
            base = os.path.expanduser("~\\AppData\\Local")
        path = Path(base) / "FaradayVault"
    else:
        xdg = os.environ.get("XDG_CONFIG_HOME")
        if xdg:
            path = Path(xdg) / "FaradayVault"
        else:
            path = Path(os.path.expanduser("~/.config")) / "FaradayVault"
    try:
        path.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return path


def access_log_path() -> Path:
    return app_data_dir() / "access_log.json"


def _read_all() -> list[dict]:
    try:
        with access_log_path().open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, list):
            return data
        return []
    except (OSError, json.JSONDecodeError, Exception):
        return []


def _write_all(events: list[dict]) -> None:
    path = access_log_path()
    try:
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(events, fh, indent=2)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except Exception:
                    pass
    except (OSError, json.JSONDecodeError, Exception):
        return


def record(event: str, *, vault_path: str | None = None, reason: str | None = None, source: str = "gui") -> None:
    try:
        with _write_lock:
            events = _read_all()
            entry: dict = {
                "ts": datetime.now().astimezone().isoformat(),
                "event": event,
                "reason": reason,
                "vault_path": vault_path,
                "vault_name": os.path.basename(vault_path) if vault_path else None,
                "source": source,
            }
            events.append(entry)
            if len(events) > MAX_EVENTS:
                events = events[-MAX_EVENTS:]
            _write_all(events)
    except (OSError, json.JSONDecodeError, Exception):
        return


def load_events(vault_path=None, limit: int = 500) -> list[dict]:
    try:
        events = _read_all()
        if vault_path is not None:
            events = [e for e in events if e.get("vault_path") == vault_path]
        if limit is not None and len(events) > limit:
            events = events[-limit:]
        # returns newest last
        return events
    except (OSError, json.JSONDecodeError, Exception):
        return []


def clear(keep_events=(CLEAR_EVENT,)) -> None:
    """Wipe the audit trail, retaining the ``keep_events`` markers.

    By default every ``log_cleared`` entry survives, so the record of which
    vault cleared the log (and when) persists for other users. Pass an empty
    sequence to delete the file outright.
    """
    try:
        keep = {str(name) for name in (keep_events or ())}
        with _write_lock:
            if not keep:
                path = access_log_path()
                if path.exists():
                    path.unlink()
                return
            retained = [
                ev for ev in _read_all()
                if isinstance(ev, dict) and ev.get("event") in keep
            ]
            if len(retained) > MAX_EVENTS:
                retained = retained[-MAX_EVENTS:]
            _write_all(retained)
    except (OSError, json.JSONDecodeError, Exception):
        return


def describe(ev: dict) -> str:
    event = ev.get("event", "")
    reason = ev.get("reason")
    if event == "unlock_succeeded":
        return "Vault unlocked"
    if event == "unlock_failed":
        if reason == "bad_password_or_corrupt":
            return "Failed sign-in — wrong password or damaged vault file"
        if reason == "vault_missing":
            return "Failed sign-in — vault file not found"
        if reason == "vault_damaged":
            return "Failed sign-in — vault file is corrupted or wrong format"
        return "Failed sign-in"
    if event == "unlock_cancelled":
        return "Sign-in cancelled"
    if event == "vault_locked":
        if reason == "auto_timeout":
            return "Vault locked automatically after 5 minutes of inactivity"
        if reason == "manual":
            return "Vault locked"
        if reason == "switch_vault":
            return "Vault locked to open another"
        if reason == "app_exit":
            return "Vault locked on app exit"
        return "Vault locked"
    if event == "vault_created":
        return "Vault created"
    if event == "app_launched":
        return "Faraday opened"
    if event == "app_closed":
        return "Faraday closed"
    if event == CLEAR_EVENT:
        return "Access log cleared"
    return event
