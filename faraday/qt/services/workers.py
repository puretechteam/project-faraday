"""
Run blocking work (Argon2, disk I/O) off the GUI thread.

``run_async(fn, on_done, on_error, pool=...)`` calls ``fn()`` on a pool thread
and delivers the result or exception back on the GUI thread. Vault operations
use ``VAULT_POOL``, a single-thread pool, so they run strictly one at a time.
"""

import traceback
from typing import Any, Callable, Optional

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, Signal

VAULT_POOL = QThreadPool()
VAULT_POOL.setMaxThreadCount(1)

# Keeps signal objects alive until their result is delivered.
_in_flight = set()


class _Signals(QObject):
    finished = Signal(object)
    failed = Signal(object)


class _Task(QRunnable):
    def __init__(self, fn: Callable[[], Any], signals: _Signals):
        super().__init__()
        self.fn = fn
        self.signals = signals
        self.setAutoDelete(True)

    def run(self):
        try:
            result = self.fn()
        except BaseException as exc:  # delivered to the GUI thread, never swallowed
            exc.__faraday_traceback__ = traceback.format_exc()
            self.signals.failed.emit(exc)
        else:
            self.signals.finished.emit(result)


def run_async(fn: Callable[[], Any], on_done: Optional[Callable[[Any], None]] = None,
              on_error: Optional[Callable[[BaseException], None]] = None,
              pool: Optional[QThreadPool] = None) -> None:
    signals = _Signals()  # created on the GUI thread, so queued slots run there
    _in_flight.add(signals)

    def done(result):
        _in_flight.discard(signals)
        if on_done:
            on_done(result)

    def failed(exc):
        _in_flight.discard(signals)
        if on_error:
            on_error(exc)
        else:
            print(getattr(exc, "__faraday_traceback__", repr(exc)))

    signals.finished.connect(done, Qt.QueuedConnection)
    signals.failed.connect(failed, Qt.QueuedConnection)
    (pool or QThreadPool.globalInstance()).start(_Task(fn, signals))
