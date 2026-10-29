"""
Access log: sign-ins, locks and other vault events recorded on this PC,
newest first. Failed sign-ins are highlighted. Clearing the log needs the
master password, and the clear itself is recorded so it cannot go unnoticed.
"""

from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QHBoxLayout, QHeaderView, QStackedWidget, QTableWidget,
    QTableWidgetItem, QVBoxLayout,
)

from ... import access_log
from .. import icons, theme
from ..context import Page
from ..services.guard import CRITICAL
from ..widgets.common import EmptyState, alive, button, icon_button, label

COLUMNS = ("When", "Event", "Vault", "Source")
SOURCES = {"gui": "App", "cli": "Command line", "core": "Vault"}
LIMIT = 1000


def _when(ts) -> str:
    try:
        return datetime.fromisoformat(str(ts)).astimezone().strftime("%Y-%m-%d  %H:%M:%S")
    except (TypeError, ValueError):
        return str(ts or "")


class AccessLogPage(Page):
    key = "access_log"
    title = "Access log"
    icon = "history"
    needs_vault = True

    def __init__(self, ctx, parent=None):
        super().__init__(ctx, parent)
        # Full width: the table needs the room, so no centred column here.
        col = QVBoxLayout(self)
        col.setContentsMargins(32, 28, 32, 32)
        col.setSpacing(theme.SPACE["lg"])

        head = QVBoxLayout()
        head.setSpacing(4)
        head.addWidget(label("Access log", "title"))
        head.addWidget(label("Sign-ins, locks and other events recorded on this PC. "
                             "Failed sign-ins are shown in red.", "muted", wrap=True))
        col.addLayout(head)

        controls = QHBoxLayout()
        controls.setSpacing(theme.SPACE["sm"])
        self.only_this = QCheckBox("Only this vault")
        self.only_this.setChecked(True)
        self.only_this.setCursor(Qt.PointingHandCursor)
        self.only_this.toggled.connect(lambda _c: self.on_show())
        controls.addWidget(self.only_this)
        controls.addSpacing(theme.SPACE["md"])
        self.count = label("", "small")
        controls.addWidget(self.count)
        controls.addStretch(1)
        controls.addWidget(icon_button("refresh-cw", "Refresh", lambda: self.on_show()))
        controls.addWidget(button("Clear log", "danger", "trash-2", self._clear))
        col.addLayout(controls)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.setWordWrap(False)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(34)
        self.table.setStyleSheet("QTableView::item { padding: 0 10px; }")
        hdr = self.table.horizontalHeader()
        hdr.setHighlightSections(False)
        hdr.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        hdr.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeToContents)

        self.stack = QStackedWidget()
        self.stack.addWidget(self.table)
        self.empty = EmptyState("history", "No events yet",
                                "Sign-ins, locks and app launches are listed here as they happen.")
        self.stack.addWidget(self.empty)
        col.addWidget(self.stack, 1)

        theme.bus.theme_changed.connect(lambda: alive(self) and self.isVisible() and self.on_show())

    def on_show(self, entry_id=None):
        path = self.ctx.service.path if self.only_this.isChecked() else None
        events = list(reversed(access_log.load_events(vault_path=path, limit=LIMIT)))
        n = len(events)
        self.count.setText(f"{n} event{'' if n == 1 else 's'}" + (" (most recent)" if n >= LIMIT else ""))
        self.stack.setCurrentWidget(self.table if events else self.empty)
        p = theme.current()
        danger = QColor(p.danger)
        fail_icon = icons.icon("circle-alert", p.danger, 16)
        self.table.setRowCount(0)
        self.table.setRowCount(n)
        for row, ev in enumerate(events):
            failed = ev.get("event") == "unlock_failed"
            source = str(ev.get("source") or "")
            cells = (_when(ev.get("ts")), access_log.describe(ev), str(ev.get("vault_name") or ""),
                     SOURCES.get(source, source.title()))
            for c, text in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setToolTip(text if c != 2 else str(ev.get("vault_path") or text))
                if failed:
                    item.setForeground(danger)
                    if c == 1:
                        item.setIcon(fail_icon)
                self.table.setItem(row, c, item)

    def _clear(self):
        if not self.ctx.guard.require(CRITICAL, self, "clear the access log") or not alive(self):
            return
        # Record the clear first; clear() keeps every log_cleared marker.
        access_log.record(access_log.CLEAR_EVENT, vault_path=self.ctx.service.path, source="gui")
        access_log.clear(keep_events=(access_log.CLEAR_EVENT,))
        self.ctx.toast("Access log cleared")
        self.on_show()
