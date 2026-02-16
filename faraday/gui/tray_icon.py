"""
System tray icon integration (optional).
Can be disabled via build flag or config.
"""

import sys
import threading
from typing import Optional, Callable
from .console_toggle import toggle_console, is_frozen


TRAY_ENABLED = True

try:
    import pystray
    from PIL import Image, ImageDraw
    TRAY_AVAILABLE = True
except ImportError:
    TRAY_AVAILABLE = False
    TRAY_ENABLED = False


class TrayIcon:
    """System tray icon for basic vault functions."""
    
    def __init__(self, on_show: Optional[Callable] = None, on_lock: Optional[Callable] = None, on_exit: Optional[Callable] = None, on_toggle_console: Optional[Callable] = None):
        """Initialize tray icon."""
        if not TRAY_ENABLED or not TRAY_AVAILABLE:
            self.icon = None
            return
        self.on_show = on_show
        self.on_lock = on_lock
        self.on_exit = on_exit
        self.on_toggle_console = on_toggle_console
        self.icon = None
        self._create_icon()
    
    def _create_icon(self):
        """Create tray icon image and menu."""
        image = Image.new('RGB', (64, 64), color='gray')
        draw = ImageDraw.Draw(image)
        draw.ellipse([16, 16, 48, 48], fill='blue', outline='white')
        menu_items = []
        if self.on_show:
            menu_items.append(pystray.MenuItem("Show Window", self._show_window))
        if self.on_lock:
            menu_items.append(pystray.MenuItem("Lock Vault", self._lock_vault))
        if is_frozen() and self.on_toggle_console:
            menu_items.append(pystray.MenuItem("Toggle Console", self._toggle_console))
            menu_items.append(pystray.MenuItem.SEPARATOR)
        menu_items.append(pystray.MenuItem("Exit", self._exit_app))
        self.icon = pystray.Icon("Project Faraday", image, "Project Faraday", pystray.Menu(*menu_items))
    
    def _show_window(self, icon, item):
        """Show main window."""
        if self.on_show:
            self.on_show()
    
    def _lock_vault(self, icon, item):
        """Lock vault."""
        if self.on_lock:
            self.on_lock()
    
    def _toggle_console(self, icon, item):
        """Toggle console window."""
        if self.on_toggle_console:
            self.on_toggle_console()
    
    def _exit_app(self, icon, item):
        """Exit application."""
        if self.on_exit:
            self.on_exit()
        self.stop()
    
    def run(self):
        """Run tray icon (non-blocking in separate thread)."""
        if self.icon:
            threading.Thread(target=self.icon.run, daemon=True).start()
    
    def stop(self):
        """Stop tray icon."""
        if self.icon:
            self.icon.stop()


def is_tray_available() -> bool:
    """Check if tray support is available."""
    return TRAY_ENABLED and TRAY_AVAILABLE
