"""
Optional local action PIN for sensitive GUI operations (delete, copy secrets, etc.).
PIN verification uses Argon2id. Hash and salt are stored only on this machine (not in the vault).
A short numeric PIN is weak against offline guessing if someone obtains the guard file; this is optional UX friction, not strong authentication.

For irreversible actions the PIN is not enough: :func:`require_master_password`
prompts for the vault's real master password and verifies it against the
unlocked :class:`~faraday.vault.manager.VaultManager`.
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

from .design_system import SPACING, font_role, get_active_merged
from .icon_helper import set_window_icon
from .ui_theme import theme_toplevel_window
from .widgets.dialogs import Dialog, ThemedPasswordDialog
from .widgets.inputs import DangerButton, GhostButton, PrimaryButton

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
    """Single PIN entry (themed Dialog); sets self.result to str or None.

    Behavior is identical to the previous custom Toplevel: returns the stripped
    PIN on OK, ``None`` on Cancel / window close / Escape.
    """

    def __init__(self, parent: tk.Misc, title: str, prompt: str):
        self.result: Optional[str] = None
        self._win = Dialog(parent.winfo_toplevel(), title=title, width=360, height=180)
        tk.Label(
            self._win.content, text=prompt, font=font_role("body"), anchor=tk.W
        ).pack(anchor=tk.W, padx=SPACING["md"], pady=(SPACING["md"], SPACING["xs"]))
        self._var = tk.StringVar()
        ent = ttk.Entry(self._win.content, textvariable=self._var, width=24, show="*")
        ent.pack(fill=tk.X, padx=SPACING["md"])
        ent.focus_set()
        ent.bind("<Return>", lambda e: self._ok())
        bf = tk.Frame(self._win.content, bd=0, highlightthickness=0)
        bf.pack(fill=tk.X, padx=SPACING["md"], pady=SPACING["md"])
        PrimaryButton(bf, text="OK", command=self._ok).pack(side=tk.RIGHT, padx=(SPACING["sm"], 0))
        DangerButton(bf, text="Cancel", command=self._cancel).pack(side=tk.RIGHT)
        self._win.protocol("WM_DELETE_WINDOW", self._cancel)

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
    """Return 'setup' or 'skip' (themed Dialog)."""
    choice = tk.StringVar(value="skip")
    win = Dialog(parent.winfo_toplevel(), title="Optional action PIN", width=460, height=300)
    tk.Label(
        win.content,
        text=(
            "You can set an optional action PIN (4+ digits) on this computer.\n"
            "When enabled, the app will ask for it before deleting entries, copying passwords\n"
            "and other secrets, downloading vault documents, and similar actions.\n\n"
            "You can change this anytime under Security in the menu bar."
        ),
        wraplength=420,
        justify=tk.LEFT,
        font=font_role("body"),
    ).pack(anchor=tk.W, padx=SPACING["md"], pady=SPACING["md"])
    bf = tk.Frame(win.content, bd=0, highlightthickness=0)
    bf.pack(fill=tk.X, padx=SPACING["md"], pady=SPACING["md"])
    PrimaryButton(bf, text="Set up action PIN",
                  command=lambda: (choice.set("setup"), win.destroy())).pack(side=tk.LEFT, padx=(0, SPACING["sm"]))
    GhostButton(bf, text="Not now", command=lambda: (choice.set("skip"), win.destroy())).pack(side=tk.LEFT)
    win.protocol("WM_DELETE_WINDOW", lambda: (choice.set("skip"), win.destroy()))
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


def require_master_password(parent: tk.Misc, manager: Any) -> bool:
    """Require the vault's MASTER password before a high-risk action.

    Unlike :func:`require_action_unlock` (a short, machine-local PIN that is
    only optional UX friction), this proves the caller knows the password that
    actually encrypts the vault. Use it for destructive/irreversible actions
    such as wiping the access log.

    Re-prompts after a wrong password; returns False when the user cancels or
    when verification is impossible. Never raises.
    """
    if manager is None:
        return False
    verify = getattr(manager, "verify_password", None)
    if not callable(verify):
        return False
    try:
        top = parent.winfo_toplevel()
    except Exception:
        top = parent
    while True:
        try:
            dialog = ThemedPasswordDialog(
                top,
                title="Master password required",
                confirm=False,
                show_generate=False,
                prompt="Enter this vault's master password:",
                ok_label="Confirm",
            )
            pwd = dialog.show()
        except Exception:
            return False
        # Cancel / window close / Escape -> silent no-op for the caller.
        if pwd is None:
            return False
        try:
            candidate = pwd.encode("utf-8") if isinstance(pwd, str) else pwd
            ok = bool(verify(candidate))
        except Exception:
            ok = False
        finally:
            pwd = None
        if ok:
            return True
        try:
            messagebox.showerror("Incorrect", "Master password is incorrect.")
        except Exception:
            return False


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
    # Paint the raw Toplevel so the frame around the ttk/ScrolledText content
    # matches the active palette instead of the default white.
    try:
        theme_toplevel_window(win, get_active_merged())
    except Exception:
        pass
    f = ttk.Frame(win, padding=8)
    f.pack(fill=tk.BOTH, expand=True)
    txt = scrolledtext.ScrolledText(f, width=80, height=20, wrap=tk.WORD, font=("Consolas", 10))
    txt.pack(fill=tk.BOTH, expand=True)
    txt.insert("1.0", body)
    txt.configure(state=tk.DISABLED)
    ttk.Button(f, text="Close", command=win.destroy).pack(pady=8)
    win.geometry("700x480")
