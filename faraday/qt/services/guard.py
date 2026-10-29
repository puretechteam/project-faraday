"""
The single place that decides when to ask for the PIN or the master password.

Tier 0  browse, search, copy non-secret fields, generator, appearance settings: never asks.
Tier 1  reveal or copy a secret, edit, delete, export a document: asks for the
        action PIN if one is set, then trusts the session for ``pin_grace_seconds``.
        After MAX_PIN_FAILURES wrong PINs only the master password is accepted
        until the next unlock. With no PIN set, tier 1 does not ask.
Tier 2  restore a backup, clear the access log, change or remove the PIN, turn
        auto-lock off, re-key: master password every time.
"""

import time
from typing import Optional

from PySide6.QtCore import QObject
from PySide6.QtWidgets import QDialog

from ... import pin as pin_store

BROWSE, SENSITIVE, CRITICAL = 0, 1, 2


class Guard(QObject):
    def __init__(self, settings, service, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.service = service
        self._last_ok = 0.0
        self._failures = 0
        service.locked.connect(lambda *_: self.reset())

    def reset(self) -> None:
        self._last_ok = 0.0
        self._failures = 0

    def require(self, tier: int, parent, action: str = "continue") -> bool:
        if tier <= BROWSE:
            return True
        if tier >= CRITICAL:
            return self.master_password(parent, action) is not None
        if not pin_store.pin_enabled():
            return True
        if self._failures >= pin_store.MAX_PIN_FAILURES:
            return self.master_password(parent, action, after_pin_lockout=True) is not None
        grace = int(self.settings.pin_grace_seconds)
        if grace and time.monotonic() - self._last_ok < grace:
            return True
        from ..widgets.dialogs import PinDialog

        def verify(pin: str) -> bool:
            if pin and pin_store.verify_pin(pin):
                self._failures = 0
                self._last_ok = time.monotonic()
                return True
            self._failures += 1
            return False

        def keep_trying() -> bool:
            return self._failures < pin_store.MAX_PIN_FAILURES

        dlg = PinDialog(parent, f"Enter your PIN to {action}.", verify, keep_trying)
        result = dlg.exec()
        if result == QDialog.Accepted:
            return True
        if result == 2:
            return self.master_password(parent, action, after_pin_lockout=True) is not None
        return False

    def master_password(self, parent, action: str = "continue", after_pin_lockout: bool = False) -> Optional[bytes]:
        """Ask for and verify the master password. Returns it on success, None if cancelled."""
        from ..widgets.dialogs import PasswordPromptDialog
        prompt = (f"Too many wrong PINs. Enter your master password to {action}."
                  if after_pin_lockout else f"Enter your master password to {action}.")
        dlg = PasswordPromptDialog(parent, "Confirm it is you", prompt,
                                   lambda pw, cb: self.service.verify_password(pw, cb, lambda e: cb(False)))
        if dlg.exec() == QDialog.Accepted and dlg.password:
            self._last_ok = time.monotonic()
            return dlg.password
        return None
