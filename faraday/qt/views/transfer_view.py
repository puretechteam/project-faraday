"""
Import from other password managers or another Faraday vault, and export
everything into one password-protected ``.faraday`` archive.

Faraday deliberately offers no plaintext export.
"""

import os
from typing import Optional

from cryptography.exceptions import InvalidTag
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QFileDialog, QGridLayout, QHBoxLayout, QLabel, QProgressBar, QVBoxLayout, QWidget,
)

from ...models.schema import REGISTRY
from ...transfer import importers
from ...transfer.archive import EXTENSION
from ...vault.security import secure_delete_file
from .. import theme
from ..context import Page, page_layout
from ..services.guard import CRITICAL
from ..services.workers import run_async
from ..widgets.common import Banner, Card, IconLabel, SecretLineEdit, alive, button, label
from ..widgets.dialogs import BusyDialog, FaradayDialog, confirm, message

SOURCES = (
    ("Bitwarden", "Export from Bitwarden as .json or .csv (unencrypted), then import it here."),
    ("KeePass and KeePassXC", "Export as .xml (KeePass 2) or .csv (KeePass, KeePassXC)."),
    ("Faraday", "A .faraday archive, or another .vault file. You will need its password."),
)


class ArchivePasswordDialog(FaradayDialog):
    """Ask for the password of an archive or other vault being imported."""

    def __init__(self, parent, filename: str, error: str = ""):
        super().__init__(parent, "Password needed", 420)
        self.password: Optional[bytes] = None
        self.body.addWidget(label("Password needed", "title"))
        self.body.addWidget(label(f"Enter the password for {filename}.", "muted", wrap=True))
        self.edit = SecretLineEdit("Password", caps_hint=True)
        self.edit.returnPressed.connect(self._ok)
        self.body.addWidget(self.edit)
        if error:
            self.body.addWidget(label(error, "error", wrap=True))
        self.add_button("Cancel", "ghost", self.reject)
        self.add_button("Open", "primary", self._ok, default=True)

    def _ok(self):
        if self.edit.text():
            self.password = self.edit.text().encode("utf-8")
            self.accept()


class ExportPasswordDialog(FaradayDialog):
    def __init__(self, parent):
        super().__init__(parent, "Export encrypted archive", 460)
        self.password: Optional[bytes] = None
        self.body.addWidget(label("Choose an archive password", "title"))
        self.body.addWidget(label(
            "The archive holds every item and document in this vault, encrypted with this password. "
            "It can be different from your master password. Without it the archive cannot be opened.",
            "muted", wrap=True))
        self.pw1 = SecretLineEdit("Archive password", generator=True, meter=True)
        self.pw2 = SecretLineEdit("Repeat archive password")
        self.body.addWidget(self.pw1)
        self.body.addWidget(self.pw2)
        self.error = label("", "error", wrap=True)
        self.error.hide()
        self.body.addWidget(self.error)
        self.add_button("Cancel", "ghost", self.reject)
        self.add_button("Choose where to save", "primary", self._ok, default=True)

    def _ok(self):
        if len(self.pw1.text()) < 8:
            self.error.setText("Use at least 8 characters.")
        elif self.pw1.text() != self.pw2.text():
            self.error.setText("The two passwords do not match.")
        else:
            self.password = self.pw1.text().encode("utf-8")
            self.accept()
            return
        self.error.show()


class ImportPreviewDialog(FaradayDialog):
    def __init__(self, parent, path: str, result: importers.ImportResult):
        super().__init__(parent, "Import preview", 520)
        self.body.addWidget(label("Ready to import", "title"))
        self.body.addWidget(label(f"{os.path.basename(path)}  ·  {importers.FORMATS[result.format]}", "muted"))
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(8)
        for i, (type_id, n) in enumerate(sorted(result.counts().items())):
            spec = REGISTRY.get(type_id)
            grid.addWidget(IconLabel(spec.icon if spec else "file-question", 18, "accent"), i, 0)
            grid.addWidget(QLabel(spec.plural if spec else "Unreadable items"), i, 1)
            count = QLabel(str(n))
            count.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            grid.addWidget(count, i, 2)
        card = Card("soft")
        card.layout_.addLayout(grid)
        if not result.entries:
            card.layout_.addWidget(label("Nothing new to import.", "muted"))
        self.body.addWidget(card)
        if result.duplicates:
            self.body.addWidget(Banner(f"{len(result.duplicates)} item(s) are already in this vault and will be skipped.",
                                       "info"))
        if result.skipped:
            shown = "; ".join(result.skipped[:4]) + ("; ..." if len(result.skipped) > 4 else "")
            self.body.addWidget(Banner(f"{len(result.skipped)} item(s) cannot be imported: {shown}", "warning",
                                       "triangle-alert"))
        self.add_button("Cancel", "ghost", self.reject)
        ok = self.add_button(f"Import {len(result.entries)} item{'s' if len(result.entries) != 1 else ''}",
                             "primary", self.accept, default=True)
        ok.setEnabled(bool(result.entries))


class TransferPage(Page):
    key = "transfer"
    title = "Import and export"
    icon = "upload"

    def __init__(self, ctx, parent=None):
        super().__init__(ctx, parent)
        self._busy: Optional[BusyDialog] = None
        content = QWidget()
        col = QVBoxLayout(content)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(theme.SPACE["xl"])
        head = QVBoxLayout()
        head.setSpacing(4)
        head.addWidget(label("Import and export", "title"))
        head.addWidget(label("Bring passwords in from another manager, or move this whole vault "
                             "somewhere else in one encrypted file.", "muted", wrap=True))
        col.addLayout(head)

        imp = Card(margins=20, spacing=12)
        row = QHBoxLayout()
        row.addWidget(IconLabel("upload", 22, "accent"))
        row.addWidget(label("Import", "heading"), 1)
        row.addWidget(button("Choose a file", "primary", "folder-open", self.start_import))
        imp.layout_.addLayout(row)
        for name, text in SOURCES:
            r = QHBoxLayout()
            r.setSpacing(12)
            n = label(name)
            n.setMinimumWidth(170)
            r.addWidget(n, 0, Qt.AlignTop)
            r.addWidget(label(text, "muted", wrap=True), 1)
            imp.layout_.addLayout(r)
        imp.layout_.addWidget(Banner(
            "Exports from other apps are plain text: anyone who finds the file can read every password. "
            "Faraday offers to securely delete the file after importing it.", "warning", "triangle-alert"))
        col.addWidget(imp)

        exp = Card(margins=20, spacing=12)
        row = QHBoxLayout()
        row.addWidget(IconLabel("download", 22, "accent"))
        row.addWidget(label("Export", "heading"), 1)
        row.addWidget(button("Export encrypted archive", "primary", "lock", self.start_export))
        exp.layout_.addLayout(row)
        exp.layout_.addWidget(label(
            "Creates one .faraday file with every item and document, encrypted with a password you choose "
            "(Argon2id and AES-256-GCM, like the vault itself). Import it into any Faraday vault. "
            "Faraday never writes your secrets to an unencrypted file.", "muted", wrap=True))
        col.addWidget(exp)
        col.addStretch(1)
        page_layout(self, content)

    # ---------------------------------------------------------------- import

    def _show_busy(self, text: str):
        self._busy = BusyDialog(self.window(), text)
        self._busy.show()

    def _hide_busy(self):
        if self._busy is not None and alive(self._busy):
            self._busy.done(0)
        self._busy = None

    def start_import(self):
        path, _ = QFileDialog.getOpenFileName(self.window(), "Import from", os.path.expanduser("~"),
                                              importers.FILE_FILTER)
        if path and alive(self) and self.ctx.service.is_unlocked:
            self._parse(path, None)

    def _parse(self, path: str, password: Optional[bytes], error: str = ""):
        if password is None and os.path.splitext(path)[1].lower() in (EXTENSION, ".vault"):
            if os.path.normcase(os.path.abspath(path)) == os.path.normcase(self.ctx.service.path or ""):
                message(self.window(), "That is this vault", "Choose a different vault or archive to import.", "info")
                return
            dlg = ArchivePasswordDialog(self.window(), os.path.basename(path), error)
            if dlg.exec() != QDialog.Accepted:
                return
            password = dlg.password
        self._show_busy("Reading the file...")
        existing = self.ctx.service.manager.list_entries(include_opaque=True)

        def work():
            result = importers.load(path, password)
            importers.split_duplicates(result, existing)
            return result

        def failed(exc):
            self._hide_busy()
            if not alive(self):
                return
            if isinstance(exc, InvalidTag):
                self._parse(path, None, "That password is not right.")
            elif isinstance(exc, importers.NeedsPassword):
                self._parse(path, None)
            else:
                message(self.window(), "Cannot import this file", str(exc), "error")
        run_async(work, lambda r: self._preview(path, r, password is not None), failed)

    def _preview(self, path: str, result: importers.ImportResult, encrypted: bool):
        self._hide_busy()
        if not alive(self) or not self.ctx.service.is_unlocked:
            return
        if ImportPreviewDialog(self.window(), path, result).exec() != QDialog.Accepted:
            return
        self._show_busy(f"Importing {len(result.entries)} items...")

        def done(count):
            self._hide_busy()
            self.ctx.toast(f"Imported {count} item{'s' if count != 1 else ''}")
            if alive(self) and not encrypted and confirm(
                    self.window(), "Delete the export file?",
                    f"{os.path.basename(path)} holds your passwords in plain text. Securely delete it now? "
                    "It is overwritten before removal, so it cannot be recovered.",
                    "Securely delete", danger=True, cancel_text="Keep it"):
                if secure_delete_file(path):
                    self.ctx.toast("Export file securely deleted")
                else:
                    message(self.window(), "Could not delete the file", path, "warning")

        def failed(exc):
            self._hide_busy()
            message(self.window(), "Import failed", f"Nothing was added. {exc}", "error")
        self.ctx.service.import_entries(result.entries, result.attachments, done, failed)

    # ---------------------------------------------------------------- export

    def start_export(self):
        if not self.ctx.guard.require(CRITICAL, self, "export everything in this vault"):
            return
        dlg = ExportPasswordDialog(self.window())
        if dlg.exec() != QDialog.Accepted:
            return
        stem = os.path.splitext(self.ctx.service.vault_name())[0] or "Faraday"
        path, _ = QFileDialog.getSaveFileName(
            self.window(), "Save encrypted archive", os.path.join(os.path.expanduser("~"), "Documents", f"{stem}{EXTENSION}"),
            f"Faraday archive (*{EXTENSION})", options=QFileDialog.Option.DontConfirmOverwrite)
        if not path or not alive(self) or not self.ctx.service.is_unlocked:
            return
        if not path.lower().endswith(EXTENSION):
            path += EXTENSION
        if os.path.exists(path):
            message(self.window(), "File already exists", "Choose a new file name; Faraday never overwrites files.",
                    "warning")
            return
        self._show_busy("Encrypting the archive...")

        def done(written):
            self._hide_busy()
            self.ctx.toast("Encrypted archive saved")
            message(self.window(), "Archive saved", f"{written}\n\nKeep the archive password somewhere safe.",
                    "success")

        def failed(exc):
            self._hide_busy()
            message(self.window(), "Export failed", str(exc), "error")
        self.ctx.service.export_archive(path, dlg.password, done, failed)

    def on_show(self, entry_id=None):
        pass
