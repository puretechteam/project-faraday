"""
Ctrl+K: jump to any item or run a command.

Enter opens the highlighted result; Shift+Enter copies an item's main secret
(through the PIN guard). Results are ranked by a simple subsequence score.
"""

from dataclasses import dataclass
from typing import Callable, List, Optional

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QDialog, QLineEdit, QListWidget, QListWidgetItem, QVBoxLayout

from ...models.schema import REGISTRY
from .. import icons, theme
from ..widgets.common import label


@dataclass
class Command:
    title: str
    icon: str
    run: Callable[[], None]
    hint: str = ""


def score(query: str, text: str) -> int:
    """Higher is better; 0 means no match. Prefix and word-start matches rank first."""
    q, t = query.lower(), text.lower()
    if not q:
        return 1
    if t.startswith(q):
        return 1000 - len(t)
    if f" {q}" in f" {t}":
        return 800 - len(t)
    if q in t:
        return 600 - len(t)
    i = 0
    for ch in t:
        if i < len(q) and ch == q[i]:
            i += 1
    return 100 - len(t) if i == len(q) else 0


class CommandPalette(QDialog):
    closes_on_lock = True

    def __init__(self, parent, ctx, commands: List[Command], open_entry: Callable[[str, str], None],
                 copy_entry: Callable[[str], None]):
        super().__init__(parent)
        self.ctx, self.commands = ctx, commands
        self.open_entry, self.copy_entry = open_entry, copy_entry
        self.setWindowTitle("Search")
        self.setModal(True)
        self.setMinimumSize(560, 420)
        col = QVBoxLayout(self)
        col.setContentsMargins(14, 14, 14, 10)
        col.setSpacing(8)
        self.edit = QLineEdit()
        self.edit.setObjectName("SearchBox")
        self.edit.setPlaceholderText("Search items and commands")
        self.edit.addAction(icons.icon("search", theme.current().text_muted, 16), QLineEdit.LeadingPosition)
        self.edit.textChanged.connect(self._refresh)
        self.edit.installEventFilter(self)
        col.addWidget(self.edit)
        self.results = QListWidget()
        self.results.setIconSize(QSize(18, 18))
        self.results.itemActivated.connect(lambda item: self._activate(item, copy=False))
        col.addWidget(self.results, 1)
        col.addWidget(label("Enter to open  ·  Shift+Enter to copy the main secret  ·  Esc to close", "small"))
        self._refresh("")

    def showEvent(self, event):
        theme.set_dark_title_bar(self, theme.current().dark)
        super().showEvent(event)

    def _refresh(self, text: str = ""):
        query = self.edit.text().strip()
        scored = []
        for c in self.commands:
            s = score(query, c.title)
            if s:
                scored.append((s + (50 if not query else 0), ("command", c)))
        if self.ctx.service.is_unlocked and query:
            for r in self.ctx.service.summaries():
                s = max(score(query, r.title), score(query, r.subtitle) // 2,
                        300 if query.lower() in r.search_text else 0)
                if s:
                    scored.append((s + 100, ("entry", r)))
        scored.sort(key=lambda x: -x[0])
        self.results.clear()
        for _, (kind, obj) in scored[:60]:
            if kind == "command":
                item = QListWidgetItem(icons.icon(obj.icon, size=18), obj.title + (f"    {obj.hint}" if obj.hint else ""))
            else:
                spec = REGISTRY.get(obj.type_id)
                sub = " · ".join(x for x in ((spec.label if spec else "Unreadable"), obj.subtitle) if x)
                item = QListWidgetItem(icons.icon(spec.icon if spec else "file-question", size=18),
                                       f"{obj.title}    {sub}")
            item.setData(Qt.UserRole, (kind, obj))
            self.results.addItem(item)
        if self.results.count():
            self.results.setCurrentRow(0)

    def eventFilter(self, obj, event):
        from PySide6.QtCore import QEvent
        if obj is self.edit and event.type() == QEvent.KeyPress:
            key = event.key()
            if key in (Qt.Key_Down, Qt.Key_Up):
                row = self.results.currentRow() + (1 if key == Qt.Key_Down else -1)
                self.results.setCurrentRow(max(0, min(self.results.count() - 1, row)))
                return True
            if key in (Qt.Key_Return, Qt.Key_Enter):
                item = self.results.currentItem()
                if item:
                    self._activate(item, copy=bool(event.modifiers() & Qt.ShiftModifier))
                return True
        return False

    def _activate(self, item: QListWidgetItem, copy: bool):
        kind, obj = item.data(Qt.UserRole)
        self.accept()
        if kind == "command":
            obj.run()
        elif copy:
            self.copy_entry(obj.entry_id)
        else:
            self.open_entry(obj.type_id, obj.entry_id)
