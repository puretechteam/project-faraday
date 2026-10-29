"""
Themed dialogs. Every dialog has a parent window (never ownerless or frameless:
an ownerless modal sinking behind the main window is what froze 3.0) and is
closed automatically when the vault locks.
"""

from typing import Callable, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QLineEdit, QProgressBar, QPushButton, QVBoxLayout, QWidget,
)

from ... import pin as pin_store
from .. import theme
from .common import IconLabel, SecretLineEdit, alive, button, label


class FaradayDialog(QDialog):
    """Base dialog: title, body layout, right-aligned footer buttons."""

    closes_on_lock = True

    def __init__(self, parent: QWidget, title: str, width: int = 440):
        assert parent is not None, "Faraday dialogs must have a parent window"
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(width)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(22, 20, 22, 18)
        outer.setSpacing(14)
        self.body = QVBoxLayout()
        self.body.setSpacing(10)
        outer.addLayout(self.body, 1)
        self.footer = QHBoxLayout()
        self.footer.setSpacing(8)
        self.footer.addStretch(1)
        outer.addLayout(self.footer)

    def add_button(self, text: str, variant: str = "", on_click: Optional[Callable] = None,
                   default: bool = False) -> QPushButton:
        b = button(text, variant, on_click=on_click)
        if default:
            b.setDefault(True)
            b.setAutoDefault(True)
        else:
            b.setAutoDefault(False)
        self.footer.addWidget(b)
        return b

    def showEvent(self, event):
        theme.set_dark_title_bar(self, theme.current().dark)
        super().showEvent(event)


def _heading(icon_name: str, role: str, title: str, text: str) -> QHBoxLayout:
    row = QHBoxLayout()
    row.setSpacing(14)
    row.addWidget(IconLabel(icon_name, 26, role), 0, Qt.AlignTop)
    col = QVBoxLayout()
    col.setSpacing(6)
    col.addWidget(label(title, "heading", wrap=True))
    if text:
        col.addWidget(label(text, "muted", wrap=True))
    row.addLayout(col, 1)
    return row


def message(parent: QWidget, title: str, text: str, kind: str = "info") -> None:
    icon_name, role = {"info": ("info", "accent"), "error": ("circle-alert", "danger"),
                       "warning": ("triangle-alert", "warning"), "success": ("circle-check", "success")}[kind]
    dlg = FaradayDialog(parent, title)
    dlg.body.addLayout(_heading(icon_name, role, title, text))
    dlg.add_button("OK", "primary", dlg.accept, default=True)
    dlg.exec()


def confirm(parent: QWidget, title: str, text: str, confirm_text: str = "Continue",
            danger: bool = False, cancel_text: str = "Cancel") -> bool:
    dlg = FaradayDialog(parent, title)
    dlg.body.addLayout(_heading("triangle-alert" if danger else "info", "danger" if danger else "accent", title, text))
    dlg.add_button(cancel_text, "ghost", dlg.reject)
    dlg.add_button(confirm_text, "danger" if danger else "primary", dlg.accept, default=not danger)
    return dlg.exec() == QDialog.Accepted


class PinDialog(FaradayDialog):
    """Asks for the action PIN; ``verify(pin) -> bool`` is checked before closing."""

    def __init__(self, parent, prompt: str, verify: Callable[[str], bool], on_fail: Callable[[], bool]):
        super().__init__(parent, "Enter PIN", 380)
        self._verify, self._on_fail = verify, on_fail
        self.body.addLayout(_heading("lock", "accent", "Enter your PIN", prompt))
        self.edit = QLineEdit()
        self.edit.setEchoMode(QLineEdit.Password)
        self.edit.setMaxLength(16)
        self.edit.setPlaceholderText("PIN")
        self.edit.setAlignment(Qt.AlignCenter)
        self.edit.setProperty("mono", "true")
        self.body.addWidget(self.edit)
        self.error = label("", "error")
        self.error.hide()
        self.body.addWidget(self.error)
        self.add_button("Cancel", "ghost", self.reject)
        self.add_button("Unlock", "primary", self._submit, default=True)
        self.edit.returnPressed.connect(self._submit)

    def _submit(self):
        if self._verify(self.edit.text().strip()):
            self.accept()
            return
        self.edit.clear()
        if not self._on_fail():  # too many failures: caller falls back to the master password
            self.done(2)
            return
        self.error.setText("That PIN is not right. Try again.")
        self.error.show()


class PasswordPromptDialog(FaradayDialog):
    """Asks for the master password and verifies it off the GUI thread before closing.

    ``verify(password_bytes, on_result)`` must call ``on_result(bool)`` on the GUI thread.
    """

    def __init__(self, parent, title: str, prompt: str,
                 verify: Callable[[bytes, Callable[[bool], None]], None], confirm_text: str = "Confirm",
                 danger: bool = False):
        super().__init__(parent, title, 420)
        self._verify = verify
        self.password: Optional[bytes] = None
        self.body.addLayout(_heading("shield-alert" if danger else "lock", "danger" if danger else "accent",
                                     title, prompt))
        self.edit = SecretLineEdit("Master password", caps_hint=True)
        self.body.addWidget(self.edit)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.hide()
        self.body.addWidget(self.progress)
        self.error = label("", "error")
        self.error.hide()
        self.body.addWidget(self.error)
        self.add_button("Cancel", "ghost", self.reject)
        self.ok = self.add_button(confirm_text, "danger" if danger else "primary", self._submit, default=True)
        self.edit.returnPressed.connect(self._submit)

    def _submit(self):
        text = self.edit.text()
        if not text:
            return
        candidate = text.encode("utf-8")
        self.ok.setEnabled(False)
        self.edit.setEnabled(False)
        self.progress.show()
        self.error.hide()

        def result(ok):
            if not alive(self):
                return
            self.progress.hide()
            self.ok.setEnabled(True)
            self.edit.setEnabled(True)
            if ok:
                self.password = candidate
                self.accept()
            else:
                self.edit.clear()
                self.edit.setFocus()
                self.error.setText("That is not the master password for this vault.")
                self.error.show()
        self._verify(candidate, result)


class SetPinDialog(FaradayDialog):
    def __init__(self, parent, intro: str = ""):
        super().__init__(parent, "Set an action PIN", 420)
        self.pin: Optional[str] = None
        self.body.addLayout(_heading(
            "lock", "accent", "Set an action PIN",
            intro or "A short PIN guards revealing and copying secrets, editing and deleting. "
                     "It is a convenience lock, not a replacement for your master password."))
        self.first = QLineEdit()
        self.second = QLineEdit()
        for edit, ph in ((self.first, "New PIN (4 or more digits)"), (self.second, "Repeat PIN")):
            edit.setEchoMode(QLineEdit.Password)
            edit.setPlaceholderText(ph)
            edit.setMaxLength(16)
            edit.setProperty("mono", "true")
            self.body.addWidget(edit)
        self.error = label("", "error")
        self.error.hide()
        self.body.addWidget(self.error)
        self.add_button("Cancel", "ghost", self.reject)
        self.add_button("Save PIN", "primary", self._submit, default=True)
        self.second.returnPressed.connect(self._submit)

    def _submit(self):
        a, b = self.first.text().strip(), self.second.text().strip()
        ok, problem = pin_store.validate_pin_format(a)
        if not ok:
            self.error.setText(problem)
        elif a != b:
            self.error.setText("The two PINs do not match.")
        else:
            self.pin = a
            self.accept()
            return
        self.error.show()


class BusyDialog(FaradayDialog):
    """Non-closable progress note for longer operations (key derivation, backups)."""

    closes_on_lock = False

    def __init__(self, parent, text: str):
        super().__init__(parent, "Working", 360)
        self.body.addWidget(QLabel(text))
        bar = QProgressBar()
        bar.setRange(0, 0)
        self.body.addWidget(bar)

    def reject(self):  # Esc does nothing; the operation closes it
        pass
