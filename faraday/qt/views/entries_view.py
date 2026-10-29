"""
Entries: one list + detail view for every type (and "All items"), built from
faraday.models.schema. Secret values are only placed in a widget while
revealed, and are fetched from the vault at the moment they are copied.
"""

import os
from datetime import datetime, timezone
from typing import List, Optional

from PySide6.QtCore import QAbstractListModel, QModelIndex, QRect, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QListView,
    QPlainTextEdit, QScrollArea, QSplitter, QStyle, QStyledItemDelegate, QVBoxLayout, QWidget,
)

from ...models import schema
from ...models.schema import REGISTRY, TypeSpec, is_secret, spec_for
from .. import icons, theme
from ..context import Page
from ..services.guard import SENSITIVE
from ..services.vault_service import EntrySummary
from ..widgets.common import (
    Banner, EmptyState, IconLabel, SecretLineEdit, alive, button, divider, icon_button, label,
)
from ..widgets.dialogs import FaradayDialog, confirm, message

MASK = "•" * 12


def local_time(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone()


def relative(dt: Optional[datetime]) -> str:
    dt = local_time(dt)
    if dt is None:
        return ""
    seconds = (datetime.now().astimezone() - dt).total_seconds()
    if seconds < 60:
        return "just now"
    for unit, size in (("minute", 60), ("hour", 3600), ("day", 86400)):
        n = int(seconds // size)
        if seconds < size * (60 if unit == "minute" else 24 if unit == "hour" else 30):
            return f"{n} {unit}{'s' if n != 1 else ''} ago"
    return dt.strftime("%d %b %Y")


def type_icon(type_id: str) -> str:
    spec = REGISTRY.get(type_id)
    return spec.icon if spec else "file-question"


# ---------------------------------------------------------------- list model + delegate

class EntryListModel(QAbstractListModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows: List[EntrySummary] = []

    def set_rows(self, rows: List[EntrySummary]):
        self.beginResetModel()
        self.rows = rows
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        row = self.rows[index.row()]
        if role == Qt.DisplayRole:
            return row.title
        if role == Qt.UserRole:
            return row
        if role == Qt.AccessibleTextRole:
            return f"{row.title}, {row.subtitle}"
        return None

    def row_of(self, entry_id: str) -> int:
        for i, r in enumerate(self.rows):
            if r.entry_id == entry_id:
                return i
        return -1


class EntryDelegate(QStyledItemDelegate):
    HEIGHT = 56

    def __init__(self, show_type: bool, parent=None):
        super().__init__(parent)
        self.show_type = show_type

    def sizeHint(self, option, index):
        return QSize(option.rect.width(), self.HEIGHT)

    def paint(self, painter: QPainter, option, index):
        row: EntrySummary = index.data(Qt.UserRole)
        p = theme.current()
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        rect = option.rect.adjusted(2, 2, -2, -2)
        selected = option.state & QStyle.State_Selected
        hover = option.state & QStyle.State_MouseOver
        if selected or hover:
            path = QPainterPath()
            path.addRoundedRect(rect, 8, 8)
            painter.fillPath(path, QColor(p.accent_soft if selected else p.hover))
        badge = QRect(rect.left() + 10, rect.center().y() - 16, 32, 32)
        bpath = QPainterPath()
        bpath.addRoundedRect(badge, 9, 9)
        painter.fillPath(bpath, QColor(p.surface_alt if selected else p.accent_soft))
        color = p.danger if row.opaque else p.accent
        painter.drawPixmap(badge.left() + 7, badge.top() + 7, icons.pixmap(type_icon(row.type_id), color, 18))
        text_left = badge.right() + 12
        width = rect.right() - text_left - 10
        font = QFont(option.font)
        font.setWeight(QFont.DemiBold)
        painter.setFont(font)
        painter.setPen(QColor(p.text))
        fm = painter.fontMetrics()
        painter.drawText(QRect(text_left, rect.top() + 9, width, fm.height()), Qt.AlignLeft | Qt.AlignVCenter,
                         fm.elidedText(row.title or "Untitled", Qt.ElideRight, width))
        sub = row.subtitle
        if self.show_type:
            spec = REGISTRY.get(row.type_id)
            sub = " · ".join(x for x in ((spec.label if spec else "Unreadable"), sub) if x)
        font.setWeight(QFont.Normal)
        font.setPixelSize(max(10, round(option.font.pixelSize() * 0.88)) if option.font.pixelSize() > 0 else 11)
        painter.setFont(font)
        painter.setPen(QColor(p.text_muted))
        fm = painter.fontMetrics()
        painter.drawText(QRect(text_left, rect.bottom() - 9 - fm.height(), width, fm.height()),
                         Qt.AlignLeft | Qt.AlignVCenter, fm.elidedText(sub, Qt.ElideRight, width))
        painter.restore()


# ---------------------------------------------------------------- detail pane

class FieldRow(QWidget):
    """Label, value and actions for one field. Secrets stay masked until revealed."""

    def __init__(self, view: "EntryDetail", spec: TypeSpec, f: schema.FieldSpec, text: str):
        super().__init__()
        self.view, self.spec, self.f = view, spec, f
        self.secret = is_secret(spec.type_id, f)
        self.multiline = f.kind in (schema.MULTILINE, schema.SECRET_MULTILINE, schema.LINES) or "\n" in text
        col = QVBoxLayout(self)
        col.setContentsMargins(0, 6, 0, 6)
        col.setSpacing(4)
        col.addWidget(label(f.label.upper(), "overline"))
        row = QHBoxLayout()
        row.setSpacing(4)
        self.value = QLabel()
        self.value.setWordWrap(True)
        self.value.setTextInteractionFlags(Qt.TextSelectableByMouse)
        mono = (spec.type_id, f.key) in (("crypto", "address"), ("document", "file_hash"))
        self.value.setProperty("role", "secret" if self.secret else ("mono" if mono else ""))
        row.addWidget(self.value, 1)
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.mask)
        if self.secret:
            self.reveal_btn = icon_button("eye", f"Show {f.label.lower()}", self.toggle_reveal)
            row.addWidget(self.reveal_btn, 0, Qt.AlignTop)
        if f.copyable:
            row.addWidget(icon_button("copy", f"Copy {f.label.lower()}", self.copy), 0, Qt.AlignTop)
        col.addLayout(row)
        if self.secret:
            hint = f.display(text) if f.display else ""
            self.value.setText(f"{MASK}  {hint}".strip() if hint else MASK)
            self._masked_text = self.value.text()
        else:
            self.value.setText(f.display(text) if f.display else text)

    def toggle_reveal(self):
        if self._hide_timer.isActive():
            self.mask()
            return
        if not self.view.ctx.guard.require(SENSITIVE, self, f"show the {self.f.label.lower()}"):
            return
        self.value.setText(self.view.ctx.service.value(self.view.entry_id, self.f.key))
        self.reveal_btn.setToolTip(f"Hide {self.f.label.lower()}")
        from ..widgets.common import set_icon_name
        set_icon_name(self.reveal_btn, "eye-off")
        self._hide_timer.start(int(self.view.ctx.settings.reveal_seconds) * 1000)

    def mask(self):
        self._hide_timer.stop()
        if self.secret and alive(self):
            self.value.setText(self._masked_text)
            from ..widgets.common import set_icon_name
            set_icon_name(self.reveal_btn, "eye")
            self.reveal_btn.setToolTip(f"Show {self.f.label.lower()}")

    def copy(self):
        text = self.view.ctx.service.value(self.view.entry_id, self.f.key)
        if self.secret:
            self.view.ctx.copy_secret(self, text, self.f.label)
        else:
            self.view.ctx.clipboard.copy(text, f"{self.f.label} copied", secret=False)


class CountdownRing(QWidget):
    """Seconds left in the current code period, drawn as a shrinking ring."""

    def __init__(self, period: int, parent=None):
        super().__init__(parent)
        self.period, self.left = period, period
        self.setFixedSize(40, 40)

    def set_left(self, left: int):
        self.left = left
        self.update()

    def paintEvent(self, event):
        from PySide6.QtGui import QPen
        p = theme.current()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.rect().adjusted(4, 4, -4, -4)
        painter.setPen(QPen(QColor(p.border), 3))
        painter.drawEllipse(rect)
        pen = QPen(QColor(p.danger if self.left <= 5 else p.accent), 3)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        painter.drawArc(rect, 90 * 16, int(360 * 16 * self.left / self.period))
        painter.setPen(QColor(p.text_muted))
        font = painter.font()
        font.setPixelSize(theme.font_px(11))
        painter.setFont(font)
        painter.drawText(self.rect(), Qt.AlignCenter, str(self.left))
        painter.end()


class TotpCard(QFrame):
    """Live authenticator code with a countdown, refreshed every second."""

    def __init__(self, view: "EntryDetail", secret: str):
        super().__init__()
        from ... import totp
        self.view = view
        self.setProperty("card", "soft")
        row = QHBoxLayout(self)
        row.setContentsMargins(16, 12, 12, 12)
        row.setSpacing(12)
        try:
            self.params = totp.parse(secret)
        except ValueError as exc:
            self.params = None
            row.addWidget(IconLabel("triangle-alert", 18, "warning"))
            row.addWidget(label(f"No live code: {exc}.", "warning", wrap=True), 1)
            return
        col = QVBoxLayout()
        col.setSpacing(2)
        col.addWidget(label("CURRENT CODE", "overline"))
        self.code = QLabel()
        self.code.setProperty("role", "mono")
        self.code.setStyleSheet(f"font-size: {theme.font_px(28)}px; font-weight: 600;")
        self.code.setTextInteractionFlags(Qt.TextSelectableByMouse)
        col.addWidget(self.code)
        row.addLayout(col, 1)
        self.ring = CountdownRing(self.params.period)
        self.ring.setToolTip("Seconds until the next code")
        row.addWidget(self.ring, 0, Qt.AlignVCenter)
        row.addWidget(button("Copy code", "primary", "copy", self.copy), 0, Qt.AlignVCenter)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(1000)
        self.tick()

    def current(self) -> str:
        from ... import totp
        return totp.code(self.params)

    def tick(self):
        from ... import totp
        value = self.current()
        half = len(value) // 2
        self.code.setText(f"{value[:half]} {value[half:]}")
        self.ring.set_left(totp.seconds_left(self.params))

    def copy(self):
        self.view.ctx.clipboard.copy(self.current(), "Code copied", secret=True)


class EntryDetail(QWidget):
    def __init__(self, ctx, entries_view: "EntriesView"):
        super().__init__()
        self.ctx = ctx
        self.entries_view = entries_view
        self.entry_id: Optional[str] = None
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        outer.addWidget(self.scroll)
        self.clear()

    def clear(self):
        self.entry_id = None
        spec = self.entries_view.spec
        if spec is None:
            empty = EmptyState("layers", "Select an item", "Pick something on the left to see its details.")
        elif not self.entries_view.model.rows:
            action = button(f"Add {spec.label.lower()}" if spec.creatable else "Add document", "primary", "plus",
                            self.entries_view.new_entry)
            empty = EmptyState(spec.icon, f"No {spec.plural.lower()} yet", spec.description, action)
        else:
            empty = EmptyState(spec.icon, f"Select a {spec.label.lower()}", "Its details will appear here.")
        self.scroll.setWidget(empty)

    def show_entry(self, entry_id: str):
        entry = self.ctx.service.entry(entry_id)
        if entry is None:
            self.clear()
            return
        self.entry_id = entry_id
        spec = spec_for(entry)
        body = QWidget()
        col = QVBoxLayout(body)
        col.setContentsMargins(28, 24, 28, 28)
        col.setSpacing(4)

        head = QHBoxLayout()
        head.setSpacing(14)
        badge = QFrame()
        badge.setProperty("banner", "info")
        badge.setFixedSize(48, 48)
        bl = QVBoxLayout(badge)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.addWidget(IconLabel(spec.icon if spec else "file-question", 24, "accent" if spec else "danger"),
                     0, Qt.AlignCenter)
        head.addWidget(badge)
        titles = QVBoxLayout()
        titles.setSpacing(2)
        t = label(schema.entry_title(entry), "title", wrap=True)
        t.setTextInteractionFlags(Qt.TextSelectableByMouse)
        titles.addWidget(t)
        titles.addWidget(label(spec.label if spec else "Unreadable item", "muted"))
        head.addLayout(titles, 1)
        if spec:
            if spec.type_id == "document":
                head.addWidget(button("Export", "", "download", self.export_document), 0, Qt.AlignTop)
            head.addWidget(button("Edit", "", "pencil", self.edit), 0, Qt.AlignTop)
            head.addWidget(icon_button("trash-2", "Delete", self.delete), 0, Qt.AlignTop)
        col.addLayout(head)
        col.addSpacing(14)
        col.addWidget(divider())
        col.addSpacing(8)
        if spec and spec.type_id == "two_factor" and getattr(entry, "totp_secret", ""):
            col.addWidget(TotpCard(self, entry.totp_secret))
            col.addSpacing(8)

        if spec is None:
            col.addWidget(Banner(
                "This item was written by a newer version of Faraday, or some of its fields could not be read. "
                "It is kept exactly as it is and saved back unchanged. Update Faraday to view or edit it.",
                "warning", "triangle-alert"))
        else:
            grid = QGridLayout()
            grid.setHorizontalSpacing(24)
            grid.setVerticalSpacing(2)
            r = c = 0
            for f in spec.visible_fields:
                text = schema.to_text(f, getattr(entry, f.key, None))
                if not text.strip():
                    continue
                row = FieldRow(self, spec, f, text)
                if row.multiline or f.key == "site_note":
                    if c:
                        r, c = r + 1, 0
                    grid.addWidget(row, r, 0, 1, 2)
                    r += 1
                else:
                    grid.addWidget(row, r, c)
                    r, c = (r, 1) if c == 0 else (r + 1, 0)
            col.addLayout(grid)
        col.addSpacing(18)
        created, modified = local_time(entry.created), local_time(entry.modified)
        meta = []
        if created:
            meta.append(f"Created {created:%d %b %Y, %H:%M}")
        if modified:
            meta.append(f"Updated {relative(entry.modified)}")
        col.addWidget(label("   ·   ".join(meta), "small"))
        col.addStretch(1)
        self.scroll.setWidget(body)

    # ---------------------------------------------------------------- actions

    def edit(self):
        entry = self.ctx.service.entry(self.entry_id) if self.entry_id else None
        spec = spec_for(entry) if entry else None
        if not spec or not self.ctx.guard.require(SENSITIVE, self, "edit this item"):
            return
        EntryEditor(self.window(), self.ctx, spec, entry, on_saved=self.entries_view.select).exec()

    def delete(self):
        entry = self.ctx.service.entry(self.entry_id) if self.entry_id else None
        if not entry or not self.ctx.guard.require(SENSITIVE, self, "delete this item"):
            return
        title = schema.entry_title(entry)
        extra = " Its encrypted file is wiped." if entry.get_entry_type() == "document" else \
            " A copy stays in the automatic snapshots until they rotate out."
        if not confirm(self.window(), f"Delete \"{title}\"?", f"This removes it from the vault.{extra}",
                       "Delete", danger=True):
            return
        entry_id = self.entry_id
        view = self.entries_view

        def done(_):
            self.ctx.toast("Deleted")
            if alive(view):
                view.reload()
        self.ctx.service.delete(entry_id, done, lambda e: message(self.window(), "Delete failed", str(e), "error"))

    def export_document(self):
        entry = self.ctx.service.entry(self.entry_id) if self.entry_id else None
        if not entry or not self.ctx.guard.require(SENSITIVE, self, "export this document"):
            return
        dest, _ = QFileDialog.getSaveFileName(self.window(), "Export document",
                                              os.path.join(os.path.expanduser("~"), "Downloads", entry.filename))
        if not dest or not alive(self) or not self.ctx.service.is_unlocked:
            return  # cancelled, or the vault locked while the dialog was open
        self.ctx.service.export_document(
            entry.entry_id, dest,
            lambda _: self.ctx.toast("Document exported and verified"),
            lambda e: message(self.window(), "Export failed", str(e), "error"))


# ---------------------------------------------------------------- editor

class EntryEditor(FaradayDialog):
    def __init__(self, parent, ctx, spec: TypeSpec, existing=None, on_saved=None):
        super().__init__(parent, f"Edit {spec.label.lower()}" if existing else f"New {spec.label.lower()}", 520)
        self.ctx, self.spec, self.existing, self.on_saved = ctx, spec, existing, on_saved
        self._warned = False
        values = spec.values(existing) if existing else {}
        head = QHBoxLayout()
        head.setSpacing(12)
        head.addWidget(IconLabel(spec.icon, 24, "accent"))
        head.addWidget(label(self.windowTitle(), "title"), 1)
        self.body.addLayout(head)
        self.banner = Banner("", "danger", "circle-alert")
        self.banner.hide()
        self.body.addWidget(self.banner)

        form = QWidget()
        fcol = QVBoxLayout(form)
        fcol.setContentsMargins(0, 0, 6, 0)
        fcol.setSpacing(4)
        self.inputs, self.messages = {}, {}
        for f in spec.editable_fields:
            fcol.addWidget(label(f.label.upper() + (" *" if f.required else ""), "overline"))
            widget = self._make_input(f, values.get(f.key, ""))
            self.inputs[f.key] = widget
            fcol.addWidget(widget)
            msg = label("", "error", wrap=True)
            msg.hide()
            self.messages[f.key] = msg
            fcol.addWidget(msg)
            fcol.addSpacing(6)
        fcol.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(form)
        scroll.setMinimumHeight(min(560, 90 + 78 * len(self.inputs)))
        self.body.addWidget(scroll, 1)

        self.add_button("Cancel", "ghost", self.reject)
        self.save_btn = self.add_button("Save", "primary", self._save, default=True)
        first = next(iter(self.inputs.values()), None)
        if first:
            first.setFocus()

    def _make_input(self, f, value: str) -> QWidget:
        if f.kind == schema.SECRET:
            w = SecretLineEdit(f.placeholder, generator=f.generator, meter=f.generator)
            w.setText(value)
            return w
        if f.kind in (schema.MULTILINE, schema.SECRET_MULTILINE, schema.LINES):
            w = QPlainTextEdit(value)
            w.setPlaceholderText(f.placeholder)
            w.setTabChangesFocus(True)
            w.setFixedHeight(150 if f.kind == schema.SECRET_MULTILINE else 84)
            if f.kind != schema.MULTILINE:
                w.setProperty("mono", "true")
            return w
        if f.kind == schema.CHOICE:
            w = QComboBox()
            w.setEditable(True)
            w.addItems(list(f.choices))
            w.setCurrentText(value or (f.choices[0] if f.choices else ""))
            return w
        w = QLineEdit(value)
        w.setPlaceholderText(f.placeholder)
        if f.kind == schema.INT:
            w.setMaximumWidth(140)
        return w

    @staticmethod
    def _read(w) -> str:
        if isinstance(w, SecretLineEdit):
            return w.text()
        if isinstance(w, QPlainTextEdit):
            return w.toPlainText()
        if isinstance(w, QComboBox):
            return w.currentText()
        return w.text()

    def _set_state(self, key: str, text: str, role: str):
        msg = self.messages[key]
        msg.setText(text)
        msg.setProperty("role", role)
        theme.repolish(msg)
        msg.setVisible(bool(text))
        target = self.inputs[key].edit if isinstance(self.inputs[key], SecretLineEdit) else self.inputs[key]
        target.setProperty("invalid", "true" if role == "error" and text else "false")
        theme.repolish(target)

    def _save(self):
        values = {k: self._read(w) for k, w in self.inputs.items()}
        errors, warnings = self.spec.validate(values)
        for key in self.inputs:
            if key in errors:
                self._set_state(key, errors[key], "error")
            elif key in warnings:
                self._set_state(key, warnings[key], "warning")
            else:
                self._set_state(key, "", "error")
        if errors:
            return
        if warnings and not self._warned:
            self._warned = True
            self.save_btn.setText("Save anyway")
            return
        try:
            entry = self.spec.build(values, existing=self.existing)
        except ValueError as exc:
            self.banner.set(str(exc), "danger")
            self.banner.show()
            return
        self.save_btn.setEnabled(False)

        def done(entry_id):
            if alive(self):
                self.accept()
            self.ctx.toast("Saved")
            if self.on_saved:
                self.on_saved(entry_id)

        def failed(exc):
            if not alive(self):
                return
            self.save_btn.setEnabled(True)
            self.banner.set(f"Could not save: {exc}", "danger")
            self.banner.show()
        if self.existing is not None:
            self.ctx.service.update(entry, done, failed)
        else:
            self.ctx.service.add(entry, done, failed)


class DocumentAddDialog(FaradayDialog):
    def __init__(self, parent, ctx, path: str, on_saved=None):
        super().__init__(parent, "Add document", 460)
        self.ctx, self.path, self.on_saved = ctx, path, on_saved
        size = os.path.getsize(path)
        self.body.addWidget(label("Add document", "title"))
        self.body.addWidget(label(f"{os.path.basename(path)}  ({size / 1048576:.2f} MB)", "muted"))
        self.body.addWidget(Banner("The file is encrypted into the vault. The original stays where it is; "
                                   "delete it yourself if it should only exist in Faraday.", "info"))
        self.body.addWidget(label("CATEGORY", "overline"))
        self.category = QComboBox()
        self.category.setEditable(True)
        self.category.addItems(list(schema.DOCUMENT_CATEGORIES))
        self.body.addWidget(self.category)
        self.body.addWidget(label("NOTE", "overline"))
        self.note = QLineEdit()
        self.body.addWidget(self.note)
        self.error = label("", "error", wrap=True)
        self.error.hide()
        self.body.addWidget(self.error)
        self.add_button("Cancel", "ghost", self.reject)
        self.ok = self.add_button("Encrypt and add", "primary", self._save, default=True)

    def _save(self):
        self.ok.setEnabled(False)
        self.ok.setText("Encrypting...")

        def done(entry_id):
            if alive(self):
                self.accept()
            self.ctx.toast("Document added")
            if self.on_saved:
                self.on_saved(entry_id)

        def failed(exc):
            if alive(self):
                self.ok.setEnabled(True)
                self.ok.setText("Encrypt and add")
                self.error.setText(f"Could not add the document: {exc}")
                self.error.show()
        self.ctx.service.add_document(self.path, self.category.currentText().strip() or "General",
                                      self.note.text().strip(), done, failed)


# ---------------------------------------------------------------- page

class EntriesView(Page):
    def __init__(self, ctx, type_id: Optional[str] = None, parent=None):
        super().__init__(ctx, parent)
        self.spec: Optional[TypeSpec] = REGISTRY.get(type_id) if type_id else None
        self.key = type_id or "all"
        self.title = self.spec.plural if self.spec else "All items"
        self.icon = self.spec.icon if self.spec else "layers"

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        split = QSplitter(Qt.Horizontal)
        split.setChildrenCollapsible(False)
        outer.addWidget(split)

        left = QWidget()
        lcol = QVBoxLayout(left)
        lcol.setContentsMargins(20, 20, 12, 16)
        lcol.setSpacing(10)
        head = QHBoxLayout()
        title_col = QVBoxLayout()
        title_col.setSpacing(0)
        title_col.addWidget(label(self.title, "title"))
        self.count = label("", "small")
        title_col.addWidget(self.count)
        head.addLayout(title_col, 1)
        if self.spec is not None:
            text = "Add" if self.spec.creatable else "Add file"
            head.addWidget(button(text, "primary", "plus", self.new_entry,
                                  f"New {self.spec.label.lower()} (Ctrl+N)"), 0, Qt.AlignTop)
        lcol.addLayout(head)
        filters = QHBoxLayout()
        self.filter = QLineEdit()
        self.filter.setPlaceholderText(f"Filter {self.title.lower()}")
        self.filter.setClearButtonEnabled(True)
        self.filter.addAction(icons.icon("search", theme.current().text_muted, 16), QLineEdit.LeadingPosition)
        self.filter.textChanged.connect(self._apply_filter)
        filters.addWidget(self.filter, 1)
        self.type_combo = None
        if self.spec is None:
            self.type_combo = QComboBox()
            self.type_combo.addItem("All types", None)
            for t in REGISTRY.values():
                self.type_combo.addItem(icons.icon(t.icon, size=16), t.plural, t.type_id)
            self.type_combo.currentIndexChanged.connect(self._apply_filter)
            filters.addWidget(self.type_combo)
        lcol.addLayout(filters)

        self.model = EntryListModel(self)
        self.list = QListView()
        self.list.setModel(self.model)
        self.list.setItemDelegate(EntryDelegate(show_type=self.spec is None, parent=self.list))
        self.list.setMouseTracking(True)
        self.list.setUniformItemSizes(True)
        self.list.setVerticalScrollMode(QListView.ScrollPerPixel)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list.selectionModel().currentChanged.connect(self._current_changed)
        self.list.activated.connect(lambda idx: self.detail.edit())
        lcol.addWidget(self.list, 1)
        left.setMinimumWidth(280)
        left.setMaximumWidth(460)
        split.addWidget(left)

        self.detail = EntryDetail(ctx, self)
        split.addWidget(self.detail)
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        split.setSizes([340, 700])

        self._all: List[EntrySummary] = []
        ctx.service.entriesChanged.connect(self._on_entries_changed)

    # ---------------------------------------------------------------- data

    def on_show(self, entry_id: Optional[str] = None):
        self.reload(select=entry_id)
        self.list.setFocus()

    def _on_entries_changed(self):
        if alive(self) and self.isVisible():
            self.reload()

    def reload(self, select: Optional[str] = None):
        if not self.ctx.service.is_unlocked:
            return
        current = select or self.detail.entry_id
        self._all = self.ctx.service.summaries(self.spec.type_id if self.spec else None)
        self._apply_filter(select=current)

    def _apply_filter(self, *_, select: Optional[str] = None):
        select = select or self.detail.entry_id
        needle = self.filter.text().strip().lower()
        type_filter = self.type_combo.currentData() if self.type_combo else None
        rows = [r for r in self._all
                if (not needle or needle in r.search_text) and (not type_filter or r.type_id == type_filter)]
        self.model.set_rows(rows)
        total = len(self._all)
        self.count.setText(f"{len(rows)} of {total}" if len(rows) != total else
                           f"{total} item{'s' if total != 1 else ''}")
        row = self.model.row_of(select) if select else -1
        if row >= 0:
            self.list.setCurrentIndex(self.model.index(row))
            self.detail.show_entry(select)
        else:
            self.detail.clear()

    def _current_changed(self, current, _previous):
        row = current.data(Qt.UserRole) if current.isValid() else None
        if row:
            self.detail.show_entry(row.entry_id)

    def select(self, entry_id: str):
        if self.filter.text() and self.model.row_of(entry_id) < 0:
            self.filter.clear()
        self.reload(select=entry_id)

    # ---------------------------------------------------------------- commands (also used by shortcuts)

    def new_entry(self):
        if self.spec is None:
            return
        if not self.spec.creatable:
            path, _ = QFileDialog.getOpenFileName(self.window(), "Choose a file to encrypt", os.path.expanduser("~"))
            if not path or not alive(self) or not self.ctx.service.is_unlocked:
                return  # cancelled, or the vault locked while the dialog was open
            if os.path.getsize(path) > schema.MAX_DOCUMENT_BYTES:
                message(self.window(), "File too large", "Documents can be up to 100 MB.", "warning")
                return
            DocumentAddDialog(self.window(), self.ctx, path, on_saved=self.select).exec()
            return
        EntryEditor(self.window(), self.ctx, self.spec, on_saved=self.select).exec()

    def edit_selected(self):
        if self.detail.entry_id:
            self.detail.edit()

    def delete_selected(self):
        if self.detail.entry_id:
            self.detail.delete()

    def copy_primary(self):
        entry_id = self.detail.entry_id
        entry = self.ctx.service.entry(entry_id) if entry_id else None
        spec = spec_for(entry) if entry else None
        if not spec:
            return
        if spec.type_id == "two_factor" and getattr(entry, "totp_secret", ""):
            from ... import totp
            try:
                self.ctx.clipboard.copy(totp.code(totp.parse(entry.totp_secret)), "Code copied", secret=True)
                return
            except ValueError:
                pass  # fall back to copying the secret itself
        key = spec.primary_secret or spec.primary_copy
        if not key:
            return
        f = spec.field(key)
        text = self.ctx.service.value(entry_id, key)
        if is_secret(spec.type_id, f):
            self.ctx.copy_secret(self, text, f.label)
        else:
            self.ctx.clipboard.copy(text, f"{f.label} copied", secret=False)
