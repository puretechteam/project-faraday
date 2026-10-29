"""
Lucide icons (ISC, see resources/icons/lucide/LICENSE-lucide.txt), recoloured
to the theme and cached per (name, colour, size).
"""

import os
import tempfile
from functools import lru_cache
from typing import Optional

from PySide6.QtCore import QByteArray, QRectF, QSize, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

RESOURCES = os.path.join(os.path.dirname(__file__), "resources")
ICON_DIR = os.path.join(RESOURCES, "icons", "lucide")


@lru_cache(maxsize=None)
def _svg_source(name: str) -> Optional[str]:
    path = os.path.join(ICON_DIR, f"{name}.svg")
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return None


@lru_cache(maxsize=512)
def _pixmap(name: str, color: str, size: int, ratio: float, stroke: float) -> QPixmap:
    source = _svg_source(name) or _svg_source("file-question") or ""
    source = source.replace("currentColor", color).replace('stroke-width="2"', f'stroke-width="{stroke}"')
    renderer = QSvgRenderer(QByteArray(source.encode("utf-8")))
    pm = QPixmap(round(size * ratio), round(size * ratio))
    pm.fill(Qt.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.Antialiasing)
    renderer.render(painter, QRectF(0, 0, pm.width(), pm.height()))
    painter.end()
    pm.setDevicePixelRatio(ratio)
    return pm


def _ratio() -> float:
    from PySide6.QtGui import QGuiApplication
    app = QGuiApplication.instance()
    return app.devicePixelRatio() if app else 1.0


def pixmap(name: str, color: Optional[str] = None, size: int = 18, stroke: float = 2.0) -> QPixmap:
    from . import theme
    return _pixmap(name, color or theme.current().text, size, max(1.0, _ratio()), stroke)


def icon(name: str, color: Optional[str] = None, size: int = 18) -> QIcon:
    from . import theme
    p = theme.current()
    ic = QIcon()
    ic.addPixmap(pixmap(name, color or p.text, size), QIcon.Normal)
    ic.addPixmap(pixmap(name, p.text_muted, size), QIcon.Disabled)
    return ic


_files = {}


def icon_file(name: str, color: str, size: int = 12) -> str:
    """A PNG on disk for stylesheet ``url()`` use (e.g. the checkbox tick)."""
    key = (name, color, size)
    if key not in _files:
        directory = os.path.join(tempfile.gettempdir(), "faraday-qt-icons")
        os.makedirs(directory, exist_ok=True)
        path = os.path.join(directory, f"{name}-{color.lstrip('#')}-{size}.png")
        _pixmap(name, color, size, 2.0, 3.0).save(path, "PNG")
        _files[key] = path
    return _files[key]


def brand_pixmap(size: int) -> QPixmap:
    """The Faraday mark: the Lucide vault glyph on a blue-violet rounded tile."""
    from PySide6.QtGui import QColor, QLinearGradient, QPainterPath
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.Antialiasing)
    gradient = QLinearGradient(0, 0, size, size)
    gradient.setColorAt(0.0, QColor("#4F7CFF"))
    gradient.setColorAt(1.0, QColor("#7C4DFF"))
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, size, size), size * 0.24, size * 0.24)
    painter.fillPath(path, gradient)
    glyph = round(size * 0.62)
    stroke = 2.0 if size >= 48 else 2.4
    painter.drawPixmap((size - glyph) // 2, (size - glyph) // 2, _pixmap("vault", "#FFFFFF", glyph, 1.0, stroke))
    painter.end()
    return pm


_app_icon = None


def app_icon() -> QIcon:
    global _app_icon
    if _app_icon is None:
        _app_icon = QIcon()
        for size in (16, 20, 24, 32, 40, 48, 64, 128, 256):
            _app_icon.addPixmap(brand_pixmap(size))
    return _app_icon


def clear_cache() -> None:
    _pixmap.cache_clear()


ICON_SIZE = QSize(18, 18)
