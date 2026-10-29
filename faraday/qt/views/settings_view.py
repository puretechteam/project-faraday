"""
Settings: security, appearance, behaviour and backup retention. Every change
is saved at once through ``ctx.save_settings()``, which also applies it
app-wide. ``on_show`` re-reads the settings without saving anything.
"""

from typing import Callable, Iterable, Tuple

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QAbstractButton, QButtonGroup, QCheckBox, QComboBox, QDialog, QGridLayout, QHBoxLayout, QPushButton,
    QSlider, QSpinBox, QVBoxLayout, QWidget,
)

from ... import pin as pin_store
from ... import themes
from .. import theme
from ..context import Page, page_layout
from ..services.guard import CRITICAL
from ..services.workers import run_async
from ..widgets.common import Card, IconLabel, alive, button, divider, label
from ..widgets.dialogs import SetPinDialog, message

AUTO_LOCK = ((1, "1 minute"), (2, "2 minutes"), (5, "5 minutes"), (10, "10 minutes"),
             (15, "15 minutes"), (30, "30 minutes"), (60, "1 hour"), (0, "Never"))
CLIPBOARD = ((10, "10 seconds"), (20, "20 seconds"), (30, "30 seconds"), (60, "1 minute"),
             (120, "2 minutes"), (0, "Never"))
REVEAL = ((10, "10 seconds"), (20, "20 seconds"), (30, "30 seconds"), (60, "1 minute"))
PIN_GRACE = ((0, "Ask every time"), (30, "30 seconds"), (60, "1 minute"), (300, "5 minutes"))
BEHAVIOUR = (
    ("minimize_to_tray", "Minimize to the system tray",
     "Keep Faraday running in the notification area when minimized."),
    ("lock_on_minimize", "Lock when minimized", ""),
    ("lock_on_session_lock", "Lock when Windows locks or sleeps", ""),
    ("hide_from_capture", "Hide the window from screenshots and screen sharing",
     "Other apps see a blank window instead of your vault."),
)


# ---------------------------------------------------------------- helpers

class ThemeTile(QAbstractButton):
    """A clickable miniature of the app drawn in one theme's colours."""

    W, H = 128, 96

    def __init__(self, theme_id: str, parent=None):
        super().__init__(parent)
        self.theme_id = theme_id
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(themes.theme_name(theme_id))
        self.setAccessibleName(f"Theme {themes.theme_name(theme_id)}")
        self.setFixedSize(self.W, self.H + 24)

    def sizeHint(self):
        return QSize(self.W, self.H + 24)

    def _draw_preview(self, painter: QPainter, rect: QRectF, theme_id: str):
        pal = theme.build_palette(theme_id)
        clip = QPainterPath()
        clip.addRoundedRect(rect, 9, 9)
        painter.save()
        painter.setClipPath(clip, Qt.IntersectClip)
        painter.fillRect(rect, QColor(pal.bg))
        side = QRectF(rect.left(), rect.top(), rect.width() * 0.3, rect.height())
        painter.fillRect(side, QColor(pal.surface))
        painter.fillRect(QRectF(side.right(), rect.top(), 1, rect.height()), QColor(pal.border))
        for i in range(4):  # nav items
            y = rect.top() + 12 + i * 12
            color = pal.accent if i == 1 else pal.text_muted
            painter.fillRect(QRectF(side.left() + 7, y, side.width() - 16, 4), QColor(color))
        card = QRectF(side.right() + 9, rect.top() + 12, rect.right() - side.right() - 18, rect.height() - 24)
        path = QPainterPath()
        path.addRoundedRect(card, 5, 5)
        painter.fillPath(path, QColor(pal.surface))
        painter.setPen(QPen(QColor(pal.border), 1))
        painter.drawPath(path)
        painter.fillRect(QRectF(card.left() + 8, card.top() + 9, card.width() * 0.6, 5), QColor(pal.text))
        painter.fillRect(QRectF(card.left() + 8, card.top() + 20, card.width() * 0.45, 4), QColor(pal.text_muted))
        pill = QPainterPath()
        pill.addRoundedRect(QRectF(card.left() + 8, card.bottom() - 17, card.width() * 0.42, 10), 4, 4)
        painter.fillPath(pill, QColor(pal.accent))
        painter.restore()

    def paintEvent(self, event):
        current = theme.current()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(2, 2, self.W - 4, self.H - 4)
        if self.theme_id == themes.SYSTEM:  # half light, half dark
            painter.save()
            painter.setClipRect(QRectF(0, 0, self.W / 2, self.H))
            self._draw_preview(painter, rect, "light")
            painter.restore()
            painter.save()
            painter.setClipRect(QRectF(self.W / 2, 0, self.W / 2, self.H))
            self._draw_preview(painter, rect, "dark")
            painter.restore()
        else:
            self._draw_preview(painter, rect, self.theme_id)
        if self.isChecked() or self.underMouse():
            painter.setPen(QPen(QColor(current.accent if self.isChecked() else current.text_muted), 2.5))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(rect.adjusted(-1, -1, 1, 1), 10, 10)
        font = QFont(self.font())
        font.setWeight(QFont.DemiBold if self.isChecked() else QFont.Normal)
        painter.setFont(font)
        painter.setPen(QColor(current.text if self.isChecked() else current.text_muted))
        painter.drawText(QRectF(0, self.H, self.W, 22), Qt.AlignCenter, themes.theme_name(self.theme_id))
        painter.end()

    def enterEvent(self, event):
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.update()
        super().leaveEvent(event)


def _combo(options: Iterable[Tuple[int, str]]) -> QComboBox:
    combo = QComboBox()
    for value, text in options:
        combo.addItem(text, value)
    combo.setMinimumWidth(190)
    return combo


def _select(combo: QComboBox, value: int, unit: str) -> None:
    """Select ``value``; a value from an older settings file that is not listed gets its own item."""
    index = combo.findData(value)
    if index < 0:
        combo.addItem(f"{value} {unit}", value)
        index = combo.count() - 1
    combo.setCurrentIndex(index)


def _row(title: str, description: str, control) -> QWidget:
    """A setting: title and optional description on the left, the control on the right."""
    w = QWidget()
    row = QHBoxLayout(w)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(theme.SPACE["lg"])
    text = QVBoxLayout()
    text.setSpacing(2)
    text.addWidget(label(title))
    if description:
        text.addWidget(label(description, "small", wrap=True))
    row.addLayout(text, 1)
    if isinstance(control, QWidget):
        row.addWidget(control, 0, Qt.AlignVCenter)
    else:
        row.addLayout(control)
    return w


def _section(icon_name: str, title: str, subtitle: str = "") -> Card:
    card = Card(margins=20, spacing=14)
    head = QHBoxLayout()
    head.setSpacing(10)
    head.addWidget(IconLabel(icon_name, 20, "accent"))
    head.addWidget(label(title, "heading"))
    head.addStretch(1)
    card.layout_.addLayout(head)
    if subtitle:
        card.layout_.addWidget(label(subtitle, "small", wrap=True))
    return card


class SettingsPage(Page):
    key = "settings"
    title = "Settings"
    icon = "settings"
    needs_vault = True

    def __init__(self, ctx, parent=None):
        super().__init__(ctx, parent)
        self._loading = False
        content = QWidget()
        col = QVBoxLayout(content)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(theme.SPACE["xl"])
        head = QVBoxLayout()
        head.setSpacing(4)
        head.addWidget(label("Settings", "title"))
        head.addWidget(label("Changes are saved as you make them.", "muted"))
        col.addLayout(head)
        col.addWidget(self._build_security())
        col.addWidget(self._build_appearance())
        col.addWidget(self._build_behaviour())
        col.addWidget(self._build_backups())
        col.addStretch(1)
        page_layout(self, content, max_width=760)
        self.on_show()

    # ---------------------------------------------------------------- sections

    def _build_security(self) -> Card:
        card = _section("shield-check", "Security")
        lay = card.layout_
        self.auto_lock = _combo(AUTO_LOCK)
        self.auto_lock.currentIndexChanged.connect(self._auto_lock_changed)
        lay.addWidget(_row("Auto-lock", "Lock the vault after this long with no keyboard or mouse input.",
                           self.auto_lock))
        lay.addWidget(divider())
        self.clipboard = _combo(CLIPBOARD)
        self.clipboard.currentIndexChanged.connect(
            lambda _i: self._set("clipboard_seconds", self.clipboard.currentData()))
        lay.addWidget(_row("Clear copied secrets", "Empty the clipboard this long after you copy a secret.",
                           self.clipboard))
        lay.addWidget(divider())
        self.reveal = _combo(REVEAL)
        self.reveal.currentIndexChanged.connect(
            lambda _i: self._set("reveal_seconds", self.reveal.currentData()))
        lay.addWidget(_row("Hide revealed secrets", "Mask a revealed secret again after this long.",
                           self.reveal))
        lay.addWidget(divider())

        # Action PIN
        pin_buttons = QHBoxLayout()
        pin_buttons.setSpacing(theme.SPACE["sm"])
        self.set_pin_button = button("Set PIN", "primary", "lock", self._set_pin)
        self.change_pin_button = button("Change PIN", "", "pencil", self._change_pin)
        self.remove_pin_button = button("Remove PIN", "danger", "trash-2", self._remove_pin)
        for b in (self.set_pin_button, self.change_pin_button, self.remove_pin_button):
            pin_buttons.addWidget(b)
        pin_row = QWidget()
        pin_line = QHBoxLayout(pin_row)
        pin_line.setContentsMargins(0, 0, 0, 0)
        pin_line.setSpacing(theme.SPACE["lg"])
        pin_text = QVBoxLayout()
        pin_text.setSpacing(2)
        status = QHBoxLayout()
        status.setSpacing(8)
        status.addWidget(label("Action PIN"))
        self.pin_icon = IconLabel("circle-check", 16, "success")
        status.addWidget(self.pin_icon)
        self.pin_status = label("", "small")
        status.addWidget(self.pin_status)
        status.addStretch(1)
        pin_text.addLayout(status)
        pin_text.addWidget(label("A short PIN asked before revealing, copying, editing or deleting secrets.",
                                 "small", wrap=True))
        pin_line.addLayout(pin_text, 1)
        pin_line.addLayout(pin_buttons)
        lay.addWidget(pin_row)
        lay.addWidget(divider())
        self.pin_grace = _combo(PIN_GRACE)
        self.pin_grace.currentIndexChanged.connect(
            lambda _i: self._set("pin_grace_seconds", self.pin_grace.currentData()))
        lay.addWidget(_row("Remember the PIN for", "After a correct PIN, do not ask again for this long.",
                           self.pin_grace))
        return card

    def _build_appearance(self) -> Card:
        card = _section("sun", "Appearance")
        lay = card.layout_

        lay.addWidget(label("Theme"))
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)
        self.theme_group = QButtonGroup(self)
        self.theme_tiles = {}
        for i, theme_id in enumerate(themes.THEME_IDS):
            tile = ThemeTile(theme_id)
            tile.clicked.connect(lambda _c=False, t=theme_id: self._pick_theme(t))
            self.theme_group.addButton(tile)
            self.theme_tiles[theme_id] = tile
            grid.addWidget(tile, i // 5, i % 5)
        grid.setColumnStretch(5, 1)
        lay.addLayout(grid)
        lay.addWidget(divider())

        swatches = QHBoxLayout()
        swatches.setSpacing(6)
        self.accent_group = QButtonGroup(self)
        self.accent_buttons = {}
        self.theme_accent = QPushButton("Theme")
        self.theme_accent.setCheckable(True)
        self.theme_accent.setCursor(Qt.PointingHandCursor)
        self.theme_accent.setToolTip("Use the theme's own accent colour")
        self.theme_accent.clicked.connect(lambda: self._set("accent", ""))
        self.accent_group.addButton(self.theme_accent)
        swatches.addWidget(self.theme_accent)
        for name, hex_color in theme.ACCENTS:
            b = QPushButton()
            b.setProperty("variant", "swatch")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.setToolTip(name)
            b.setAccessibleName(f"Accent colour {name}")
            b.setStyleSheet(f"background: {hex_color};")
            b.clicked.connect(lambda _c=False, h=hex_color: self._set("accent", h))
            self.accent_group.addButton(b)
            self.accent_buttons[hex_color.upper()] = b
            swatches.addWidget(b)
        accent_row = QVBoxLayout()
        accent_row.setSpacing(10)
        accent_row.addWidget(label("Accent colour"))
        accent_row.addLayout(swatches)
        swatches.addStretch(1)
        lay.addLayout(accent_row)
        lay.addWidget(divider())

        size = QHBoxLayout()
        size.setSpacing(theme.SPACE["md"])
        self.font_slider = QSlider(Qt.Horizontal)
        self.font_slider.setRange(8, 14)  # tenths: 80% .. 140%
        self.font_slider.setPageStep(1)
        self.font_slider.setTracking(False)  # apply once on release, not on every step
        self.font_slider.setFixedWidth(220)
        self.font_value = label("", "small")
        self.font_value.setMinimumWidth(44)
        self.font_slider.sliderMoved.connect(lambda v: self.font_value.setText(f"{v * 10}%"))
        self.font_slider.valueChanged.connect(self._font_changed)
        size.addWidget(self.font_slider)
        size.addWidget(self.font_value)
        lay.addWidget(_row("Text size", "", size))
        return card

    def _build_behaviour(self) -> Card:
        card = _section("monitor", "Behaviour")
        self.behaviour = {}
        for i, (attr, text, description) in enumerate(BEHAVIOUR):
            box = QCheckBox(text)
            box.setCursor(Qt.PointingHandCursor)
            box.toggled.connect(lambda checked, a=attr: self._set(a, bool(checked)))
            self.behaviour[attr] = box
            if i:
                card.layout_.addWidget(divider())
            if description:
                block = QVBoxLayout()
                block.setSpacing(2)
                block.addWidget(box)
                hint = label(description, "small", wrap=True)
                hint.setContentsMargins(26, 0, 0, 0)  # line up under the checkbox text
                block.addWidget(hint)
                card.layout_.addLayout(block)
            else:
                card.layout_.addWidget(box)
        return card

    def _build_backups(self) -> Card:
        card = _section("archive", "Backups",
                        "Faraday keeps an encrypted snapshot of the vault before every change. "
                        "Changes here apply the next time you unlock.")
        self.keep_recent = QSpinBox()
        self.keep_recent.setRange(1, 100)
        self.keep_daily = QSpinBox()
        self.keep_daily.setRange(0, 365)
        for spin, attr, suffix in ((self.keep_recent, "backup_keep_recent", " snapshots"),
                                   (self.keep_daily, "backup_keep_daily", " days")):
            spin.setKeyboardTracking(False)
            spin.setButtonSymbols(QSpinBox.NoButtons)  # type or scroll; the theme draws no spin arrows
            spin.setSuffix(suffix)
            spin.setMinimumWidth(150)
            spin.valueChanged.connect(lambda v, a=attr: self._set(a, int(v)))
        card.layout_.addWidget(_row("Keep the newest", "", self.keep_recent))
        card.layout_.addWidget(divider())
        card.layout_.addWidget(_row("Also keep one per day for", "0 turns daily snapshots off.",
                                    self.keep_daily))
        return card

    def _pick_theme(self, theme_id: str):
        if self._loading:
            return
        self.ctx.settings.theme_colors = {}  # a picked theme shows its own colours
        self._set("theme_mode", theme_id)
        for tile in self.theme_tiles.values():
            tile.update()

    # ---------------------------------------------------------------- load

    def on_show(self, entry_id=None):
        s = self.ctx.settings
        self._loading = True
        try:
            _select(self.auto_lock, int(s.auto_lock_minutes), "minutes")
            _select(self.clipboard, int(s.clipboard_seconds), "seconds")
            _select(self.reveal, int(s.reveal_seconds), "seconds")
            _select(self.pin_grace, int(s.pin_grace_seconds), "seconds")
            tile = self.theme_tiles.get(s.theme_mode) or self.theme_tiles[themes.SYSTEM]
            tile.setChecked(True)
            current = self.theme_accent if not s.accent else self.accent_buttons.get(str(s.accent).upper())
            self.accent_group.setExclusive(False)  # allow "none checked" for a custom accent
            for b in [self.theme_accent, *self.accent_buttons.values()]:
                b.setChecked(b is current)
            self.accent_group.setExclusive(True)
            self.font_slider.setValue(max(8, min(14, round(float(s.font_scale) * 10))))
            self.font_value.setText(f"{self.font_slider.value() * 10}%")
            for attr, box in self.behaviour.items():
                box.setChecked(bool(getattr(s, attr)))
            self.keep_recent.setValue(int(s.backup_keep_recent))
            self.keep_daily.setValue(int(s.backup_keep_daily))
        finally:
            self._loading = False
        self._refresh_pin()

    def _refresh_pin(self):
        enabled = pin_store.pin_enabled()
        self.pin_status.setText("On" if enabled else "Off")
        self.pin_icon.set_icon("circle-check" if enabled else "circle-alert",
                               "success" if enabled else "text_muted")
        self.set_pin_button.setVisible(not enabled)
        self.change_pin_button.setVisible(enabled)
        self.remove_pin_button.setVisible(enabled)
        self.pin_grace.setEnabled(enabled)

    # ---------------------------------------------------------------- save

    def _set(self, attr: str, value) -> None:
        if self._loading or value is None:
            return
        if getattr(self.ctx.settings, attr) == value:
            return
        setattr(self.ctx.settings, attr, value)
        self.ctx.save_settings()

    def _auto_lock_changed(self, _index):
        if self._loading:
            return
        value = self.auto_lock.currentData()
        if value == 0 and self.ctx.settings.auto_lock_minutes != 0:
            if not self.ctx.guard.require(CRITICAL, self, "turn off auto-lock"):
                if alive(self):  # put the old choice back
                    self._loading = True
                    _select(self.auto_lock, int(self.ctx.settings.auto_lock_minutes), "minutes")
                    self._loading = False
                return
        self._set("auto_lock_minutes", value)

    def _font_changed(self, value: int):
        self.font_value.setText(f"{value * 10}%")
        self._set("font_scale", value / 10)

    # ---------------------------------------------------------------- PIN

    def _ask_new_pin(self, done_text: str, intro: str = ""):
        dlg = SetPinDialog(self, intro)
        if dlg.exec() != QDialog.Accepted or not dlg.pin:
            return
        code = dlg.pin
        dlg.pin = None
        self._save_pin(code, done_text)

    def _save_pin(self, code: str, done_text: str):
        """Hash and store the PIN off the GUI thread (Argon2id takes a moment)."""
        for b in (self.set_pin_button, self.change_pin_button):
            b.setEnabled(False)

        def finished(_result=None):
            self.ctx.toast(done_text)
            if alive(self):
                self.set_pin_button.setEnabled(True)
                self.change_pin_button.setEnabled(True)
                self._refresh_pin()

        def failed(exc):
            if alive(self):
                self.set_pin_button.setEnabled(True)
                self.change_pin_button.setEnabled(True)
                message(self, "Could not save the PIN", str(exc), "error")
        run_async(lambda: pin_store.set_pin(code), finished, failed)

    def _set_pin(self):
        self._ask_new_pin("PIN set")

    def _change_pin(self):
        if self.ctx.guard.require(CRITICAL, self, "change the PIN") and alive(self):
            self._ask_new_pin("PIN changed", "Choose a new PIN of 4 or more digits.")

    def _remove_pin(self):
        if not (self.ctx.guard.require(CRITICAL, self, "remove the PIN") and alive(self)):
            return
        try:
            pin_store.disable_pin()
        except OSError as exc:
            message(self, "Could not remove the PIN", str(exc), "error")
            return
        self.ctx.toast("PIN removed")
        self._refresh_pin()
