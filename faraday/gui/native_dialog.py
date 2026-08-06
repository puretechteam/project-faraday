"""
Native (OS) file dialogs that always appear ABOVE Faraday's borderless window.

Faraday's main window is ``overrideredirect(True)`` (the OS title bar is
replaced by in-app chrome) and its dialogs are borderless too. An
override-redirect window is invisible to the window manager, so a native common
dialog (``tk_getOpenFile`` / ``tk_getSaveFile``) is not guaranteed to be stacked
above it: the picker can open BEHIND the app. Because the picker is modal, the
app then looks frozen - nothing responds and the window that owns input is
hidden.

What actually decides the stacking on Windows (measured on this Tk build):

* An owned window is always above its owner, and the owned windows of a
  topmost window are raised into the topmost band with it.
* Tk gives the common dialog an OWNER only when no ``-parent`` is passed: it
  then uses the interpreter's main window. Passing ``-parent`` for an
  OVERRIDEREDIRECT toplevel yields ``hwndOwner = 0`` (no owner at all), which
  drops the picker into the normal band where any always-on-top window - or a
  window that grabbed the foreground - can cover it.

So the guard below deliberately does NOT pass ``parent``; it keeps Tk's own
main-window ownership and lifts that main window (and therefore the owned
picker, plus the app's own modal dialogs, which are owned by it as well) into
the topmost band for the lifetime of the call. The previous ``-topmost`` value
is always restored afterwards.

Nothing here touches the vault; these helpers only pick a path.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Callable, Dict, Optional

import tkinter as tk
from tkinter import filedialog


def _main_window(widget: Any) -> Optional[tk.Misc]:
    """Return the Tk MAIN window - the one Tk makes the dialog's owner."""
    if widget is None:
        return None
    root = None
    try:
        root = widget._root()  # Tkinter's own accessor for the '.' window
    except Exception:
        try:
            root = widget.nametowidget(".")
        except Exception:
            root = None
    if root is None:
        return None
    try:
        return root if root.winfo_exists() else None
    except Exception:
        return None


@contextmanager
def dialog_on_top(widget: Any):
    """Float the app (and the native dialog it owns) above every other window.

    Yields the main window (or ``None`` when it could not be resolved). The
    previous ``-topmost`` state is always restored, even if the body raises.
    """
    root = _main_window(widget)
    previous: Optional[bool] = None
    if root is not None:
        try:
            previous = bool(root.attributes("-topmost"))
            if not previous:
                root.attributes("-topmost", True)
            root.update_idletasks()
        except Exception:
            # Platform/WM refused the hint: the dialog is still owned by the
            # main window, which is the part that guarantees the stacking.
            previous = None
    try:
        yield root
    finally:
        if root is not None and previous is not None and not previous:
            try:
                root.attributes("-topmost", False)
            except Exception:
                pass


def _show(func: Callable[..., Any], widget: Any, options: Dict[str, Any]) -> Any:
    # NOTE: no ``parent`` option on purpose - see the module docstring.
    try:
        with dialog_on_top(widget):
            return func(**options)
    finally:
        # AFTER the topmost band is released, or a non-topmost caller window
        # could not be raised back over the main window (a hidden modal dialog
        # is exactly the "app is frozen" symptom this module exists to avoid).
        _restore_focus(widget)


def _restore_focus(widget: Any) -> None:
    """Bring the caller's own (possibly modal) window back to the front."""
    try:
        top = widget.winfo_toplevel()
        if not top.winfo_exists():
            return
        top.lift()
        top.update_idletasks()
        top.focus_force()
    except Exception:
        pass


def ask_open_filename(widget: Any, **options: Any) -> str:
    """``filedialog.askopenfilename`` that cannot hide behind the app window."""
    return _show(filedialog.askopenfilename, widget, options)


def ask_save_as_filename(widget: Any, **options: Any) -> str:
    """``filedialog.asksaveasfilename`` that cannot hide behind the app window."""
    return _show(filedialog.asksaveasfilename, widget, options)
