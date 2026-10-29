"""About: version, what Faraday is, where to find the project, and credits."""

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ... import __version__
from .. import icons, theme
from ..context import Page, page_layout
from ..widgets.common import Card, IconLabel, button, label

GITHUB_URL = "https://github.com/puretechteam/project-faraday"
DISCORD_URL = "https://discord.gg/dRMRGCG9Fk"

DESCRIPTION = (
    "Project Faraday is an offline password vault. Your vault is a single file encrypted with "
    "AES-256-GCM, using a key derived from your master password with Argon2id. There is no account, "
    "no cloud and no telemetry: nothing leaves this PC unless you copy it somewhere yourself."
)

CREDITS = (
    ("Lucide icons", "ISC License"),
    ("EFF Large Wordlist", "CC BY 3.0 US"),
    ("Qt for Python (PySide6)", "LGPL v3"),
    ("argon2-cffi", "MIT License"),
    ("cryptography", "Apache 2.0 or BSD"),
    ("cbor2", "MIT License"),
)


def _open(url: str):
    QDesktopServices.openUrl(QUrl(url))


class AboutPage(Page):
    key = "about"
    title = "About"
    icon = "info"
    needs_vault = False

    def __init__(self, ctx, parent=None):
        super().__init__(ctx, parent)
        content = QWidget()
        col = QVBoxLayout(content)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(theme.SPACE["xl"])

        head = QVBoxLayout()
        head.setSpacing(4)
        head.addWidget(label("About", "title"))
        head.addWidget(label("Version, links and credits.", "muted"))
        col.addLayout(head)

        # Identity card
        hero = Card(margins=24, spacing=14)
        top = QHBoxLayout()
        top.setSpacing(theme.SPACE["lg"])
        logo = QLabel()
        logo.setFixedSize(64, 64)
        logo.setPixmap(icons.app_icon().pixmap(64, 64))
        top.addWidget(logo, 0, Qt.AlignTop)
        names = QVBoxLayout()
        names.setSpacing(2)
        names.addWidget(label("Project Faraday", "display"))
        names.addWidget(label(f"Version {__version__}, by Pure Tech", "muted", selectable=True))
        top.addLayout(names, 1)
        hero.layout_.addLayout(top)
        hero.layout_.addWidget(label(DESCRIPTION, wrap=True))
        links = QHBoxLayout()
        links.setSpacing(theme.SPACE["xl"])
        github = button("GitHub", "link", "external-link", lambda: _open(GITHUB_URL), GITHUB_URL)
        discord = button("Discord", "link", "external-link", lambda: _open(DISCORD_URL), DISCORD_URL)
        links.addWidget(github)
        links.addWidget(discord)
        links.addStretch(1)
        hero.layout_.addLayout(links)
        col.addWidget(hero)

        # Credits
        credits = Card(margins=20, spacing=12)
        credits_head = QHBoxLayout()
        credits_head.setSpacing(10)
        credits_head.addWidget(IconLabel("layers", 20, "accent"))
        credits_head.addWidget(label("Built with", "heading"))
        credits_head.addStretch(1)
        credits.layout_.addLayout(credits_head)
        grid = QGridLayout()
        grid.setHorizontalSpacing(theme.SPACE["xl"])
        grid.setVerticalSpacing(theme.SPACE["sm"])
        for r, (name, licence) in enumerate(CREDITS):
            grid.addWidget(label(name), r, 0)
            grid.addWidget(label(licence, "muted"), r, 1)
        grid.setColumnStretch(1, 1)
        credits.layout_.addLayout(grid)
        col.addWidget(credits)

        # Licence
        licence = Card(margins=20, spacing=8)
        licence_head = QHBoxLayout()
        licence_head.setSpacing(10)
        licence_head.addWidget(IconLabel("file-lock", 20, "accent"))
        licence_head.addWidget(label("License", "heading"))
        licence_head.addStretch(1)
        licence.layout_.addLayout(licence_head)
        licence.layout_.addWidget(label(
            "Project Faraday is free software released under the MIT License. "
            "It comes with no warranty: keep a backup of your vault somewhere safe.", "muted", wrap=True))
        col.addWidget(licence)
        col.addStretch(1)
        page_layout(self, content, max_width=760)
