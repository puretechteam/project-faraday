"""
Render the README screenshots (docs/screenshots/*.png) from a throwaway demo
vault with made-up data. Never touches real vaults or settings.

    python scripts/make_screenshots.py
"""

import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = tempfile.mkdtemp(prefix="faraday-shots-")
# The native platform renders with the real system fonts; windows are kept off-screen.
os.environ["QT_QPA_PLATFORM"] = "windows" if sys.platform == "win32" else "offscreen"
os.environ["QT_SCALE_FACTOR"] = "2"
os.environ["FARADAY_APPDATA"] = os.path.join(WORK, "appdata")
os.environ["FARADAY_VAULTS_DIR"] = os.path.join(WORK, "vaults")
os.makedirs(os.environ["FARADAY_VAULTS_DIR"])
sys.path.insert(0, ROOT)
OUT = os.path.join(ROOT, "docs", "screenshots")
os.makedirs(OUT, exist_ok=True)

import faraday.vault.crypto as crypto  # noqa: E402
crypto.validate_argon2_params = lambda *a, **k: True  # demo vault only: instant key derivation
import faraday.qt.services.vault_service as vs  # noqa: E402
vs.get_argon2_params = lambda level="standard": {"time_cost": 1, "memory_cost": 8, "parallelism": 1}
from faraday import pin  # noqa: E402
pin.mark_offer_shown()

from PySide6.QtCore import QEventLoop, QPoint, QRect, Qt, QTimer  # noqa: E402
from PySide6.QtGui import QColor, QPainter, QPixmap  # noqa: E402
from PySide6.QtWidgets import QScrollArea  # noqa: E402

from faraday.models.schema import REGISTRY  # noqa: E402
from faraday.qt.app import build_app  # noqa: E402

DEMO = [
    ("credential", {"site_note": "GitHub", "username": "alex.morgan", "password": "v9#Lq2!mTz8pW4", "url": "https://github.com/login", "notes": "Personal account"}),
    ("credential", {"site_note": "Northwind Bank", "username": "amorgan", "password": "Rx7$kP2m!Qw9", "url": "https://northwind.example", "notes": ""}),
    ("credential", {"site_note": "Proton Mail", "username": "alex@morgan.example", "password": "pebble-orbit-canyon-41", "url": "", "notes": ""}),
    ("credential", {"site_note": "Steam", "username": "alexm", "password": "Gk3!vN8sYq2", "url": "", "notes": ""}),
    ("credential", {"site_note": "Old forum", "username": "alexm", "password": "summer2019", "url": "", "notes": ""}),
    ("credential", {"site_note": "Figma", "username": "alex@morgan.example", "password": "T7w#pL0zQ4!c", "url": "", "notes": ""}),
    ("card", {"cardholder_name": "Alex Morgan", "card_number": "4111111111111111", "expiration_month": "8", "expiration_year": "2029", "cvv": "123", "billing_zip": "30301", "site_note": "Everyday card"}),
    ("identity", {"full_name": "Alex Morgan", "email": "alex@morgan.example", "phone": "555-0142", "date_of_birth": "1992-04-18", "address": "12 Example Lane\nSpringfield", "social_security_number": "000-00-0000", "site_note": ""}),
    ("two_factor", {"service_name": "GitHub", "totp_secret": "JBSWY3DPEHPK3PXP", "backup_codes": "4f9a-2c71\n8b3e-61d0\nc5d2-9a47", "site_note": ""}),
    ("two_factor", {"service_name": "Northwind Bank", "totp_secret": "KRSXG5CTMVRXEZLU", "backup_codes": "", "site_note": ""}),
    ("wifi", {"network_name": "Morgan Home 5G", "password": "lantern-meadow-quiet-7", "security_type": "WPA3", "site_note": ""}),
    ("secure_note", {"title": "Seed phrase (cold wallet)", "content": "demo demo demo demo demo demo", "site_note": ""}),
    ("api_key", {"service_name": "Stripe", "environment": "dev", "api_key": "sk_test_demo", "api_secret": "", "notes": "Test mode", "site_note": ""}),
    ("crypto", {"address": "bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh", "site_note": "Cold wallet"}),
    ("emergency_contact", {"contact_name": "Jordan Morgan", "relationship": "Sibling", "phone": "555-0177", "email": "", "address": "", "medical_notes": "", "instructions": "Has the spare key", "site_note": ""}),
]


def pump(ms=80):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def wait_for(cond, ms=8000):
    loop = QEventLoop()
    t = QTimer()
    t.timeout.connect(lambda: cond() and loop.quit())
    t.start(10)
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


app, ctx, window = build_app([])
window.tray.hide()
window.setAttribute(Qt.WA_DontShowOnScreen, True)
window.resize(1240, 780)
window.show()


def use_theme(theme_id):
    ctx.settings.theme_mode = theme_id
    ctx.settings.accent = ""
    ctx.save_settings()
    pump(120)


def save(name, pixmap=None):
    (pixmap or window.grab()).save(os.path.join(OUT, f"{name}.png"))
    print("saved", name)


use_theme("dark")
save("lock-screen")

ctx.service.create(os.path.join(os.environ["FARADAY_VAULTS_DIR"], "Personal.vault"), b"demo-password")
wait_for(lambda: window.shell is not None)
for type_id, values in DEMO:
    done = []
    ctx.service.add(REGISTRY[type_id].build(values), done.append)
    wait_for(lambda: bool(done))
doc = os.path.join(WORK, "passport-scan.pdf")
with open(doc, "wb") as fh:
    fh.write(b"%PDF-1.4 demo")
done = []
ctx.service.add_document(doc, "ID / Driver License", "Passport scan", done.append)
wait_for(lambda: bool(done))


def show(key, select_title=None):
    window.navigate(key)
    page = window.shell.current_page()
    if select_title and hasattr(page, "model"):
        for i, row in enumerate(page.model.rows):
            if row.title == select_title:
                page.list.setCurrentIndex(page.model.index(i))
    pump(150)
    return page


show("overview")
save("overview")

show("credential", "GitHub")
save("logins")

use_theme("spiral")
show("two_factor", "GitHub")
save("two-factor-spiral")

use_theme("dark")
page = show("settings")
area = page.findChild(QScrollArea)
tiles = page.theme_tiles
top = tiles["system"].mapTo(area.widget(), QPoint(0, 0)).y()
area.verticalScrollBar().setValue(max(0, top - 330))
pump(150)
save("themes")

use_theme("light")
show("generator")
save("generator-light")

use_theme("dark")
show("credential", "GitHub")
from faraday.qt.views.command_palette import Command, CommandPalette  # noqa: E402
palette = CommandPalette(window, ctx, [Command("Lock vault", "lock", lambda: None, "Ctrl+L"),
                                       Command("Password generator", "wand-sparkles", lambda: None, "Ctrl+G")],
                         lambda *a: None, lambda *a: None)
pump(150)
base = window.grab()  # before the palette exists, so nothing half-repainted ends up behind it
palette.edit.setText("north")
palette.resize(600, 340)
palette.setAttribute(Qt.WA_DontShowOnScreen, True)
palette.show()
pump(150)
from faraday.qt import theme  # noqa: E402
ratio = base.devicePixelRatio()
overlay = QPixmap(round(palette.width() * ratio), round(palette.height() * ratio))
overlay.setDevicePixelRatio(ratio)
overlay.fill(QColor(theme.current().bg))  # offscreen dialogs grab with a transparent backdrop
palette.render(overlay)
composed = QPixmap(base.size())
composed.setDevicePixelRatio(base.devicePixelRatio())
painter = QPainter(composed)
painter.drawPixmap(0, 0, base)
painter.fillRect(QRect(0, 0, window.width(), window.height()), QColor(0, 0, 0, 120))
x = (window.width() - palette.width()) // 2
painter.drawPixmap(QPoint(x, 110), overlay)
painter.setPen(QColor(theme.current().border))
painter.drawRect(QRect(x, 110, palette.width() - 1, palette.height() - 1))
painter.end()
palette.reject()
save("command-palette", composed)

ctx.service.lock("manual")
print("done:", OUT)
