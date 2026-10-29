"""
Threat model: this vault's Argon2id settings, an illustrative offline-guessing
table measured on this PC, how strong the stored passwords are (counts only,
never values) and an honest list of what Faraday does and does not protect.
"""

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QAbstractItemView, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QProgressBar, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from ... import threat_model
from ...generator.password import estimate_entropy
from ...vault.crypto import ARGON2_MEMORY_COST, ARGON2_PARALLELISM, ARGON2_TIME_COST
from .. import theme
from ..context import Page, page_layout
from ..services.workers import run_async
from ..widgets.common import Banner, Card, IconLabel, alive, button, label

BUCKETS = (  # (label, lower bound in bits, colour role)
    ("Weak", 0, "danger"),
    ("Fair", 40, "warning"),
    ("Strong", 60, "success"),
    ("Very strong", 80, "accent"),
)
PROTECTS = (
    "Someone copying your vault file: without the master password it is AES-256-GCM ciphertext.",
    "Offline guessing: every guess costs a full Argon2id derivation with this vault's settings.",
    "Shoulder surfing: secrets stay masked until you reveal them, and copied secrets are cleared "
    "from the clipboard.",
)
DOES_NOT = (
    "Malware or a keylogger on this PC while the vault is unlocked.",
    "A weak or reused master password. Argon2id slows guessing, it cannot make a guessable "
    "password safe.",
    "Secrets held in memory while unlocked. Python cannot reliably wipe them, so lock the vault "
    "when you step away.",
)


def _section(icon_name: str, title: str, subtitle: str = "") -> Card:
    card = Card(margins=20, spacing=12)
    head = QHBoxLayout()
    head.setSpacing(10)
    head.addWidget(IconLabel(icon_name, 20, "accent"))
    head.addWidget(label(title, "heading"))
    head.addStretch(1)
    card.layout_.addLayout(head)
    if subtitle:
        card.layout_.addWidget(label(subtitle, "small", wrap=True))
    return card


def _tile(value: str, caption: str) -> QFrame:
    tile = QFrame()
    tile.setProperty("card", "soft")
    box = QVBoxLayout(tile)
    box.setContentsMargins(14, 12, 14, 12)
    box.setSpacing(2)
    box.addWidget(label(value, "heading"))
    box.addWidget(label(caption, "small"))
    return tile


def _bullets(items, icon_name: str, role: str) -> QVBoxLayout:
    col = QVBoxLayout()
    col.setSpacing(10)
    for text in items:
        row = QHBoxLayout()
        row.setSpacing(10)
        row.addWidget(IconLabel(icon_name, 16, role), 0, Qt.AlignTop)
        row.addWidget(label(text, wrap=True), 1)
        col.addLayout(row)
    return col


class ThreatPage(Page):
    key = "threat"
    title = "Threat model"
    icon = "shield-alert"
    needs_vault = True

    def __init__(self, ctx, parent=None):
        super().__init__(ctx, parent)
        self._measuring = False
        content = QWidget()
        col = QVBoxLayout(content)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(theme.SPACE["xl"])

        head = QVBoxLayout()
        head.setSpacing(4)
        head.addWidget(label("Threat model", "title"))
        head.addWidget(label("What stands between your secrets and someone who gets hold of the vault file.",
                             "muted", wrap=True))
        col.addLayout(head)

        # Key derivation settings
        kdf = _section("lock", "This vault's key derivation",
                       "Argon2id turns your master password into the encryption key. Its cost is paid "
                       "once when you unlock, and again for every single guess an attacker makes.")
        self.tiles = QHBoxLayout()
        self.tiles.setSpacing(theme.SPACE["md"])
        kdf.layout_.addLayout(self.tiles)
        col.addWidget(kdf)

        # Offline guessing estimate
        guess = _section("clock", "Offline guessing estimate",
                         "How long it would take to try every possible password of a given strength, "
                         "with this vault's settings. Hover a column heading for what it assumes.")
        measure_row = QHBoxLayout()
        measure_row.setSpacing(theme.SPACE["md"])
        self.measure_button = button("Measure this PC", "primary", "monitor", self._measure)
        measure_row.addWidget(self.measure_button)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setFixedWidth(160)
        self.progress.hide()
        measure_row.addWidget(self.progress)
        self.measure_note = label("Takes a few seconds and uses the same memory as an unlock.", "small",
                                  wrap=True)
        measure_row.addWidget(self.measure_note, 1)
        guess.layout_.addLayout(measure_row)
        self.table = QTableWidget(len(threat_model.ENTROPY_TABLE_BIT_ROWS),
                                  len(threat_model.SCENARIO_MULTIPLIERS))
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.setFocusPolicy(Qt.NoFocus)
        self.table.setWordWrap(True)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.setCornerButtonEnabled(False)
        self.table.setStyleSheet("QTableView::item { padding: 4px 8px; }"
                                 "QTableCornerButton::section { background: transparent; border: none; }")
        self.table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        for c, (name, _mult, description) in enumerate(threat_model.SCENARIO_MULTIPLIERS):
            item = QTableWidgetItem(name)
            item.setToolTip(description)
            self.table.setHorizontalHeaderItem(c, item)
        for r, bits in enumerate(threat_model.ENTROPY_TABLE_BIT_ROWS):
            self.table.setVerticalHeaderItem(r, QTableWidgetItem(f"{bits} bits"))
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.horizontalHeader().setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.hide()
        guess.layout_.addWidget(self.table)
        self.table_hint = label(
            "For scale: a random 16 character password using every character type is about 100 bits, "
            "a 5 word passphrase about 65 bits. Values written as 10^n years are orders of magnitude.",
            "small", wrap=True)
        self.table_hint.hide()
        guess.layout_.addWidget(self.table_hint)
        col.addWidget(guess)

        # Password strength distribution
        dist = _section("key-round", "Your passwords",
                        "Login and Wi-Fi passwords by estimated strength. Only counts are shown.")
        self.buckets = QGridLayout()
        self.buckets.setHorizontalSpacing(theme.SPACE["md"])
        self.buckets.setVerticalSpacing(theme.SPACE["sm"])
        self.bucket_bars = []
        for r, (name, low, _role) in enumerate(BUCKETS):
            high = BUCKETS[r + 1][1] if r + 1 < len(BUCKETS) else None
            span = f"{low} to {high} bits" if high is not None else f"{low}+ bits"
            if low == 0:
                span = f"under {high} bits"
            name_label = label(name)
            name_label.setMinimumWidth(90)
            bar = QProgressBar()
            bar.setTextVisible(False)
            count = label("0", "small")
            count.setMinimumWidth(110)
            self.buckets.addWidget(name_label, r, 0)
            self.buckets.addWidget(bar, r, 1)
            self.buckets.addWidget(count, r, 2)
            self.bucket_bars.append((bar, count, span))
        self.buckets.setColumnStretch(1, 1)
        dist.layout_.addLayout(self.buckets)
        self.dist_note = label("", "small", wrap=True)
        dist.layout_.addWidget(self.dist_note)
        col.addWidget(dist)

        # What Faraday does and does not protect against
        scope = QHBoxLayout()
        scope.setSpacing(theme.SPACE["lg"])
        yes = _section("shield-check", "Faraday protects against")
        yes.layout_.addLayout(_bullets(PROTECTS, "circle-check", "success"))
        yes.layout_.addStretch(1)
        no = _section("triangle-alert", "Faraday cannot protect against")
        no.layout_.addLayout(_bullets(DOES_NOT, "circle-alert", "warning"))
        no.layout_.addStretch(1)
        scope.addWidget(yes, 1)
        scope.addWidget(no, 1)
        col.addLayout(scope)

        col.addWidget(Banner(threat_model.DISCLAIMER, "info", "info"))
        col.addStretch(1)
        page_layout(self, content, max_width=960)
        theme.bus.theme_changed.connect(lambda: alive(self) and self._fill_distribution())

    # ---------------------------------------------------------------- refresh

    def _params(self):
        manager = self.ctx.service.manager
        params = (manager.kdf_params if manager else None) or {}
        return (int(params.get("time_cost", ARGON2_TIME_COST)),
                int(params.get("memory_cost", ARGON2_MEMORY_COST)),
                int(params.get("parallelism", ARGON2_PARALLELISM)))

    def on_show(self, entry_id=None):
        while self.tiles.count():
            item = self.tiles.takeAt(0)
            if item.widget() is not None:
                item.widget().hide()
                item.widget().deleteLater()
        time_cost, memory_kib, parallelism = self._params()
        self.tiles.addWidget(_tile(f"{time_cost} passes", "Time cost"), 1)
        self.tiles.addWidget(_tile(f"{memory_kib / 1024:,.0f} MiB", "Memory per guess"), 1)
        self.tiles.addWidget(_tile(f"{parallelism} lanes", "Parallelism"), 1)
        self._fill_distribution()

    def _fill_distribution(self):
        counts = [0] * len(BUCKETS)
        for type_id in ("credential", "wifi"):
            for entry in self.ctx.service.entries(type_id):
                value = getattr(entry, "password", "") or ""
                if not value:
                    continue
                bits = estimate_entropy(value)
                index = max(i for i, (_n, low, _r) in enumerate(BUCKETS) if bits >= low)
                counts[index] += 1
        total = sum(counts)
        p = theme.current()
        for (bar, count, span), n, (_name, _low, role) in zip(self.bucket_bars, counts, BUCKETS):
            bar.setRange(0, max(1, total))
            bar.setValue(n)
            bar.setStyleSheet(f"QProgressBar::chunk {{ background: {getattr(p, role)}; border-radius: 3px; }}")
            count.setText(f"{n}  ({span})")
        self.dist_note.setText(
            "No login or Wi-Fi passwords yet." if not total else
            f"{total} password{'' if total == 1 else 's'} checked. Strength is estimated from length and "
            "character types, so a password built from a common word scores higher than it deserves.")

    # ---------------------------------------------------------------- benchmark

    def _measure(self):
        if self._measuring:
            return
        self._measuring = True
        self.measure_button.setEnabled(False)
        self.progress.show()
        self.measure_note.setText("Measuring with this vault's Argon2id settings...")
        params = self._params()

        def done(seconds):
            if not alive(self):
                return
            self._measuring = False
            self.measure_button.setEnabled(True)
            self.measure_button.setText("Measure again")
            self.progress.hide()
            self._fill_table(float(seconds))

        def failed(exc):
            if not alive(self):
                return
            self._measuring = False
            self.measure_button.setEnabled(True)
            self.progress.hide()
            self.measure_note.setText(f"Could not measure: {str(exc) or type(exc).__name__}")
        # Global pool, not the vault pool: a benchmark must never queue a save behind it.
        run_async(lambda: threat_model._benchmark_argon2id(*params), done, failed)

    def _fill_table(self, seconds: float):
        rate = 1 / seconds if seconds > 0 else 0
        self.measure_note.setText(
            f"One guess takes about {seconds:.2f} seconds on this PC, about {rate:,.1f} guesses per second.")
        for r, bits in enumerate(threat_model.ENTROPY_TABLE_BIT_ROWS):
            for c, (_name, multiplier, _d) in enumerate(threat_model.SCENARIO_MULTIPLIERS):
                text = threat_model._time_to_exhaust_bits_table_cell(bits, seconds / multiplier)
                item = QTableWidgetItem(text.replace(" (order of magnitude)", ""))
                item.setToolTip(text)
                self.table.setItem(r, c, item)
        self.table.show()
        self.table_hint.show()
        self._fit_table()
        QTimer.singleShot(0, lambda: alive(self) and self._fit_table())  # again once columns have their width

    def _fit_table(self):
        """Size the table to its rows so the page scrolls, not the table."""
        self.table.resizeRowsToContents()
        height = (self.table.horizontalHeader().sizeHint().height() + 2 * self.table.frameWidth() + 8
                  + sum(self.table.rowHeight(r) for r in range(self.table.rowCount())))
        self.table.setFixedHeight(height)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.table.isVisible():
            self._fit_table()
