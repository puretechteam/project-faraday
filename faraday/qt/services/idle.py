"""Locks the vault after a period with no keyboard or mouse input anywhere in the app."""

from PySide6.QtCore import QEvent, QObject, QTimer, Signal

_INPUT_EVENTS = {
    QEvent.KeyPress, QEvent.MouseButtonPress, QEvent.MouseMove, QEvent.Wheel,
    QEvent.TouchBegin, QEvent.TabletPress,
}


class IdleMonitor(QObject):
    idle = Signal()

    def __init__(self, app, parent=None):
        super().__init__(parent)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.idle)
        self._ms = 0
        app.installEventFilter(self)

    def set_minutes(self, minutes: float) -> None:
        self._ms = int(minutes * 60_000)
        self.reset()

    def set_milliseconds(self, ms: int) -> None:  # for tests
        self._ms = int(ms)
        self.reset()

    def reset(self) -> None:
        if self._ms > 0:
            self._timer.start(self._ms)
        else:
            self._timer.stop()

    def stop(self) -> None:
        self._timer.stop()

    def eventFilter(self, obj, event):
        if event.type() in _INPUT_EVENTS and self._timer.isActive():
            self._timer.start(self._ms)
        return False
