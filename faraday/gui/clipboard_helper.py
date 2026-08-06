"""
Centralized clipboard utility for sensitive data.
Handles clipboard operations with sensitivity-aware timeout logic.
"""

import tkinter as tk
from typing import Optional


def copy_to_clipboard(text: str, sensitivity_level: str, root: tk.Tk) -> None:
    """Copy text to clipboard with auto-clear based on sensitivity level.
    
    Args:
        text: Text to copy to clipboard
        sensitivity_level: Sensitivity level ("normal", "sensitive", "critical")
        root: Tkinter root window for clipboard operations
        
    Clipboard auto-clear timeout: 30 seconds for all sensitivity levels.
    """
    if not text:
        return
    
    root.clipboard_clear()
    root.clipboard_append(text)
    
    # Auto-clear after 30 seconds (same timeout for all levels)
    def clear_clipboard():
        try:
            root.clipboard_clear()
        except Exception:
            pass  # Ignore errors when clearing (window may be closed)
    
    root.after(30000, clear_clipboard)

