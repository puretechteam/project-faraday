"""
Top-level window: switches between the lock screen and the unlocked shell,
and owns everything that must react to locking (dialogs, clipboard, idle
timer, Windows session lock, tray).
"""

import sys
from typing import Optional

from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtGui import QAction, QKeySequence, QShortcut
from PySide6.QtWidgets import QApplication, QDialog, QMainWindow, QMenu, QStackedWidget, QSystemTrayIcon

from .. import pin
from . import icons, theme
from .context import AppContext
from .services.idle import IdleMonitor
from .views.command_palette import Command, CommandPalette
from .views.unlock_view import UnlockView
from .widgets.common import Toast, alive
from .widgets.dialogs import SetPinDialog, confirm

WM_WTSSESSION_CHANGE = 0x02B1
WTS_SESSION_LOCK = 0x7
WM_POWERBROADCAST = 0x0218
PBT_APMSUSPEND = 0x0004
WDA_NONE, WDA_EXCLUDEFROMCAPTURE = 0x0, 0x11


class MainWindow(QMainWindow):
    def __init__(self, ctx: AppContext):
        super().__init__()
        self.ctx = ctx
        ctx.window = self
        ctx._toast = lambda m, k="success", c=0: self.toast.show_message(m, k, countdown=c)
        ctx._navigate = self.navigate
        ctx._settings_applied = self.apply_settings
        self.setWindowTitle("Faraday")
        self.setWindowIcon(icons.app_icon())
        self.resize(1200, 840)
        self.setMinimumSize(900, 600)

        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)
        self.unlock_view = UnlockView(ctx)
        self.unlock_view.open_generator.connect(self.open_generator_dialog)
        self.stack.addWidget(self.unlock_view)
        self.shell = None
        self.toast = Toast(self)

        self.idle = IdleMonitor(QApplication.instance(), self)
        self.idle.idle.connect(lambda: self.lock("auto_timeout"))
        ctx.service.unlocked.connect(self._on_unlocked)
        ctx.service.locked.connect(self._on_locked)
        ctx.clipboard.copied.connect(self._on_copied)

        for seq, fn in (
            ("Ctrl+K", self.open_palette), ("Ctrl+L", lambda: self.lock("manual")),
            ("Ctrl+N", lambda: self.shell and self.shell.new_entry()),
            ("Ctrl+Shift+C", lambda: self.shell and self.shell.copy_primary()),
            ("Ctrl+G", lambda: self.navigate("generator")),
            ("Ctrl+,", lambda: self.navigate("settings")),
            ("Ctrl+F", lambda: self.shell and self.shell.focus_filter()),
        ):
            QShortcut(QKeySequence(seq), self).activated.connect(fn)

        self._session_registered = False
        self._build_tray()
        self.apply_settings()

    # ---------------------------------------------------------------- lock / unlock

    def _on_unlocked(self, path: str):
        from .views.shell import Shell
        self.shell = Shell(self.ctx, self.open_palette, lambda: self.lock("manual"))
        self.stack.addWidget(self.shell)
        self.stack.setCurrentWidget(self.shell)
        self.shell.navigate("overview")
        self.idle.set_minutes(self.ctx.settings.auto_lock_minutes)
        self._update_tray()
        self.setWindowTitle(f"Faraday - {self.ctx.service.vault_name()}")
        QTimer.singleShot(400, self._offer_pin)

    def lock(self, reason: str = "manual"):
        if self.ctx.service.is_unlocked:
            self.ctx.service.lock(reason)

    def _on_locked(self, reason: str):
        self.idle.stop()
        self.ctx.clipboard.clear_if_ours()
        self.ctx.guard.reset()
        for w in QApplication.topLevelWidgets():
            if isinstance(w, QDialog) and w.isVisible() and getattr(w, "closes_on_lock", True):
                w.reject()
        path = None
        if self.shell is not None:
            path = self.ctx.service.path
            shell, self.shell = self.shell, None
            self.stack.removeWidget(shell)
            shell.deleteLater()
        self.stack.setCurrentWidget(self.unlock_view)
        self.unlock_view.refresh(reason, select=path or self._last_path())
        self.setWindowTitle("Faraday")
        self._update_tray()

    def _last_path(self) -> Optional[str]:
        from .. import recent
        paths = recent.load_recent()
        return paths[0] if paths else None

    def _offer_pin(self):
        if not self.ctx.service.is_unlocked or pin.offer_shown():
            return
        pin.mark_offer_shown()
        if confirm(self, "Add an action PIN?",
                   "A short PIN can guard revealing, copying, editing and deleting, so someone at your "
                   "unlocked PC cannot grab secrets in one click. You can change this later in Settings.",
                   "Set a PIN", cancel_text="Not now"):
            dlg = SetPinDialog(self)
            if dlg.exec() == QDialog.Accepted and dlg.pin:
                pin.set_pin(dlg.pin)
                self.toast.show_message("PIN set")

    # ---------------------------------------------------------------- navigation

    def navigate(self, key: str, entry_id: Optional[str] = None):
        if self.shell is not None:
            self.shell.navigate(key, entry_id)
        elif key == "generator":
            self.open_generator_dialog()

    def open_palette(self):
        if self.shell is None:
            return
        commands = [
            Command("Lock vault", "lock", lambda: self.lock("manual"), "Ctrl+L"),
            Command("Password generator", "wand-sparkles", lambda: self.navigate("generator"), "Ctrl+G"),
            Command("Overview", "layout-grid", lambda: self.navigate("overview")),
            Command("All items", "layers", lambda: self.navigate("all")),
            Command("Backups", "archive", lambda: self.navigate("backups")),
            Command("Import from Bitwarden, KeePass or Faraday", "upload", lambda: self.navigate("transfer")),
            Command("Export encrypted archive", "download", lambda: self.navigate("transfer")),
            Command("Access log", "history", lambda: self.navigate("access_log")),
            Command("Threat model", "shield-alert", lambda: self.navigate("threat")),
            Command("Settings", "settings", lambda: self.navigate("settings"), "Ctrl+,"),
        ]
        from .. import themes
        for theme_id in themes.THEME_IDS:
            icon = "monitor" if theme_id == themes.SYSTEM else ("moon" if themes.is_dark(theme_id) else "sun")
            commands.append(Command(f"Theme: {themes.theme_name(theme_id)}", icon,
                                    lambda t=theme_id: self._set_mode(t)))
        from ..models.schema import REGISTRY
        for spec in REGISTRY.values():
            commands.append(Command(f"Go to {spec.plural}", spec.icon, lambda k=spec.type_id: self.navigate(k)))
            commands.append(Command(f"New {spec.label.lower()}", "plus",
                                    lambda k=spec.type_id: (self.navigate(k), self.shell and self.shell.new_entry())))

        def copy_entry(entry_id):
            entry = self.ctx.service.entry(entry_id)
            if entry is not None and self.shell is not None:
                self.shell.navigate(entry.get_entry_type(), entry_id)
                self.shell.copy_primary()
        CommandPalette(self, self.ctx, commands, lambda t, e: self.navigate(t if t != "_opaque" else "all", e),
                       copy_entry).exec()

    def open_generator_dialog(self):
        from .views.generator_view import GeneratorDialog
        GeneratorDialog(self, self.ctx).exec()

    def _set_mode(self, mode: str):
        self.ctx.settings.theme_mode = mode
        self.ctx.settings.theme_colors = {}  # a picked theme shows its own colours
        self.ctx.save_settings()

    def _on_copied(self, label: str, seconds: int):
        self.toast.show_message(label, "success", countdown=seconds)

    # ---------------------------------------------------------------- settings

    def apply_settings(self):
        s = self.ctx.settings
        theme.apply_theme(QApplication.instance(), s.theme_mode, s.accent, s.font_scale, s.theme_colors)
        if self.ctx.service.is_unlocked:
            self.idle.set_minutes(s.auto_lock_minutes)
        self._apply_capture_protection()
        if hasattr(self, "tray"):
            self.tray.setVisible(QSystemTrayIcon.isSystemTrayAvailable())

    def _apply_capture_protection(self):
        if sys.platform != "win32":
            return
        try:
            import ctypes
            affinity = WDA_EXCLUDEFROMCAPTURE if self.ctx.settings.hide_from_capture else WDA_NONE
            ctypes.windll.user32.SetWindowDisplayAffinity(int(self.winId()), affinity)
        except Exception:
            pass

    # ---------------------------------------------------------------- tray

    def _build_tray(self):
        self.tray = QSystemTrayIcon(icons.app_icon(), self)
        self.tray.setToolTip("Faraday")
        menu = QMenu(self)
        self.tray_show = QAction("Open Faraday", self, triggered=self.bring_to_front)
        self.tray_lock = QAction("Lock vault", self, triggered=lambda: self.lock("manual"))
        self.tray_gen = QAction("Password generator", self,
                                triggered=lambda: (self.bring_to_front(), self.navigate("generator")))
        quit_action = QAction("Exit", self, triggered=self.quit)
        for a in (self.tray_show, self.tray_lock, self.tray_gen):
            menu.addAction(a)
        menu.addSeparator()
        menu.addAction(quit_action)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(
            lambda reason: reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick) and self.bring_to_front())
        self._update_tray()

    def _update_tray(self):
        unlocked = self.ctx.service.is_unlocked
        self.tray_lock.setEnabled(unlocked)
        self.tray.setToolTip(f"Faraday - {self.ctx.service.vault_name()} (unlocked)" if unlocked else "Faraday (locked)")

    def bring_to_front(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def quit(self):
        self._quitting = True
        self.close()

    # ---------------------------------------------------------------- window events

    def showEvent(self, event):
        super().showEvent(event)
        theme.set_dark_title_bar(self, theme.current().dark)
        self._apply_capture_protection()
        if sys.platform == "win32" and not self._session_registered:
            try:
                import ctypes
                ctypes.windll.wtsapi32.WTSRegisterSessionNotification(int(self.winId()), 0)
                self._session_registered = True
            except Exception:
                pass

    def nativeEvent(self, event_type, message):
        if sys.platform == "win32" and self.ctx.settings.lock_on_session_lock:
            try:
                import ctypes.wintypes
                msg = ctypes.wintypes.MSG.from_address(int(message))
                if (msg.message == WM_WTSSESSION_CHANGE and msg.wParam == WTS_SESSION_LOCK) or \
                        (msg.message == WM_POWERBROADCAST and msg.wParam == PBT_APMSUSPEND):
                    QTimer.singleShot(0, lambda: self.lock("session_lock"))
            except Exception:
                pass
        return super().nativeEvent(event_type, message)

    def changeEvent(self, event):
        if event.type() == QEvent.WindowStateChange and self.isMinimized():
            if self.ctx.settings.lock_on_minimize:
                QTimer.singleShot(0, lambda: self.lock("minimized"))
            if self.ctx.settings.minimize_to_tray and self.tray.isVisible():
                QTimer.singleShot(0, self.hide)
        super().changeEvent(event)

    def closeEvent(self, event):
        self.lock("app_exit")
        self.ctx.clipboard.clear_if_ours()
        if sys.platform == "win32" and self._session_registered:
            try:
                import ctypes
                ctypes.windll.wtsapi32.WTSUnRegisterSessionNotification(int(self.winId()))
            except Exception:
                pass
        self.tray.hide()
        super().closeEvent(event)
        QApplication.instance().quit()
