"""
Console window toggle for PyInstaller frozen executables.
"""

import sys


def is_frozen() -> bool:
    """Check if running as PyInstaller frozen executable."""
    return getattr(sys, 'frozen', False)


def toggle_console():
    """Toggle console window visibility (Windows only, frozen exe only)."""
    if not is_frozen() or sys.platform != 'win32':
        return
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        user32 = ctypes.windll.user32
        hwnd = kernel32.GetConsoleWindow()
        if hwnd:
            is_visible = user32.IsWindowVisible(hwnd)
            user32.ShowWindow(hwnd, 0 if is_visible else 5)
    except Exception:
        pass


def is_console_visible() -> bool:
    """Check if console is currently visible."""
    if not is_frozen() or sys.platform != 'win32':
        return True
    try:
        import ctypes
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        hwnd = kernel32.GetConsoleWindow()
        return bool(user32.IsWindowVisible(hwnd)) if hwnd else True
    except Exception:
        return True
