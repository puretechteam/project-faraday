"""Small shared widgets: buttons, cards, secret inputs, strength meter, toast, empty state."""

from typing import Callable, Optional

from PySide6.QtCore import QEvent, QPropertyAnimation, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QGuiApplication, QKeyEvent
from PySide6.QtWidgets import (
    QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QLineEdit, QProgressBar, QPushButton,
    QSizePolicy, QToolButton, QVBoxLayout, QWidget,
)

from ...generator.password import PasswordGenerator, estimate_entropy, strength_label
from .. import icons, theme


def alive(obj) -> bool:
    """False once Qt has deleted the C++ side (e.g. a dialog closed by a lock)."""
    try:
        import shiboken6
        return obj is not None and shiboken6.isValid(obj)
    except Exception:
        return obj is not None


def button(text: str, variant: str = "", icon_name: Optional[str] = None,
           on_click: Optional[Callable] = None, tooltip: str = "") -> QPushButton:
    b = QPushButton(text)
    if variant:
        b.setProperty("variant", variant)
    if icon_name:
        b._icon_name = icon_name
        set_button_icon(b)
        theme.bus.theme_changed.connect(lambda b=b: alive(b) and set_button_icon(b))
    if on_click:
        b.clicked.connect(on_click)
    if tooltip:
        b.setToolTip(tooltip)
    b.setCursor(Qt.PointingHandCursor)
    return b


def set_button_icon(b):
    p = theme.current()
    color = p.on_accent if b.property("variant") == "primary" else (
        p.danger if b.property("variant") == "danger" else p.text)
    b.setIcon(icons.icon(b._icon_name, color, 16))
    b.setIconSize(QSize(16, 16))


def icon_button(icon_name: str, tooltip: str, on_click: Optional[Callable] = None,
                checkable: bool = False, size: int = 18) -> QToolButton:
    b = QToolButton()
    b.setProperty("variant", "icon")
    b.setToolTip(tooltip)
    b.setAccessibleName(tooltip)
    b.setCheckable(checkable)
    b.setCursor(Qt.PointingHandCursor)
    b.setIconSize(QSize(size, size))
    b._icon_name = icon_name
    b.setIcon(icons.icon(icon_name, size=size))
    theme.bus.theme_changed.connect(lambda b=b: alive(b) and b.setIcon(icons.icon(b._icon_name, size=size)))
    if on_click:
        b.clicked.connect(on_click)
    return b


def set_icon_name(b, icon_name: str, size: int = 18):
    b._icon_name = icon_name
    b.setIcon(icons.icon(icon_name, size=size))


def label(text: str = "", role: str = "", wrap: bool = False, selectable: bool = False) -> QLabel:
    lbl = QLabel(text)
    if role:
        lbl.setProperty("role", role)
    lbl.setWordWrap(wrap)
    if selectable:
        lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
    return lbl


class IconLabel(QLabel):
    """A themed icon as a label."""

    def __init__(self, icon_name: str, size: int = 20, color_role: str = "text", parent=None):
        super().__init__(parent)
        self._name, self._size, self._role = icon_name, size, color_role
        self.setFixedSize(size, size)
        self._paint()
        theme.bus.theme_changed.connect(lambda: alive(self) and self._paint())

    def set_icon(self, icon_name: str, color_role: Optional[str] = None):
        self._name = icon_name
        if color_role:
            self._role = color_role
        self._paint()

    def _paint(self):
        self.setPixmap(icons.pixmap(self._name, getattr(theme.current(), self._role), self._size))


class Card(QFrame):
    def __init__(self, kind: str = "true", parent=None, margins: int = 16, spacing: int = 10):
        super().__init__(parent)
        self.setProperty("card", kind)
        self.layout_ = QVBoxLayout(self)
        self.layout_.setContentsMargins(margins, margins, margins, margins)
        self.layout_.setSpacing(spacing)


def divider() -> QFrame:
    line = QFrame()
    line.setProperty("divider", "true")
    return line


class Banner(QFrame):
    """A tinted message strip: kind is info, warning or danger."""

    def __init__(self, text: str = "", kind: str = "info", icon_name: str = "info", parent=None):
        super().__init__(parent)
        self.setProperty("banner", kind)
        row = QHBoxLayout(self)
        row.setContentsMargins(12, 10, 12, 10)
        row.setSpacing(10)
        role = {"info": "accent", "warning": "warning", "danger": "danger"}[kind]
        self.icon = IconLabel(icon_name, 18, role)
        self.text = label(text, wrap=True)
        row.addWidget(self.icon, 0, Qt.AlignTop)
        row.addWidget(self.text, 1)

    def set(self, text: str, kind: Optional[str] = None):
        self.text.setText(text)
        if kind:
            self.setProperty("banner", kind)
            self.icon.set_icon(self.icon._name, {"info": "accent", "warning": "warning", "danger": "danger"}[kind])
            theme.repolish(self)


class StrengthMeter(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setTextVisible(False)
        self.text = label("", "small")
        self.text.setMinimumWidth(150)
        row.addWidget(self.bar, 1)
        row.addWidget(self.text)
        self.update_for("")

    def update_for(self, password: str, bits: Optional[float] = None):
        bits = estimate_entropy(password) if bits is None else bits
        self.bar.setValue(min(100, int(bits / 100 * 100)))
        p = theme.current()
        color = p.danger if bits < 40 else p.warning if bits < 60 else p.success
        self.bar.setStyleSheet(f"QProgressBar::chunk {{ background: {color}; border-radius: 3px; }}")
        self.text.setText("" if not password else f"{strength_label(bits)}, about {int(bits)} bits")


class SecretLineEdit(QWidget):
    """Password-style input with a reveal toggle and optional generate button / strength meter."""

    textChanged = Signal(str)
    returnPressed = Signal()

    def __init__(self, placeholder: str = "", generator: bool = False, meter: bool = False,
                 caps_hint: bool = False, parent=None):
        super().__init__(parent)
        col = QVBoxLayout(self)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(6)
        row = QHBoxLayout()
        row.setSpacing(4)
        self.edit = QLineEdit()
        self.edit.setEchoMode(QLineEdit.Password)
        self.edit.setPlaceholderText(placeholder)
        self.edit.setProperty("mono", "true")
        self.edit.textChanged.connect(self._changed)
        self.edit.returnPressed.connect(self.returnPressed)
        row.addWidget(self.edit, 1)
        self.reveal = icon_button("eye", "Show", self._toggle, checkable=True)
        row.addWidget(self.reveal)
        if generator:
            row.addWidget(icon_button("wand-sparkles", "Generate a strong password", self.generate))
        col.addLayout(row)
        self.meter = StrengthMeter() if meter else None
        if self.meter:
            col.addWidget(self.meter)
        self.caps = label("Caps Lock is on", "warning") if caps_hint else None
        if self.caps:
            self.caps.hide()
            col.addWidget(self.caps)
            self.edit.installEventFilter(self)
        self.setFocusProxy(self.edit)

    def _toggle(self, checked: bool):
        self.edit.setEchoMode(QLineEdit.Normal if checked else QLineEdit.Password)
        set_icon_name(self.reveal, "eye-off" if checked else "eye")
        self.reveal.setToolTip("Hide" if checked else "Show")

    def _changed(self, text: str):
        if self.meter:
            self.meter.update_for(text)
        self.textChanged.emit(text)

    def generate(self):
        self.edit.setText(PasswordGenerator(length=20).generate())
        self.reveal.setChecked(True)
        self._toggle(True)

    def eventFilter(self, obj, event):
        if self.caps is not None and event.type() in (QEvent.KeyPress, QEvent.FocusIn, QEvent.KeyRelease):
            self.caps.setVisible(_caps_lock_on())
        return False

    def text(self) -> str:
        return self.edit.text()

    def setText(self, text: str):
        self.edit.setText(text)

    def clear(self):
        self.edit.clear()

    def set_invalid(self, invalid: bool):
        self.edit.setProperty("invalid", "true" if invalid else "false")
        theme.repolish(self.edit)


def _caps_lock_on() -> bool:
    try:
        import ctypes
        return bool(ctypes.windll.user32.GetKeyState(0x14) & 1)
    except Exception:
        return False


class EmptyState(QWidget):
    def __init__(self, icon_name: str, title: str, text: str = "", action: Optional[QPushButton] = None, parent=None):
        super().__init__(parent)
        col = QVBoxLayout(self)
        col.setAlignment(Qt.AlignCenter)
        col.setSpacing(10)
        ic = IconLabel(icon_name, 40, "text_muted")
        col.addWidget(ic, 0, Qt.AlignHCenter)
        t = label(title, "heading")
        t.setAlignment(Qt.AlignCenter)
        col.addWidget(t)
        if text:
            d = label(text, "muted", wrap=True)
            d.setAlignment(Qt.AlignCenter)
            d.setMaximumWidth(360)
            col.addWidget(d, 0, Qt.AlignHCenter)
        if action:
            col.addSpacing(6)
            col.addWidget(action, 0, Qt.AlignHCenter)


class Toast(QFrame):
    """Transient message at the bottom of a window. One at a time; newer replaces older."""

    def __init__(self, host: QWidget):
        super().__init__(host)
        self.setObjectName("Toast")
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        row = QHBoxLayout(self)
        row.setContentsMargins(14, 10, 16, 10)
        row.setSpacing(10)
        self.icon = IconLabel("circle-check", 18, "success")
        self.text = QLabel()
        row.addWidget(self.icon)
        row.addWidget(self.text)
        self._effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._effect)
        self._anim = QPropertyAnimation(self._effect, b"opacity", self)
        self._anim.setDuration(180)
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._fade_out)
        self._tick = QTimer(self)
        self._tick.timeout.connect(self._countdown)
        self._remaining = 0
        self._message = ""
        self.hide()
        host.installEventFilter(self)

    def show_message(self, message: str, kind: str = "success", ms: int = 2600, countdown: int = 0):
        role, name = {"success": ("success", "circle-check"), "error": ("danger", "circle-alert"),
                      "warning": ("warning", "triangle-alert"), "info": ("accent", "info")}[kind]
        self.icon.set_icon(name, role)
        self._message = message
        self._remaining = countdown
        self._tick.stop()
        if countdown:
            self._countdown_text()
            self._tick.start(1000)
            ms = max(ms, 2600)
        else:
            self.text.setText(message)
        self.adjustSize()
        self._place()
        self.show()
        self.raise_()
        self._anim.stop()
        self._anim.setStartValue(self._effect.opacity() if self.isVisible() else 0.0)
        self._anim.setEndValue(1.0)
        self._anim.start()
        self._hide_timer.start(ms)

    def _countdown_text(self):
        self.text.setText(f"{self._message}. Clipboard clears in {self._remaining}s")
        self.adjustSize()
        self._place()

    def _countdown(self):
        self._remaining -= 1
        if self._remaining <= 0 or not self.isVisible():
            self._tick.stop()
            return
        self._countdown_text()

    def _fade_out(self):
        self._tick.stop()
        self._anim.stop()
        self._anim.setStartValue(1.0)
        self._anim.setEndValue(0.0)
        self._anim.finished.connect(self._after_fade)
        self._anim.start()

    def _after_fade(self):
        try:
            self._anim.finished.disconnect(self._after_fade)
        except (RuntimeError, TypeError):
            pass
        if self._effect.opacity() < 0.05:
            self.hide()

    def _place(self):
        host = self.parentWidget()
        self.move((host.width() - self.width()) // 2, host.height() - self.height() - 28)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Resize and self.isVisible():
            self._place()
        return False


def h_row(*widgets, spacing: int = 8, stretch_after: bool = False) -> QHBoxLayout:
    row = QHBoxLayout()
    row.setSpacing(spacing)
    row.setContentsMargins(0, 0, 0, 0)
    for w in widgets:
        if w is None:
            row.addStretch(1)
        elif isinstance(w, int):
            row.addSpacing(w)
        else:
            row.addWidget(w)
    if stretch_after:
        row.addStretch(1)
    return row


def expanding(widget: QWidget) -> QWidget:
    widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
    return widget
