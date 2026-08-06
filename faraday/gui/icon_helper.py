"""
Icon path helper for GUI windows.
Handles both normal execution and PyInstaller frozen context.
"""

import os
import sys


def get_icon_path() -> str:
    """Get the path to the application icon."""
    base_path = sys._MEIPASS if getattr(sys, 'frozen', False) else os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    return os.path.join(base_path, 'assets', 'icon.ico')


def set_window_icon(window):
    """Set the application icon for a tkinter window."""
    try:
        icon_path = get_icon_path()
        if os.path.exists(icon_path):
            window.iconbitmap(icon_path)
    except Exception:
        pass
