"""Lock screen: choose a vault, enter the master password; plus the create-vault dialog."""

import os
from typing import Optional

from cryptography.exceptions import InvalidTag
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox, QDialog, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QProgressBar, QVBoxLayout, QWidget,
)

from ... import recent
from ...paths import default_vaults_dir
from ...vault.errors import VaultInUseError
from .. import icons
from ..services.vault_service import KDF_LEVELS
from ..widgets.common import Banner, Card, IconLabel, SecretLineEdit, alive, button, label
from ..widgets.dialogs import FaradayDialog

LOCK_REASONS = {
    "auto_timeout": "Locked after a period of inactivity.",
    "session_lock": "Locked because Windows was locked or went to sleep.",
    "minimized": "Locked when the window was minimized.",
    "restored_backup": "Backup restored. Unlock to continue.",
    "manual": "",
    "switch_vault": "",
}


def describe_open_error(exc: BaseException) -> str:
    if isinstance(exc, InvalidTag):
        return "Wrong password, or the vault file is damaged."
    if isinstance(exc, VaultInUseError):
        return "This vault is open in another Faraday window or the command line. Close it there first."
    if isinstance(exc, FileNotFoundError):
        return "The vault file was not found. It may have been moved or renamed."
    if isinstance(exc, FileExistsError):
        return "A file with that name already exists. Faraday never overwrites an existing file."
    if isinstance(exc, ValueError):
        return f"This file is not a readable Faraday vault ({exc})."
    return f"Could not open the vault: {exc}"


class UnlockView(QWidget):
    open_generator = Signal()

    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.setObjectName("UnlockView")
        outer = QVBoxLayout(self)
        outer.setAlignment(Qt.AlignCenter)

        card = Card(margins=32, spacing=14)
        card.setFixedWidth(440)
        outer.addWidget(card, 0, Qt.AlignCenter)
        col = card.layout_

        logo = QLabel()
        logo.setPixmap(icons.app_icon().pixmap(56, 56))
        col.addWidget(logo, 0, Qt.AlignHCenter)
        title = label("Faraday", "display")
        title.setAlignment(Qt.AlignCenter)
        col.addWidget(title)
        sub = label("Your offline vault, by Pure Tech", "muted")
        sub.setAlignment(Qt.AlignCenter)
        col.addWidget(sub)
        col.addSpacing(6)

        self.banner = Banner("", "info", "lock")
        self.banner.hide()
        col.addWidget(self.banner)

        col.addWidget(label("VAULT", "overline"))
        vault_row = QHBoxLayout()
        vault_row.setSpacing(6)
        self.vault_combo = QComboBox()
        self.vault_combo.setMinimumWidth(0)
        self.vault_combo.currentIndexChanged.connect(lambda *_: self.password.setFocus())
        vault_row.addWidget(self.vault_combo, 1)
        vault_row.addWidget(button("", "ghost", "folder-open", self._browse, "Open another vault file"))
        col.addLayout(vault_row)

        col.addWidget(label("MASTER PASSWORD", "overline"))
        self.password = SecretLineEdit("Master password", caps_hint=True)
        self.password.returnPressed.connect(self._unlock)
        col.addWidget(self.password)

        self.error = label("", "error", wrap=True)
        self.error.hide()
        col.addWidget(self.error)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.hide()
        col.addWidget(self.progress)

        self.unlock_btn = button("Unlock", "primary", "lock-open", self._unlock)
        self.unlock_btn.setMinimumHeight(40)
        col.addWidget(self.unlock_btn)

        links = QHBoxLayout()
        links.addWidget(button("Create a new vault", "link", on_click=self._create))
        links.addStretch(1)
        links.addWidget(button("Password generator", "link", on_click=self.open_generator.emit))
        col.addLayout(links)

        foot = label("Nothing leaves this computer. Faraday works fully offline.", "small")
        foot.setAlignment(Qt.AlignCenter)
        outer.addSpacing(14)
        outer.addWidget(foot, 0, Qt.AlignHCenter)
        self.refresh()

    # ---------------------------------------------------------------- state

    def refresh(self, reason: str = "", select: Optional[str] = None):
        self.vault_combo.clear()
        paths = recent.load_recent()
        default_dir = default_vaults_dir(create=False)
        if default_dir.is_dir():
            for name in sorted(os.listdir(default_dir)):
                p = str(default_dir / name)
                if name.lower().endswith(".vault") and os.path.isfile(p) and \
                        os.path.normcase(p) not in {os.path.normcase(x) for x in paths}:
                    paths.append(p)
        for p in paths:
            self.vault_combo.addItem(icons.icon("vault", size=16), os.path.basename(p), p)
            self.vault_combo.setItemData(self.vault_combo.count() - 1, p, Qt.ToolTipRole)
        if select:
            i = self.vault_combo.findData(select)
            if i >= 0:
                self.vault_combo.setCurrentIndex(i)
        has_vaults = self.vault_combo.count() > 0
        self.vault_combo.setEnabled(has_vaults)
        self.unlock_btn.setEnabled(has_vaults)
        if not has_vaults:
            self.vault_combo.addItem("No vaults yet. Create one below.", None)
        text = LOCK_REASONS.get(reason, "")
        self.banner.setVisible(bool(text))
        if text:
            self.banner.set(text, "info")
        self.password.clear()
        self.error.hide()
        self._set_busy(False)
        self.password.setFocus()

    def _set_busy(self, busy: bool):
        self.progress.setVisible(busy)
        self.unlock_btn.setEnabled(not busy and self.vault_combo.currentData() is not None)
        self.password.setEnabled(not busy)
        self.vault_combo.setEnabled(not busy)
        self.unlock_btn.setText("Deriving key..." if busy else "Unlock")

    def _show_error(self, text: str):
        self.error.setText(text)
        self.error.show()
        self.password.set_invalid(True)

    # ---------------------------------------------------------------- actions

    def _unlock(self):
        path = self.vault_combo.currentData()
        pw = self.password.text()
        if not path or not pw:
            return
        self.error.hide()
        self.password.set_invalid(False)
        self._set_busy(True)

        def failed(exc):
            if not alive(self):
                return
            self._set_busy(False)
            self.password.clear()
            self._show_error(describe_open_error(exc))
            self.password.setFocus()
        self.ctx.service.open(path, pw.encode("utf-8"), on_error=failed)
        self.password.clear()

    def _browse(self):
        start = str(default_vaults_dir(create=False))
        path, _ = QFileDialog.getOpenFileName(self, "Open vault", start, "Faraday vaults (*.vault);;All files (*)")
        if path:
            if self.vault_combo.findData(path) < 0:
                self.vault_combo.insertItem(0, icons.icon("vault", size=16), os.path.basename(path), path)
            self.vault_combo.setEnabled(True)
            self.vault_combo.setCurrentIndex(self.vault_combo.findData(path))
            self.unlock_btn.setEnabled(True)
            self.password.setFocus()

    def _create(self):
        CreateVaultDialog(self, self.ctx).exec()


class CreateVaultDialog(FaradayDialog):
    def __init__(self, parent, ctx):
        super().__init__(parent, "Create a new vault", 480)
        self.ctx = ctx
        self.body.addWidget(label("Create a new vault", "title"))
        self.body.addWidget(label(
            "Choose where to keep it and a master password. There is no way to recover a forgotten "
            "master password, so make it memorable and write it down somewhere safe.", "muted", wrap=True))

        self.body.addWidget(label("FILE", "overline"))
        row = QHBoxLayout()
        self.path_edit = QLineEdit(str(default_vaults_dir(create=False) / "My vault.vault"))
        row.addWidget(self.path_edit, 1)
        row.addWidget(button("Browse", "ghost", "folder-open", self._browse))
        self.body.addLayout(row)

        self.body.addWidget(label("MASTER PASSWORD", "overline"))
        self.pw1 = SecretLineEdit("Master password", meter=True, caps_hint=True)
        self.pw2 = SecretLineEdit("Repeat master password")
        self.body.addWidget(self.pw1)
        self.body.addWidget(self.pw2)

        self.body.addWidget(label("KEY STRENGTH", "overline"))
        self.level = QComboBox()
        for key, (name, desc) in KDF_LEVELS.items():
            self.level.addItem(f"{name}: {desc}", key)
        self.body.addWidget(self.level)

        self.error = label("", "error", wrap=True)
        self.error.hide()
        self.body.addWidget(self.error)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.hide()
        self.body.addWidget(self.progress)
        self.add_button("Cancel", "ghost", self.reject)
        self.create_btn = self.add_button("Create vault", "primary", self._submit, default=True)

    def _browse(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Create vault", self.path_edit.text(), "Faraday vaults (*.vault)",
            options=QFileDialog.Option.DontConfirmOverwrite,
        )
        if path:
            self.path_edit.setText(path if path.lower().endswith(".vault") else path + ".vault")

    def _fail(self, text):
        self.error.setText(text)
        self.error.show()

    def _submit(self):
        path = self.path_edit.text().strip()
        if path and not path.lower().endswith(".vault"):
            path += ".vault"
        pw1, pw2 = self.pw1.text(), self.pw2.text()
        if not path:
            return self._fail("Choose where to save the vault.")
        if os.path.exists(path):
            return self._fail("A file with that name already exists. Faraday never overwrites an existing file.")
        if not os.path.isdir(os.path.dirname(os.path.abspath(path))):
            return self._fail("That folder does not exist.")
        if len(pw1) < 8:
            return self._fail("Use at least 8 characters for the master password.")
        if pw1 != pw2:
            return self._fail("The two passwords do not match.")
        self.error.hide()
        self.progress.show()
        self.create_btn.setEnabled(False)

        def done(_):
            if alive(self):
                self.accept()

        def failed(exc):
            if not alive(self):
                return
            self.progress.hide()
            self.create_btn.setEnabled(True)
            self._fail(describe_open_error(exc))
        self.ctx.service.create(path, pw1.encode("utf-8"), self.level.currentData(), done, failed)
