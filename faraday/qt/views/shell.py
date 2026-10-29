"""
The unlocked app: sidebar navigation, top bar and the page stack.

The whole shell is destroyed when the vault locks, so no page or widget
outlives the unlocked session.
"""

from typing import Dict, Optional

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QColor, QFont, QKeySequence, QPainter, QPainterPath, QShortcut
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QProgressBar, QPushButton, QStackedWidget,
    QStyle, QStyledItemDelegate, QVBoxLayout, QWidget,
)

from ...models.schema import REGISTRY
from .. import icons, theme
from ..context import Page
from ..widgets.common import alive, button, icon_button, label
from .access_log_view import AccessLogPage
from .about_view import AboutPage
from .backups_view import BackupsPage
from .entries_view import EntriesView
from .generator_view import GeneratorPage
from .overview_view import OverviewPage
from .settings_view import SettingsPage
from .threat_view import ThreatPage
from .transfer_view import TransferPage

TOOL_PAGES = (GeneratorPage, TransferPage, BackupsPage, AccessLogPage, ThreatPage)
FOOT_PAGES = (SettingsPage, AboutPage)
HEADER_ROLE = Qt.UserRole + 1
COUNT_ROLE = Qt.UserRole + 2
ICON_ROLE = Qt.UserRole + 3


class NavDelegate(QStyledItemDelegate):
    def sizeHint(self, option, index):
        return QSize(option.rect.width(), 26 if index.data(HEADER_ROLE) else 31)

    def paint(self, painter: QPainter, option, index):
        p = theme.current()
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        rect = option.rect
        if index.data(HEADER_ROLE):
            font = QFont(option.font)
            font.setPixelSize(max(10, round(theme.font_px(11))))
            font.setWeight(QFont.DemiBold)
            painter.setFont(font)
            painter.setPen(QColor(p.text_muted))
            painter.drawText(rect.adjusted(12, 6, 0, 0), Qt.AlignLeft | Qt.AlignVCenter, index.data(Qt.DisplayRole).upper())
            painter.restore()
            return
        selected = option.state & QStyle.State_Selected
        hover = option.state & QStyle.State_MouseOver
        inner = rect.adjusted(6, 1, -6, -1)
        if selected or hover:
            path = QPainterPath()
            path.addRoundedRect(inner, 8, 8)
            painter.fillPath(path, QColor(p.accent_soft if selected else p.hover))
        color = p.accent if selected else p.text_muted
        painter.drawPixmap(inner.left() + 10, inner.center().y() - 9, icons.pixmap(index.data(ICON_ROLE), color, 18))
        font = QFont(option.font)
        font.setWeight(QFont.DemiBold if selected else QFont.Normal)
        painter.setFont(font)
        painter.setPen(QColor(p.text if selected or hover else p.text_muted))
        text_rect = QRect(inner.left() + 38, inner.top(), inner.width() - 80, inner.height())
        painter.drawText(text_rect, Qt.AlignLeft | Qt.AlignVCenter, index.data(Qt.DisplayRole))
        count = index.data(COUNT_ROLE)
        if count:
            font.setWeight(QFont.Normal)
            font.setPixelSize(theme.font_px(11))
            painter.setFont(font)
            painter.setPen(QColor(p.text_muted))
            painter.drawText(inner.adjusted(0, 0, -12, 0), Qt.AlignRight | Qt.AlignVCenter, str(count))
        painter.restore()


class Shell(QWidget):
    def __init__(self, ctx, open_palette, lock):
        super().__init__()
        self.ctx = ctx
        self.setObjectName("Shell")
        self.pages: Dict[str, Page] = {}
        self._items: Dict[str, QListWidgetItem] = {}
        self._navigating = False
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)

        # ---- sidebar
        side = QFrame()
        side.setObjectName("Sidebar")
        side.setFixedWidth(244)
        scol = QVBoxLayout(side)
        scol.setContentsMargins(10, 16, 10, 8)
        scol.setSpacing(8)
        brand = QHBoxLayout()
        brand.setContentsMargins(8, 0, 0, 0)
        logo = QLabel()
        logo.setPixmap(icons.app_icon().pixmap(30, 30))
        brand.addWidget(logo)
        names = QVBoxLayout()
        names.setSpacing(0)
        names.addWidget(label("Faraday", "heading"))
        self.vault_label = label(ctx.service.vault_name(), "small")
        self.vault_label.setToolTip(ctx.service.path or "")
        names.addWidget(self.vault_label)
        brand.addLayout(names, 1)
        scol.addLayout(brand)
        scol.addSpacing(6)

        self.nav = QListWidget()
        self.nav.setObjectName("Nav")
        self.nav.setItemDelegate(NavDelegate(self.nav))
        self.nav.setMouseTracking(True)
        self.nav.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.nav.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.nav.currentItemChanged.connect(self._nav_changed)
        self._header("Vault")
        self._add("overview", "Overview", "layout-grid")
        self._add("all", "All items", "layers")
        self._header("Categories")
        for spec in REGISTRY.values():
            self._add(spec.type_id, spec.plural, spec.icon)
        self._header("Tools")
        for cls in TOOL_PAGES:
            self._add(cls.key, cls.title, cls.icon)
        scol.addWidget(self.nav, 1)

        foot = QListWidget()
        foot.setObjectName("Nav")
        foot.setItemDelegate(NavDelegate(foot))
        foot.setMouseTracking(True)
        foot.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        for cls in FOOT_PAGES:
            item = QListWidgetItem(cls.title)
            item.setData(Qt.UserRole, cls.key)
            item.setData(ICON_ROLE, cls.icon)
            foot.addItem(item)
            self._items[cls.key] = item
        foot.setFixedHeight(66)
        foot.currentItemChanged.connect(self._nav_changed)
        self.foot = foot
        scol.addWidget(foot)
        row.addWidget(side)

        # ---- main column
        main = QVBoxLayout()
        main.setContentsMargins(0, 0, 0, 0)
        main.setSpacing(0)
        top = QFrame()
        top.setObjectName("TopBar")
        trow = QHBoxLayout(top)
        trow.setContentsMargins(20, 10, 16, 10)
        search = QPushButton("  Search items and commands")
        search.setObjectName("SearchButton")
        search.setIcon(icons.icon("search", theme.current().text_muted, 16))
        search.setCursor(Qt.PointingHandCursor)
        search.setMinimumWidth(320)
        search.setStyleSheet("QPushButton#SearchButton { text-align: left; padding: 8px 12px; border-radius: 9px; }")
        search.clicked.connect(open_palette)
        trow.addWidget(search)
        trow.addWidget(label("Ctrl+K", "small"))
        trow.addStretch(1)
        self.busy = QProgressBar()
        self.busy.setRange(0, 0)
        self.busy.setFixedWidth(90)
        self.busy.hide()
        trow.addWidget(self.busy)
        trow.addWidget(icon_button("wand-sparkles", "Password generator (Ctrl+G)", lambda: self.navigate("generator")))
        trow.addWidget(icon_button("lock", "Lock now (Ctrl+L)", lock))
        main.addWidget(top)
        self.stack = QStackedWidget()
        self.stack.setObjectName("Pages")
        main.addWidget(self.stack, 1)
        row.addLayout(main, 1)

        ctx.service.entriesChanged.connect(self.update_counts)
        ctx.service.busyChanged.connect(lambda b: alive(self) and self.busy.setVisible(b))
        self.update_counts()

        for key, seq in (("Del", self._delete), ("F2", self._edit)):
            sc = QShortcut(QKeySequence(key), self)
            sc.setContext(Qt.WidgetWithChildrenShortcut)
            sc.activated.connect(seq)

    # ---------------------------------------------------------------- nav

    def _header(self, text: str):
        item = QListWidgetItem(text)
        item.setData(HEADER_ROLE, True)
        item.setFlags(Qt.NoItemFlags)
        self.nav.addItem(item)

    def _add(self, key: str, text: str, icon: str):
        item = QListWidgetItem(text)
        item.setData(Qt.UserRole, key)
        item.setData(ICON_ROLE, icon)
        item.setToolTip(text)
        self.nav.addItem(item)
        self._items[key] = item

    def _nav_changed(self, current, _previous):
        # Switching pages can move focus into a nav list that has no current row, and Qt
        # then auto-selects its first row. Acting on that mid-switch left two pages visible.
        if current is None or self._navigating:
            return
        key = current.data(Qt.UserRole)
        if key and (not self.current_page() or self.current_page().key != key):
            self.navigate(key)

    def update_counts(self):
        if not alive(self) or not self.ctx.service.is_unlocked:
            return
        counts = self.ctx.service.counts()
        total = 0
        for type_id, n in counts.items():
            total += n
            if type_id in self._items:
                self._items[type_id].setData(COUNT_ROLE, n)
        self._items["all"].setData(COUNT_ROLE, total)
        self.nav.viewport().update()

    def _make_page(self, key: str) -> Optional[Page]:
        if key == "overview":
            return OverviewPage(self.ctx)
        if key == "all" or key in REGISTRY:
            return EntriesView(self.ctx, None if key == "all" else key)
        for cls in TOOL_PAGES + FOOT_PAGES:
            if cls.key == key:
                return cls(self.ctx)
        return None

    def navigate(self, key: str, entry_id: Optional[str] = None):
        page = self.pages.get(key)
        if page is None:
            page = self._make_page(key)
            if page is None:
                return
            self.pages[key] = page
            self.stack.addWidget(page)
        self._navigating = True
        try:
            self.stack.setCurrentWidget(page)
            item = self._items.get(key)
            for lst in (self.nav, self.foot):
                lst.blockSignals(True)
                if item is not None and item.listWidget() is lst:
                    lst.setCurrentItem(item)
                else:
                    lst.clearSelection()
                    lst.setCurrentItem(None)
                lst.blockSignals(False)
        finally:
            self._navigating = False
        page.on_show(entry_id)

    def current_page(self) -> Optional[Page]:
        return self.stack.currentWidget()

    # ---------------------------------------------------------------- shortcuts routed to the entries view

    def _entries(self) -> Optional[EntriesView]:
        page = self.current_page()
        return page if isinstance(page, EntriesView) else None

    def new_entry(self):
        page = self._entries()
        if page and page.spec:
            page.new_entry()
        elif page is None or page.spec is None:
            self.navigate("credential")
            self._entries().new_entry()

    def _edit(self):
        if self._entries():
            self._entries().edit_selected()

    def _delete(self):
        page = self._entries()
        if page and page.list.hasFocus():
            page.delete_selected()

    def copy_primary(self):
        if self._entries():
            self._entries().copy_primary()

    def focus_filter(self):
        if self._entries():
            self._entries().filter.setFocus()
            self._entries().filter.selectAll()
