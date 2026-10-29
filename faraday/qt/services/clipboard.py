"""
Clipboard with auto-clear.

Secrets are copied with the Windows formats that keep them out of clipboard
history (Win+V), cloud clipboard sync and clipboard monitors, and are cleared
after the configured delay, but only if the clipboard still holds our value.
"""

import hashlib
import struct
import sys

from PySide6.QtCore import QMimeData, QObject, QTimer, Signal
from PySide6.QtGui import QGuiApplication

_WIN_FORMATS = {
    "ExcludeClipboardContentFromMonitorProcessing": b"\x00",
    "CanIncludeInClipboardHistory": struct.pack("<I", 0),
    "CanUploadToCloudClipboard": struct.pack("<I", 0),
}


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class ClipboardService(QObject):
    copied = Signal(str, int)  # label, seconds until cleared (0 = not cleared)
    cleared = Signal()

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self._digest = None
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.clear_if_ours)

    def copy(self, text: str, label: str = "Copied", secret: bool = True) -> None:
        mime = QMimeData()
        mime.setText(text)
        if secret and sys.platform == "win32":
            for name, data in _WIN_FORMATS.items():
                mime.setData(f'application/x-qt-windows-mime;value="{name}"', data)
        QGuiApplication.clipboard().setMimeData(mime)
        seconds = int(self.settings.clipboard_seconds) if secret else 0
        if secret:
            self._digest = _digest(text)
            if seconds > 0:
                self._timer.start(seconds * 1000)
            else:
                self._timer.stop()
        self.copied.emit(label, seconds)

    def clear_if_ours(self) -> None:
        self._timer.stop()
        if self._digest is None:
            return
        clipboard = QGuiApplication.clipboard()
        if _digest(clipboard.text()) == self._digest:
            clipboard.clear()
            self.cleared.emit()
        self._digest = None
