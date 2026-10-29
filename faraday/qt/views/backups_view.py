"""
Backups: the automatic encrypted snapshots taken before every save, restoring
one (master password every time), and exporting a full verified copy of the
vault with its attachments.
"""

import os
from datetime import datetime, timezone
from functools import partial

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QVBoxLayout, QWidget

from .. import theme
from ..context import Page, page_layout
from ..widgets.common import Banner, Card, EmptyState, IconLabel, alive, button, divider, label
from ..widgets.dialogs import BusyDialog, confirm, message


def _ago(when: datetime) -> str:
    seconds = max(0, (datetime.now(timezone.utc) - when).total_seconds())
    if seconds < 60:
        return "just now"
    for size, unit in ((365 * 86400, "year"), (30 * 86400, "month"), (86400, "day"),
                       (3600, "hour"), (60, "minute")):
        if seconds >= size:
            n = int(seconds // size)
            return f"{n} {unit}{'' if n == 1 else 's'} ago"
    return "just now"


def _size(n: int) -> str:
    value = float(n)
    for unit in ("bytes", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "bytes" else f"{value:.1f} {unit}"
        value /= 1024
    return ""


def _local(when: datetime) -> str:
    return when.astimezone().strftime("%a %d %b %Y, %H:%M:%S")


class BackupsPage(Page):
    key = "backups"
    title = "Backups"
    icon = "archive"
    needs_vault = True

    def __init__(self, ctx, parent=None):
        super().__init__(ctx, parent)
        self._busy = None
        content = QWidget()
        col = QVBoxLayout(content)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(theme.SPACE["xl"])

        head = QVBoxLayout()
        head.setSpacing(4)
        head.addWidget(label("Backups", "title"))
        head.addWidget(label("Faraday keeps an encrypted snapshot before every change.", "muted", wrap=True))
        col.addLayout(head)

        col.addWidget(Banner(
            "Snapshots cover the vault file only, and stay next to it on this PC. "
            "Export a full backup to also copy your document attachments, for example to a USB drive.",
            "info", "info"))

        actions = QHBoxLayout()
        actions.setSpacing(theme.SPACE["sm"])
        self.export_button = button("Export full backup", "primary", "download", self._export)
        actions.addWidget(self.export_button)
        actions.addWidget(button("Open snapshots folder", "", "folder-open", self._open_folder))
        actions.addStretch(1)
        col.addLayout(actions)

        self.card = Card(margins=18, spacing=8)
        head_row = QHBoxLayout()
        head_row.addWidget(label("Automatic snapshots", "heading"))
        head_row.addStretch(1)
        self.count = label("", "small")
        head_row.addWidget(self.count)
        self.card.layout_.addLayout(head_row)
        self.retention = label("", "small", wrap=True)
        self.card.layout_.addWidget(self.retention)
        self.card.layout_.addSpacing(4)
        self.rows = QVBoxLayout()
        self.rows.setSpacing(6)
        self.card.layout_.addLayout(self.rows)
        col.addWidget(self.card)
        col.addStretch(1)
        page_layout(self, content)

    # ---------------------------------------------------------------- refresh

    def on_show(self, entry_id=None):
        while self.rows.count():
            item = self.rows.takeAt(0)
            if item.widget() is not None:
                item.widget().hide()
                item.widget().deleteLater()
        backups = self.ctx.service.backups()
        manager = self.ctx.service.manager
        store = manager.backups if manager else None
        n = len(backups)
        self.count.setText(f"{n} snapshot{'' if n == 1 else 's'}" if n else "")
        if store is not None:
            daily = (f", plus the newest one of each of the last {store.keep_daily} days"
                     if store.keep_daily else "")
            self.retention.setText(f"Faraday keeps the newest {store.keep_recent}{daily}. "
                                   "Older snapshots are removed automatically.")
        if not backups:
            self.rows.addWidget(EmptyState(
                "archive", "No snapshots yet",
                "The first snapshot is taken the next time you add, edit or delete an item."))
            return
        for i, b in enumerate(backups):
            if i:
                self.rows.addWidget(divider())
            self.rows.addWidget(self._row(b, newest=(i == 0)))

    def _row(self, info, newest: bool) -> QWidget:
        w = QWidget()
        line = QHBoxLayout(w)
        line.setContentsMargins(2, 4, 2, 4)
        line.setSpacing(theme.SPACE["md"])
        line.addWidget(IconLabel("archive", 18, "accent" if newest else "text_muted"))
        text = QVBoxLayout()
        text.setSpacing(1)
        text.addWidget(label(_local(info.created)))
        detail = f"{_ago(info.created)}, {_size(info.size)}"
        text.addWidget(label(detail + (", newest" if newest else ""), "small"))
        line.addLayout(text, 1)
        restore = button("Restore", "danger", "rotate-ccw", partial(self._restore, info.path))
        restore.setToolTip("Replace the vault with this snapshot")
        line.addWidget(restore, 0, Qt.AlignVCenter)
        return w

    # ---------------------------------------------------------------- actions

    def _parent(self):
        """Where to show a message once this page may have been destroyed by a lock."""
        return self if alive(self) else self.ctx.window

    def _show_busy(self, text: str):
        self._busy = BusyDialog(self, text)
        self._busy.show()

    def _hide_busy(self):
        if self._busy is not None and alive(self._busy):
            self._busy.accept()
            self._busy.deleteLater()
        self._busy = None

    def _restore(self, path: str):
        if not os.path.exists(path):
            message(self, "Snapshot not found", "That snapshot is no longer on disk.", "error")
            self.on_show()
            return
        password = self.ctx.guard.master_password(self, "restore this backup")
        if not password or not alive(self):
            return
        stamp = os.path.basename(path)
        if not confirm(
                self, "Restore this snapshot?",
                f"The vault will be replaced with {stamp}. The current vault is snapshotted first, "
                "so this can be undone by restoring that snapshot. The vault locks afterwards and "
                "you unlock it again with the password that was in use when this snapshot was taken.",
                "Restore", danger=True):
            return
        self._show_busy("Restoring the snapshot...")

        def done(count):
            self._hide_busy()
            self.ctx.toast(f"Snapshot restored with {count} item{'' if count == 1 else 's'}. Unlock to continue.")

        def failed(exc):
            self._hide_busy()
            parent = self._parent()
            if parent is None:
                return
            message(parent, "Could not restore the snapshot",
                    "Nothing was changed. If you changed your master password after this snapshot "
                    "was taken, it needs the password that was in use then.\n\n"
                    f"Details: {str(exc) or type(exc).__name__}", "error")
        self.ctx.service.restore_backup(path, password, done, failed)

    def _export(self):
        folder = QFileDialog.getExistingDirectory(self, "Choose where to save the backup")
        if not folder or not alive(self):
            return
        self.export_button.setEnabled(False)
        self._show_busy("Copying and verifying your vault and its attachments...")

        def done(result_folder):
            self._hide_busy()
            self.ctx.toast("Full backup exported")
            if alive(self):
                self.export_button.setEnabled(True)
                message(self, "Backup exported",
                        f"Your vault and its attachments were copied and verified in:\n{result_folder}",
                        "success")

        def failed(exc):
            self._hide_busy()
            if alive(self):
                self.export_button.setEnabled(True)
            parent = self._parent()
            if parent is not None:
                message(parent, "Could not export the backup", str(exc) or type(exc).__name__, "error")
        self.ctx.service.export_full_backup(folder, done, failed)

    def _open_folder(self):
        manager = self.ctx.service.manager
        directory = manager.backups.directory if manager and manager.backups else None
        if directory and os.path.isdir(directory):
            QDesktopServices.openUrl(QUrl.fromLocalFile(directory))
        else:
            self.ctx.toast("There are no snapshots yet", "info")
