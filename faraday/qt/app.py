"""Entry point for the Qt GUI: ``faraday gui`` or the ``faraday-gui`` launcher."""

import getpass
import sys

from PySide6.QtCore import QCoreApplication
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication

from .. import access_log
from ..settings import load_settings
from . import icons, theme

APP_ID = "PureTech.Faraday"


def _server_name() -> str:
    try:
        user = getpass.getuser()
    except Exception:
        user = "user"
    return f"{APP_ID}.{user}"


def _hand_off_to_running_instance() -> bool:
    """If Faraday is already running, ask it to come to the front and return True."""
    sock = QLocalSocket()
    sock.connectToServer(_server_name())
    if sock.waitForConnected(300):
        sock.write(b"show")
        sock.waitForBytesWritten(300)
        sock.disconnectFromServer()
        return True
    return False


def build_app(argv=None):
    """Create the QApplication, context and main window (also used by tests)."""
    from .context import AppContext
    from .main_window import MainWindow
    from .services.clipboard import ClipboardService
    from .services.guard import Guard
    from .services.vault_service import VaultService

    app = QApplication.instance() or QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName("Faraday")
    app.setOrganizationName("Pure Tech")
    app.setWindowIcon(icons.app_icon())
    settings = load_settings()
    theme.apply_theme(app, settings.theme_mode, settings.accent, settings.font_scale, settings.theme_colors)
    service = VaultService(settings)
    ctx = AppContext(app=app, settings=settings, service=service,
                     clipboard=ClipboardService(settings), guard=Guard(settings, service))
    window = MainWindow(ctx)
    app.styleHints().colorSchemeChanged.connect(
        lambda *_: settings.theme_mode == "system" and window.apply_settings())
    return app, ctx, window


def main(argv=None) -> int:
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
        except Exception:
            pass
    QCoreApplication.setApplicationName("Faraday")
    app, ctx, window = build_app(argv)
    if _hand_off_to_running_instance():
        return 0
    server = QLocalServer(app)
    QLocalServer.removeServer(_server_name())  # clears a stale socket after a crash (POSIX)
    if server.listen(_server_name()):
        def on_connection():
            conn = server.nextPendingConnection()
            if conn is not None:
                conn.readyRead.connect(window.bring_to_front)
                conn.disconnected.connect(conn.deleteLater)
        server.newConnection.connect(on_connection)
    try:
        access_log.record("app_launched", source="gui")
    except Exception:
        pass
    window.show()
    code = app.exec()
    try:
        access_log.record("app_closed", source="gui")
    except Exception:
        pass
    return code


if __name__ == "__main__":
    sys.exit(main())
