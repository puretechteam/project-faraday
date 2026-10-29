"""Render the Faraday brand mark (faraday/qt/icons.py) into packaging/faraday.ico for the Windows build."""

import io
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from PIL import Image  # noqa: E402
from PySide6.QtCore import QBuffer, QIODevice  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402

from faraday.qt import icons  # noqa: E402

SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)


def main():
    app = QGuiApplication([])  # noqa: F841
    frames = []
    for size in SIZES:
        buf = QBuffer()
        buf.open(QIODevice.WriteOnly)
        icons.brand_pixmap(size).save(buf, "PNG")
        frames.append(Image.open(io.BytesIO(bytes(buf.data()))).convert("RGBA"))
    out = os.path.join(HERE, "faraday.ico")
    frames[-1].save(out, format="ICO", sizes=[(s, s) for s in SIZES], append_images=frames[:-1])
    print("wrote", out)


if __name__ == "__main__":
    main()
