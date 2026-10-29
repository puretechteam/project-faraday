"""
Overview: item counts per type, recently changed items, a vault health check
and quick actions. Health checks read secrets only to measure them; no secret
value is ever placed in a widget or kept after on_show() returns.
"""

import hashlib
from datetime import date, datetime, timezone
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QVBoxLayout, QWidget

from ...generator.password import estimate_entropy
from ...models.schema import REGISTRY
from .. import theme
from ..context import Page, page_layout
from ..widgets.common import Card, IconLabel, alive, button, divider, label

WEAK_BITS = 50          # below this a password counts as weak in the health check
EXPIRY_WARN_DAYS = 60   # cards expiring within this many days are flagged
RECENT_COUNT = 6
STAT_COLUMNS = 5


# ---------------------------------------------------------------- helpers

def plural(count: int, singular: str, many: Optional[str] = None) -> str:
    return f"{count} {singular if count == 1 else (many or singular + 's')}"


def ago(when: Optional[datetime]) -> str:
    """Relative age of a UTC timestamp (naive values are treated as UTC)."""
    if when is None:
        return ""
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    seconds = max(0, (datetime.now(timezone.utc) - when).total_seconds())
    if seconds < 60:
        return "just now"
    for size, unit in ((365 * 86400, "year"), (30 * 86400, "month"), (86400, "day"),
                       (3600, "hour"), (60, "minute")):
        if seconds >= size:
            return plural(int(seconds // size), unit) + " ago"
    return "just now"


def clear_layout(layout) -> None:
    """Remove and delete everything in a layout."""
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.hide()
            widget.deleteLater()
        elif item.layout() is not None:
            clear_layout(item.layout())


def header(title: str, subtitle: str):
    col = QVBoxLayout()
    col.setSpacing(4)
    col.addWidget(label(title, "title"))
    sub = label(subtitle, "muted", wrap=True)
    col.addWidget(sub)
    return col, sub


class Clickable(QFrame):
    """A frame that acts like a button: click, Enter or Space emits ``activated``."""

    activated = Signal()

    def __init__(self, object_name: str, accessible: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName(object_name)
        self.setAttribute(Qt.WA_Hover)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.TabFocus)
        if accessible:
            self.setAccessibleName(accessible)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.rect().contains(event.position().toPoint()):
            self.activated.emit()
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            self.activated.emit()
            return
        super().keyPressEvent(event)


# ---------------------------------------------------------------- page

class OverviewPage(Page):
    key = "overview"
    title = "Overview"
    icon = "layout-grid"
    needs_vault = True

    def __init__(self, ctx, parent=None):
        super().__init__(ctx, parent)
        content = QWidget()
        col = QVBoxLayout(content)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(theme.SPACE["xl"])

        head, self.subtitle = header("Overview", "")
        col.addLayout(head)

        # Quick actions
        actions = QHBoxLayout()
        actions.setSpacing(theme.SPACE["sm"])
        actions.addWidget(button("New login", "primary", "plus", lambda: self.ctx.navigate("credential")))
        actions.addWidget(button("Generator", "", "wand-sparkles", lambda: self.ctx.navigate("generator")))
        actions.addWidget(button("Export backup", "", "download", lambda: self.ctx.navigate("backups")))
        actions.addStretch(1)
        col.addLayout(actions)

        # Stat cards, one per type
        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(theme.SPACE["md"])
        self.grid.setVerticalSpacing(theme.SPACE["md"])
        for c in range(STAT_COLUMNS):
            self.grid.setColumnStretch(c, 1)
        col.addLayout(self.grid)

        # Recently changed + health, side by side
        lower = QHBoxLayout()
        lower.setSpacing(theme.SPACE["lg"])
        recent = Card(margins=18, spacing=6)
        recent.layout_.addWidget(label("Recently changed", "heading"))
        recent.layout_.addSpacing(4)
        self.recent_rows = QVBoxLayout()
        self.recent_rows.setSpacing(2)
        recent.layout_.addLayout(self.recent_rows)
        recent.layout_.addStretch(1)
        lower.addWidget(recent, 1)

        health = Card(margins=18, spacing=6)
        health.layout_.addWidget(label("Health", "heading"))
        self.health_summary = label("", "small", wrap=True)
        health.layout_.addWidget(self.health_summary)
        health.layout_.addSpacing(4)
        self.health_rows = QVBoxLayout()
        self.health_rows.setSpacing(theme.SPACE["sm"])
        health.layout_.addLayout(self.health_rows)
        health.layout_.addStretch(1)
        lower.addWidget(health, 1)
        col.addLayout(lower)
        col.addStretch(1)

        page_layout(self, content)
        self._apply_local_style()
        theme.bus.theme_changed.connect(lambda: alive(self) and self._apply_local_style())
        self.ctx.service.entriesChanged.connect(self._entries_changed)

    def _apply_local_style(self):
        p = theme.current()
        self.setStyleSheet(
            f"QFrame#StatCard:hover, QFrame#StatCard:focus {{ border: 1px solid {p.accent}; }}"
            f"QFrame#ClickRow {{ border-radius: {theme.RADIUS['sm']}px; background: transparent; }}"
            f"QFrame#ClickRow:hover, QFrame#ClickRow:focus {{ background: {p.hover}; }}"
        )

    def _entries_changed(self):
        if alive(self) and self.isVisible():
            self.on_show()

    # ---------------------------------------------------------------- refresh

    def on_show(self, entry_id=None):
        svc = self.ctx.service
        counts = svc.counts()
        total = sum(counts.values())
        name = svc.vault_name() or "This vault"
        self.subtitle.setText(f"{name} holds {plural(total, 'item')}." if total
                              else f"{name} is empty. Add your first item to get started.")
        self._fill_stats(counts)
        self._fill_recent()
        self._fill_health()

    def _fill_stats(self, counts):
        clear_layout(self.grid)
        for i, (type_id, spec) in enumerate(REGISTRY.items()):
            card = Clickable("StatCard", f"{spec.plural}: {counts.get(type_id, 0)}")
            card.setProperty("card", "true")
            box = QVBoxLayout(card)
            box.setContentsMargins(14, 12, 14, 12)
            box.setSpacing(2)
            top = QHBoxLayout()
            top.addWidget(IconLabel(spec.icon, 20, "accent"))
            top.addStretch(1)
            top.addWidget(IconLabel("chevron-right", 14, "text_muted"))
            box.addLayout(top)
            box.addSpacing(6)
            box.addWidget(label(str(counts.get(type_id, 0)), "title"))
            name = label(spec.plural, "muted")
            name.setToolTip(spec.description)
            name.setMinimumWidth(1)  # let the grid give every column the same width
            box.addWidget(name)
            card.activated.connect(lambda t=type_id: self.ctx.navigate(t))
            self.grid.addWidget(card, i // STAT_COLUMNS, i % STAT_COLUMNS)

    def _fill_recent(self):
        clear_layout(self.recent_rows)
        rows = [r for r in self.ctx.service.summaries() if not r.opaque and r.type_id in REGISTRY]
        epoch = datetime.min
        rows.sort(key=lambda r: (r.modified or epoch), reverse=True)
        if not rows:
            self.recent_rows.addWidget(label("Nothing here yet. Items you add or edit show up here.",
                                             "muted", wrap=True))
            return
        for r in rows[:RECENT_COUNT]:
            spec = REGISTRY[r.type_id]
            row = Clickable("ClickRow", f"{spec.label}: {r.title}")
            line = QHBoxLayout(row)
            line.setContentsMargins(8, 7, 8, 7)
            line.setSpacing(theme.SPACE["md"])
            line.addWidget(IconLabel(spec.icon, 18, "text_muted"))
            text = QVBoxLayout()
            text.setSpacing(0)
            title = label(r.title or spec.label)
            title.setMinimumWidth(10)
            text.addWidget(title)
            if r.subtitle:
                sub = label(r.subtitle, "small")
                sub.setMinimumWidth(10)
                text.addWidget(sub)
            line.addLayout(text, 1)
            line.addWidget(label(ago(r.modified), "small"), 0, Qt.AlignVCenter)
            row.activated.connect(lambda t=r.type_id, e=r.entry_id: self.ctx.navigate(t, e))
            self.recent_rows.addWidget(row)

    # ---------------------------------------------------------------- health

    def _password_health(self):
        """(weak, reused, total) over login and Wi-Fi passwords. Values are measured, never kept."""
        weak = total = 0
        seen = {}
        for type_id in ("credential", "wifi"):
            for entry in self.ctx.service.entries(type_id):
                value = getattr(entry, "password", "") or ""
                if not value:
                    continue
                total += 1
                if estimate_entropy(value) < WEAK_BITS:
                    weak += 1
                digest = hashlib.sha256(value.encode("utf-8")).digest()
                seen[digest] = seen.get(digest, 0) + 1
        reused = sum(n for n in seen.values() if n > 1)
        seen.clear()
        return weak, reused, total

    def _card_health(self):
        """(expired, expiring soon, total). A card is valid through the end of its expiry month."""
        today = date.today()
        expired = expiring = total = 0
        for card in self.ctx.service.entries("card"):
            try:
                month, year = int(card.expiration_month), int(card.expiration_year)
            except (TypeError, ValueError):
                continue
            if not 1 <= month <= 12:
                continue
            total += 1
            first_invalid = date(year + month // 12, month % 12 + 1, 1)
            if today >= first_invalid:
                expired += 1
            elif (first_invalid - today).days <= EXPIRY_WARN_DAYS:
                expiring += 1
        return expired, expiring, total

    def _fill_health(self):
        clear_layout(self.health_rows)
        issues = 0

        weak, reused, pw_total = self._password_health()
        if weak:
            issues += 1
            self._health_row(False, f"{plural(weak, 'weak password')} (under {WEAK_BITS} bits)",
                             "Review", "credential")
        else:
            self._health_row(True, "No weak passwords" if pw_total else "No passwords to check yet")
        if reused:
            issues += 1
            self._health_row(False, f"{plural(reused, 'item')} share a password with another item",
                             "Review", "credential")
        else:
            self._health_row(True, "No reused passwords")

        expired, expiring, card_total = self._card_health()
        if expired or expiring:
            issues += 1
            parts = []
            if expired:
                parts.append(f"{plural(expired, 'card')} expired")
            if expiring:
                parts.append(f"{plural(expiring, 'card')} expiring within {EXPIRY_WARN_DAYS} days")
            self._health_row(False, ", ".join(parts), "View cards", "card")
        else:
            self._health_row(True, "No cards expired or expiring soon" if card_total else "No cards stored")

        backups = self.ctx.service.backups()
        if backups:
            self._health_row(True, f"{plural(len(backups), 'automatic snapshot')}, newest {ago(backups[0].created)}",
                             "Backups", "backups")
        else:
            self._health_row(False, "No snapshots yet. One is taken before every change.",
                             "Backups", "backups")

        self.health_summary.setText("Everything looks good." if not issues
                                    else f"{plural(issues, 'thing')} worth a look.")

    def _health_row(self, ok: bool, text: str, action: Optional[str] = None, target: Optional[str] = None):
        row = QWidget()
        line = QHBoxLayout(row)
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(theme.SPACE["md"])
        line.addWidget(IconLabel("circle-check" if ok else "triangle-alert", 18,
                                 "success" if ok else "warning"), 0, Qt.AlignTop)
        line.addWidget(label(text, wrap=True), 1)
        if action and target:
            b = button(action, "link", on_click=lambda: self.ctx.navigate(target))
            line.addWidget(b, 0, Qt.AlignVCenter)
        if self.health_rows.count():
            self.health_rows.addWidget(divider())
        self.health_rows.addWidget(row)
