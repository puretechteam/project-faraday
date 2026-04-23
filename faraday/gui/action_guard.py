"""
Optional local action PIN for sensitive GUI operations (delete, copy secrets, etc.).
PIN verification uses Argon2id. Hash and salt are stored only on this machine (not in the vault).
A short numeric PIN is weak against offline guessing if someone obtains the guard file; this is optional UX friction, not strong authentication.
"""

from __future__ import annotations

import json
import os
import secrets
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
from typing import Any, Dict, Optional, Tuple

import argon2
import argon2.low_level

from .icon_helper import set_window_icon

CONFIG_VERSION = 1
PIN_TIME_COST = 2
PIN_MEMORY_KIB = 65536
PIN_PARALLELISM = 2
PIN_HASH_LEN = 32


def _config_dir() -> str:
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    d = os.path.join(base, "FaradayVault")
    os.makedirs(d, exist_ok=True)
    return d


def guard_config_path() -> str:
    return os.path.join(_config_dir(), "action_guard.json")


def load_guard_config() -> Dict[str, Any]:
    path = guard_config_path()
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_guard_config(data: Dict[str, Any]) -> None:
    data = dict(data)
    data["version"] = CONFIG_VERSION
    path = guard_config_path()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def validate_pin_format(pin: str) -> Tuple[bool, str]:
    if len(pin) < 4:
        return False, "PIN must be at least 4 digits."
    if not pin.isdigit():
        return False, "PIN must contain only digits (0-9)."
    return True, ""


def _hash_pin(pin: str, salt: bytes) -> bytes:
    return argon2.low_level.hash_secret_raw(
        secret=pin.encode("utf-8"),
        salt=salt,
        time_cost=PIN_TIME_COST,
        memory_cost=PIN_MEMORY_KIB,
        parallelism=PIN_PARALLELISM,
        hash_len=PIN_HASH_LEN,
        type=argon2.low_level.Type.ID,
    )


def _verify_pin(pin: str, salt_hex: str, hash_hex: str) -> bool:
    try:
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
    except ValueError:
        return False
    if len(salt) != 16 or len(expected) != PIN_HASH_LEN:
        return False
    digest = _hash_pin(pin, salt)
    return secrets.compare_digest(digest, expected)


class _PinEntryModal:
    """Single PIN entry; sets self.result to str or None."""

    def __init__(self, parent: tk.Misc, title: str, prompt: str):
        self.result: Optional[str] = None
        self._win = tk.Toplevel(parent)
        self._win.title(title)
        self._win.transient(parent.winfo_toplevel())
        self._win.grab_set()
        set_window_icon(self._win)
        self._win.option_add("*TkEntry*show", "*")
        f = ttk.Frame(self._win, padding=16)
        f.pack(fill=tk.BOTH, expand=True)
        ttk.Label(f, text=prompt).pack(anchor=tk.W)
        self._var = tk.StringVar()
        ent = ttk.Entry(f, textvariable=self._var, width=24, show="*")
        ent.pack(fill=tk.X, pady=(6, 12))
        ent.focus_set()
        ent.bind("<Return>", lambda e: self._ok())
        bf = ttk.Frame(f)
        bf.pack(fill=tk.X)
        ttk.Button(bf, text="OK", command=self._ok).pack(side=tk.RIGHT, padx=(6, 0))
        ttk.Button(bf, text="Cancel", command=self._cancel).pack(side=tk.RIGHT)
        self._win.protocol("WM_DELETE_WINDOW", self._cancel)
        self._win.update_idletasks()
        px = parent.winfo_toplevel().winfo_rootx() + 80
        py = parent.winfo_toplevel().winfo_rooty() + 80
        self._win.geometry(f"+{px}+{py}")

    def _ok(self) -> None:
        self.result = self._var.get().strip()
        self._win.destroy()

    def _cancel(self) -> None:
        self.result = None
        self._win.destroy()

    def wait(self) -> Optional[str]:
        self._win.wait_window()
        return self.result


def ask_pin(parent: tk.Misc, title: str, prompt: str) -> Optional[str]:
    m = _PinEntryModal(parent, title, prompt)
    return m.wait()


def _offer_optional_pin(parent: tk.Misc) -> str:
    """Return 'setup' or 'skip'."""
    choice = tk.StringVar(value="skip")
    win = tk.Toplevel(parent.winfo_toplevel())
    win.title("Optional action PIN")
    win.transient(parent.winfo_toplevel())
    win.grab_set()
    set_window_icon(win)
    f = ttk.Frame(win, padding=16)
    f.pack(fill=tk.BOTH, expand=True)
    ttk.Label(
        f,
        text=(
            "You can set an optional action PIN (4+ digits) on this computer.\n"
            "When enabled, the app will ask for it before deleting entries, copying passwords\n"
            "and other secrets, downloading vault documents, and similar actions.\n\n"
            "You can change this anytime under Security in the menu bar."
        ),
        wraplength=420,
        justify=tk.LEFT,
    ).pack(anchor=tk.W, pady=(0, 12))
    bf = ttk.Frame(f)
    bf.pack(fill=tk.X)
    ttk.Button(bf, text="Set up action PIN", command=lambda: (choice.set("setup"), win.destroy())).pack(side=tk.LEFT, padx=(0, 8))
    ttk.Button(bf, text="Not now", command=lambda: (choice.set("skip"), win.destroy())).pack(side=tk.LEFT)
    win.protocol("WM_DELETE_WINDOW", lambda: (choice.set("skip"), win.destroy()))
    win.update_idletasks()
    rx = parent.winfo_toplevel().winfo_rootx() + 60
    ry = parent.winfo_toplevel().winfo_rooty() + 60
    win.geometry(f"+{rx}+{ry}")
    win.wait_window()
    return choice.get()


def _run_new_pin_setup(parent: tk.Misc) -> Optional[Tuple[str, str]]:
    """Return (salt_hex, hash_hex) or None if cancelled/invalid."""
    p1 = ask_pin(parent, "Set action PIN", "Enter a 4+ digit PIN:")
    if p1 is None:
        return None
    ok, err = validate_pin_format(p1)
    if not ok:
        messagebox.showerror("Invalid PIN", err)
        return None
    p2 = ask_pin(parent, "Confirm action PIN", "Re-enter the same PIN:")
    if p2 is None:
        return None
    if p1 != p2:
        messagebox.showerror("Error", "PINs do not match.")
        return None
    salt = secrets.token_bytes(16)
    digest = _hash_pin(p1, salt)
    return (salt.hex(), digest.hex())


def require_action_unlock(parent: tk.Misc) -> bool:
    """
    Call before a sensitive action. Handles one-time offer, PIN verify, or no-op if disabled.
    """
    cfg = load_guard_config()
    if cfg.get("enabled") and cfg.get("salt_hex") and cfg.get("hash_hex"):
        pin = ask_pin(parent.winfo_toplevel(), "Action PIN", "Enter your action PIN:")
        if pin is None:
            return False
        if _verify_pin(pin, cfg["salt_hex"], cfg["hash_hex"]):
            return True
        messagebox.showerror("Action PIN", "Incorrect PIN.")
        return False
    if not cfg.get("offer_shown"):
        ch = _offer_optional_pin(parent)
        cfg["offer_shown"] = True
        if ch == "setup":
            pair = _run_new_pin_setup(parent.winfo_toplevel())
            if pair:
                salt_hex, hash_hex = pair
                cfg["enabled"] = True
                cfg["salt_hex"] = salt_hex
                cfg["hash_hex"] = hash_hex
                messagebox.showinfo("Action PIN", "Action PIN is now enabled on this computer.")
            else:
                cfg["enabled"] = False
        else:
            cfg["enabled"] = False
        save_guard_config(cfg)
        return True
    return True


def menu_enable_or_change_action_pin(parent: tk.Misc) -> None:
    cfg = load_guard_config()
    top = parent.winfo_toplevel()
    if cfg.get("enabled") and cfg.get("hash_hex"):
        messagebox.showinfo("Action PIN", "Action PIN is already enabled. Use Change or Disable.")
        return
    pair = _run_new_pin_setup(top)
    if not pair:
        return
    salt_hex, hash_hex = pair
    cfg["offer_shown"] = True
    cfg["enabled"] = True
    cfg["salt_hex"] = salt_hex
    cfg["hash_hex"] = hash_hex
    save_guard_config(cfg)
    messagebox.showinfo("Action PIN", "Action PIN enabled.")


def menu_change_action_pin(parent: tk.Misc) -> None:
    cfg = load_guard_config()
    top = parent.winfo_toplevel()
    if not (cfg.get("enabled") and cfg.get("salt_hex") and cfg.get("hash_hex")):
        messagebox.showinfo("Action PIN", "Action PIN is not enabled.")
        return
    old = ask_pin(top, "Current action PIN", "Enter your current action PIN:")
    if old is None:
        return
    if not _verify_pin(old, cfg["salt_hex"], cfg["hash_hex"]):
        messagebox.showerror("Action PIN", "Incorrect PIN.")
        return
    pair = _run_new_pin_setup(top)
    if not pair:
        return
    salt_hex, hash_hex = pair
    cfg["salt_hex"] = salt_hex
    cfg["hash_hex"] = hash_hex
    save_guard_config(cfg)
    messagebox.showinfo("Action PIN", "Action PIN changed.")


def menu_disable_action_pin(parent: tk.Misc) -> None:
    cfg = load_guard_config()
    top = parent.winfo_toplevel()
    if not (cfg.get("enabled") and cfg.get("salt_hex") and cfg.get("hash_hex")):
        messagebox.showinfo("Action PIN", "Action PIN is not enabled.")
        return
    pin = ask_pin(top, "Disable action PIN", "Enter your action PIN to disable protection:")
    if pin is None:
        return
    if not _verify_pin(pin, cfg["salt_hex"], cfg["hash_hex"]):
        messagebox.showerror("Action PIN", "Incorrect PIN.")
        return
    cfg["enabled"] = False
    cfg["salt_hex"] = ""
    cfg["hash_hex"] = ""
    save_guard_config(cfg)
    messagebox.showinfo("Action PIN", "Action PIN disabled. Sensitive actions no longer require it.")


def show_scrollable_secret_dialog(parent: tk.Misc, title: str, body: str) -> None:
    """Show long text in a scrollable window (avoids OS message box truncation)."""
    win = tk.Toplevel(parent.winfo_toplevel())
    win.title(title)
    win.transient(parent.winfo_toplevel())
    set_window_icon(win)
    f = ttk.Frame(win, padding=8)
    f.pack(fill=tk.BOTH, expand=True)
    txt = scrolledtext.ScrolledText(f, width=80, height=20, wrap=tk.WORD, font=("Consolas", 10))
    txt.pack(fill=tk.BOTH, expand=True)
    txt.insert("1.0", body)
    txt.configure(state=tk.DISABLED)
    ttk.Button(f, text="Close", command=win.destroy).pack(pady=8)
    win.geometry("700x480")
