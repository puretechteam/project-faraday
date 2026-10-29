"""
Password and passphrase generator: a reusable panel, the sidebar page that
hosts it, and a dialog for use from the lock screen. Generating is tier 0
(never asks for a PIN); copying uses the clipboard's auto-clear.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QComboBox, QFrame, QGridLayout, QHBoxLayout, QLineEdit, QSlider,
    QSpinBox, QVBoxLayout, QWidget,
)

from ...generator.password import MAX_LENGTH, MIN_LENGTH, PassphraseGenerator, PasswordGenerator
from .. import theme
from ..context import Page, page_layout
from ..widgets.common import Card, StrengthMeter, set_button_icon, alive, button, label
from ..widgets.dialogs import FaradayDialog

DEFAULT_LENGTH = 20
DEFAULT_WORDS = 5
SEPARATORS = (("Hyphen  ( - )", "-"), ("Space", " "), ("Period  ( . )", "."), ("Underscore  ( _ )", "_"))


def _slider_with_spin(low: int, high: int, value: int, on_change):
    """A slider and spin box kept in sync. Returns (layout, slider, spin)."""
    row = QHBoxLayout()
    row.setSpacing(theme.SPACE["md"])
    slider = QSlider(Qt.Horizontal)
    slider.setRange(low, high)
    slider.setValue(value)
    spin = QSpinBox()
    spin.setRange(low, high)
    spin.setValue(value)
    spin.setFixedWidth(72)
    spin.setButtonSymbols(QSpinBox.NoButtons)  # the slider is the stepper
    spin.setAlignment(Qt.AlignCenter)
    slider.valueChanged.connect(spin.setValue)
    spin.valueChanged.connect(slider.setValue)
    spin.valueChanged.connect(lambda _v: on_change())
    row.addWidget(slider, 1)
    row.addWidget(spin)
    return row, slider, spin


def _option_label(text: str):
    lbl = label(text)
    lbl.setMinimumWidth(90)
    return lbl


class GeneratorPanel(QWidget):
    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        col = QVBoxLayout(self)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(theme.SPACE["lg"])

        # Mode switch: two checkable buttons styled as a segmented control
        seg = QFrame()
        seg.setProperty("card", "soft")
        seg_row = QHBoxLayout(seg)
        seg_row.setContentsMargins(4, 4, 4, 4)
        seg_row.setSpacing(4)
        self.mode_password = button("Password", icon_name="key-round")
        self.mode_phrase = button("Passphrase", icon_name="notebook-pen")
        self.modes = QButtonGroup(self)
        for b in (self.mode_password, self.mode_phrase):
            b.setCheckable(True)
            b.setAutoDefault(False)
            self.modes.addButton(b)
            seg_row.addWidget(b)
        self.mode_password.setChecked(True)
        self.modes.buttonToggled.connect(self._mode_changed)
        seg_holder = QHBoxLayout()
        seg_holder.addWidget(seg)
        seg_holder.addStretch(1)
        col.addLayout(seg_holder)

        # Output
        out = Card(margins=18, spacing=12)
        out_row = QHBoxLayout()
        out_row.setSpacing(theme.SPACE["sm"])
        self.output = QLineEdit()
        self.output.setReadOnly(True)
        self.output.setProperty("mono", "true")
        self.output.setAccessibleName("Generated password")
        out_row.addWidget(self.output, 1)
        out.layout_.addLayout(out_row)
        self.meter = StrengthMeter()
        out.layout_.addWidget(self.meter)
        self.error = label("", "error", wrap=True)
        self.error.hide()
        out.layout_.addWidget(self.error)
        actions = QHBoxLayout()
        actions.setSpacing(theme.SPACE["sm"])
        actions.addStretch(1)
        actions.addWidget(button("Regenerate", "", "refresh-cw", self.regenerate))
        self.copy_button = button("Copy", "primary", "copy", self.copy)
        actions.addWidget(self.copy_button)
        out.layout_.addLayout(actions)
        col.addWidget(out)

        # Password options
        self.password_opts = Card(margins=18, spacing=12)
        self.password_opts.layout_.addWidget(label("Options", "heading"))
        length_row = QHBoxLayout()
        length_row.addWidget(_option_label("Length"))
        slider_row, self.length_slider, self.length = _slider_with_spin(
            MIN_LENGTH, MAX_LENGTH, DEFAULT_LENGTH, self.regenerate)
        length_row.addLayout(slider_row, 1)
        self.password_opts.layout_.addLayout(length_row)
        grid = QGridLayout()
        grid.setHorizontalSpacing(theme.SPACE["xl"])
        grid.setVerticalSpacing(theme.SPACE["sm"])
        self.lower = QCheckBox("Lowercase (a-z)")
        self.upper = QCheckBox("Uppercase (A-Z)")
        self.digits = QCheckBox("Digits (0-9)")
        self.symbols = QCheckBox("Symbols (!@#$%)")
        self.classes = (self.lower, self.upper, self.digits, self.symbols)
        for i, box in enumerate(self.classes):
            box.setChecked(True)
            box.toggled.connect(lambda checked, b=box: self._class_toggled(b, checked))
            grid.addWidget(box, i // 2, i % 2)
        grid.setColumnStretch(2, 1)
        self.password_opts.layout_.addLayout(grid)
        self.ambiguous = QCheckBox("Avoid look-alike characters (I, l, 1, O, 0, o)")
        self.ambiguous.toggled.connect(lambda _c: self.regenerate())
        self.password_opts.layout_.addWidget(self.ambiguous)
        col.addWidget(self.password_opts)

        # Passphrase options
        self.phrase_opts = Card(margins=18, spacing=12)
        self.phrase_opts.layout_.addWidget(label("Options", "heading"))
        words_row = QHBoxLayout()
        words_row.addWidget(_option_label("Words"))
        slider_row, self.words_slider, self.words = _slider_with_spin(
            PassphraseGenerator.MIN_WORDS, PassphraseGenerator.MAX_WORDS, DEFAULT_WORDS, self.regenerate)
        words_row.addLayout(slider_row, 1)
        self.phrase_opts.layout_.addLayout(words_row)
        sep_row = QHBoxLayout()
        sep_row.addWidget(_option_label("Separator"))
        self.separator = QComboBox()
        for text, value in SEPARATORS:
            self.separator.addItem(text, value)
        self.separator.setMinimumWidth(180)
        self.separator.currentIndexChanged.connect(lambda _i: self.regenerate())
        sep_row.addWidget(self.separator)
        sep_row.addStretch(1)
        self.phrase_opts.layout_.addLayout(sep_row)
        self.capitalize = QCheckBox("Capitalize words")
        self.capitalize.setChecked(True)
        self.add_number = QCheckBox("Add a number")
        self.add_number.setChecked(True)
        for box in (self.capitalize, self.add_number):
            box.toggled.connect(lambda _c: self.regenerate())
            self.phrase_opts.layout_.addWidget(box)
        self.phrase_opts.layout_.addWidget(label(
            "Words come from the EFF large wordlist (7,776 words). Passphrases are easier to type "
            "and remember than random characters of the same strength.", "small", wrap=True))
        col.addWidget(self.phrase_opts)
        self.phrase_opts.hide()

        self._style_modes()
        self._style_output()
        theme.bus.theme_changed.connect(lambda: alive(self) and self._style_output())
        self.regenerate()

    # ---------------------------------------------------------------- state

    @property
    def passphrase_mode(self) -> bool:
        return self.mode_phrase.isChecked()

    def _style_output(self):
        self.output.setStyleSheet(
            f"QLineEdit {{ font-size: {theme.font_px(21)}px; padding: 12px 14px; }}")

    def _style_modes(self):
        for b in (self.mode_password, self.mode_phrase):
            b.setProperty("variant", "primary" if b.isChecked() else "ghost")
            theme.repolish(b)
            set_button_icon(b)  # icon colour follows the variant

    def _mode_changed(self, _button, checked):
        if not checked:
            return
        self._style_modes()
        self.password_opts.setVisible(not self.passphrase_mode)
        self.phrase_opts.setVisible(self.passphrase_mode)
        self.output.setAccessibleName("Generated passphrase" if self.passphrase_mode else "Generated password")
        self.regenerate()

    def _class_toggled(self, box, checked):
        # Keep at least one character class on: an empty set cannot generate anything.
        if not checked and not any(b.isChecked() for b in self.classes):
            box.blockSignals(True)
            box.setChecked(True)
            box.blockSignals(False)
            return
        self.regenerate()

    def _generator(self):
        if self.passphrase_mode:
            return PassphraseGenerator(
                words=self.words.value(), separator=self.separator.currentData(),
                capitalize=self.capitalize.isChecked(), add_number=self.add_number.isChecked())
        return PasswordGenerator(
            length=self.length.value(), use_lowercase=self.lower.isChecked(),
            use_uppercase=self.upper.isChecked(), use_digits=self.digits.isChecked(),
            use_symbols=self.symbols.isChecked(), exclude_ambiguous=self.ambiguous.isChecked())

    # ---------------------------------------------------------------- actions

    def regenerate(self):
        try:
            generator = self._generator()
            text = generator.generate()
        except ValueError as exc:
            self.error.setText(str(exc))
            self.error.show()
            self.output.clear()
            self.meter.update_for("")
            self.copy_button.setEnabled(False)
            return
        self.error.hide()
        self.copy_button.setEnabled(True)
        self.output.setText(text)
        self.output.setCursorPosition(0)
        self.meter.update_for(text, generator.entropy_bits)

    def copy(self):
        text = self.output.text()
        if not text:
            return
        what = "Passphrase copied" if self.passphrase_mode else "Password copied"
        self.ctx.clipboard.copy(text, what, secret=True)  # the main window toasts the countdown


class GeneratorPage(Page):
    key = "generator"
    title = "Generator"
    icon = "wand-sparkles"
    needs_vault = False

    def __init__(self, ctx, parent=None):
        super().__init__(ctx, parent)
        content = QWidget()
        col = QVBoxLayout(content)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(theme.SPACE["xl"])
        head = QVBoxLayout()
        head.setSpacing(4)
        head.addWidget(label("Generator", "title"))
        head.addWidget(label("Make a strong random password or an easy to type passphrase. "
                             "Nothing is saved until you paste it somewhere.", "muted", wrap=True))
        col.addLayout(head)
        self.panel = GeneratorPanel(ctx)
        col.addWidget(self.panel)
        col.addStretch(1)
        page_layout(self, content, max_width=760)

    def on_show(self, entry_id=None):
        self.panel.regenerate()


class GeneratorDialog(FaradayDialog):
    """The generator in a dialog, for use from the lock screen."""

    def __init__(self, parent, ctx):
        super().__init__(parent, "Password generator", 600)
        self.panel = GeneratorPanel(ctx, self)
        self.body.addWidget(self.panel)
        self.add_button("Close", "", self.accept)
