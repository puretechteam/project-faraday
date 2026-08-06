"""
Dialogs: a themed, centered, modal ``Dialog`` base plus reusable
``ThemedPasswordDialog``, ``AboutDialog``, and ``PasswordGeneratorDialog``.
Also a thin launcher for the existing ``ui_theme.ThemeSettingsDialog``.

API contracts (consumed by ``main_window.py`` / ``credential_section.py``):

    ThemedPasswordDialog(parent, title="Unlock Vault", confirm=False,
                          show_generate=True) -> .show() -> str | None
    PasswordGeneratorDialog(parent, title="Password Generator") -> .show() -> str | None

This module also exposes the small Win32 window helpers the dialogs need
(:func:`native_hwnd`, :func:`set_window_owner`, :func:`work_area`); they are
shared with ``main_window`` so the same logic is not written twice.
"""

from __future__ import annotations

import os
from typing import Callable, Dict, Optional, Tuple

import tkinter as tk
from tkinter import messagebox, ttk

from ..clipboard_helper import copy_to_clipboard
from ..design_system import RADIUS, SPACING, TYPOGRAPHY, build_tokens, font_role, get_active_merged
from ...generator.password import PasswordGenerator
from ..ui_theme import register_themed, unregister_themed
from ._icons import load_icon
from .inputs import DangerButton, GhostButton, IconButton, LabeledEntry, PrimaryButton
from .surface import RoundedSurface


# Characters that are visually ambiguous and easy to confuse with one another.
_SIMILAR_CHARS = "ilIoO0L1|`'\"{}[]()/\\"


# ---------------------------------------------------------------------------
# Win32 window helpers
# ---------------------------------------------------------------------------
# ``wm overrideredirect`` makes Tk DESTROY and RE-CREATE a toplevel's wrapper
# HWND as an unowned ``WS_POPUP | WS_EX_TOOLWINDOW`` window parented to the
# desktop. That throws away the owner relationship ``transient()`` established,
# and ownership is the only thing on Windows that guarantees a window stays
# above another one. These helpers put the owner back.
_GWLP_HWNDPARENT = -8
_SWP_NOSIZE = 0x0001
_SWP_NOMOVE = 0x0002
_SWP_NOZORDER = 0x0004
_SWP_NOACTIVATE = 0x0010
_SWP_FRAMECHANGED = 0x0020
_SPI_GETWORKAREA = 0x0030
_MONITOR_DEFAULTTONEAREST = 0x0002


def _as_handle(value: int) -> int:
    """Normalize a possibly sign-extended handle to an unsigned integer."""
    return int(value) & 0xFFFFFFFFFFFFFFFF


def native_hwnd(widget: Optional[tk.Misc]) -> Optional[int]:
    """Return the native wrapper HWND behind a Tk widget (Windows only).

    Same pattern as ``MainWindow._hwnd``: ``winfo_id()`` is the Tk window, and
    its Win32 parent is the toplevel wrapper the window manager sees.
    """
    if os.name != "nt" or widget is None:
        return None
    try:
        import ctypes

        widget.update_idletasks()
        wid = widget.winfo_id()
        user32 = ctypes.windll.user32
        user32.GetParent.restype = ctypes.c_void_p
        user32.GetParent.argtypes = [ctypes.c_void_p]
        parent = user32.GetParent(ctypes.c_void_p(wid))
        return int(parent or wid)
    except Exception:
        return None


def set_window_owner(hwnd: Optional[int], owner_hwnd: Optional[int]) -> bool:
    """Make ``owner_hwnd`` the OWNER of ``hwnd`` (Windows only).

    Returns ``True`` only when the owner was verified afterwards. Never raises.
    """
    if os.name != "nt" or not hwnd or not owner_hwnd or hwnd == owner_hwnd:
        return False
    try:
        import ctypes

        user32 = ctypes.windll.user32
        get_long = getattr(user32, "GetWindowLongPtrW", None) or user32.GetWindowLongW
        set_long = getattr(user32, "SetWindowLongPtrW", None) or user32.SetWindowLongW
        get_long.restype = ctypes.c_ssize_t
        get_long.argtypes = [ctypes.c_void_p, ctypes.c_int]
        set_long.restype = ctypes.c_ssize_t
        set_long.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_ssize_t]
        handle = ctypes.c_void_p(hwnd)
        if _as_handle(get_long(handle, _GWLP_HWNDPARENT)) == _as_handle(owner_hwnd):
            return True
        set_long(handle, _GWLP_HWNDPARENT, ctypes.c_ssize_t(owner_hwnd).value)
        # Let the frame pick the new relationship up without moving, resizing,
        # restacking or activating the window.
        try:
            user32.SetWindowPos.argtypes = [
                ctypes.c_void_p, ctypes.c_void_p,
                ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                ctypes.c_uint,
            ]
            user32.SetWindowPos(
                handle, None, 0, 0, 0, 0,
                _SWP_FRAMECHANGED | _SWP_NOMOVE | _SWP_NOSIZE
                | _SWP_NOZORDER | _SWP_NOACTIVATE,
            )
        except Exception:
            pass
        return _as_handle(get_long(handle, _GWLP_HWNDPARENT)) == _as_handle(owner_hwnd)
    except Exception:
        return False


def activate_window(hwnd: Optional[int]) -> bool:
    """Make ``hwnd`` the ACTIVE/foreground window (Windows only).

    Ownership and ``lift()`` fix the stacking, but Tk maps an
    override-redirect toplevel WITHOUT activating it: the dialog is visible and
    on top while the main window keeps the keyboard, so every keystroke the
    user types into the (grabbed) app goes nowhere. Never raises.
    """
    if os.name != "nt" or not hwnd:
        return False
    try:
        import ctypes

        user32 = ctypes.windll.user32
        user32.BringWindowToTop.argtypes = [ctypes.c_void_p]
        user32.SetForegroundWindow.argtypes = [ctypes.c_void_p]
        user32.SetActiveWindow.argtypes = [ctypes.c_void_p]
        user32.SetActiveWindow.restype = ctypes.c_void_p
        handle = ctypes.c_void_p(hwnd)
        user32.BringWindowToTop(handle)
        if user32.SetForegroundWindow(handle):
            return True
        # Foreground lock (another process owns the foreground): activating
        # within our own thread is still enough for the app's own input.
        user32.SetActiveWindow(handle)
        return False
    except Exception:
        return False


def work_area(widget: Optional[tk.Misc] = None) -> Tuple[int, int, int, int]:
    """Return the usable screen rect ``(x, y, w, h)``, excluding the taskbar.

    When ``widget`` is given, the work area of the monitor that holds it is
    used, so a window on a secondary display is not clamped back onto the
    primary one. Falls back to ``SPI_GETWORKAREA`` (primary monitor) and then
    to the raw screen size. Never raises.
    """
    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes

            user32 = ctypes.windll.user32
            hwnd = native_hwnd(widget) if widget is not None else None
            if hwnd:
                class _MONITORINFO(ctypes.Structure):
                    _fields_ = [
                        ("cbSize", wintypes.DWORD),
                        ("rcMonitor", wintypes.RECT),
                        ("rcWork", wintypes.RECT),
                        ("dwFlags", wintypes.DWORD),
                    ]

                user32.MonitorFromWindow.restype = ctypes.c_void_p
                user32.MonitorFromWindow.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
                monitor = user32.MonitorFromWindow(
                    ctypes.c_void_p(hwnd), _MONITOR_DEFAULTTONEAREST
                )
                if monitor:
                    info = _MONITORINFO()
                    info.cbSize = ctypes.sizeof(_MONITORINFO)
                    user32.GetMonitorInfoW.argtypes = [
                        ctypes.c_void_p, ctypes.POINTER(_MONITORINFO)
                    ]
                    if user32.GetMonitorInfoW(ctypes.c_void_p(monitor), ctypes.byref(info)):
                        r = info.rcWork
                        return (r.left, r.top, r.right - r.left, r.bottom - r.top)
            rect = wintypes.RECT()
            if user32.SystemParametersInfoW(_SPI_GETWORKAREA, 0, ctypes.byref(rect), 0):
                return (
                    rect.left, rect.top,
                    rect.right - rect.left, rect.bottom - rect.top,
                )
        except Exception:
            pass
    try:
        if widget is not None:
            return (0, 0, widget.winfo_screenwidth(), widget.winfo_screenheight())
    except Exception:
        pass
    return (0, 0, 1024, 768)


class Dialog(tk.Toplevel):
    """A themed, rounded, modal dialog centered over its parent.

    Add widgets to ``self.content`` (a :class:`RoundedSurface` body).
    """

    def __init__(
        self,
        parent: tk.Misc,
        title: str = "Dialog",
        width: int = 420,
        height: int = 280,
        **kw,
    ) -> None:
        owner = parent.winfo_toplevel() if isinstance(parent, tk.Misc) else None
        super().__init__(owner)
        # Kept so _reassert_stacking() can restore the OWNER relationship that
        # overrideredirect(True) destroys (see that method).
        self._owner = owner
        self.title(title)
        self._width = width
        self._height = height
        self._title = title
        self._tokens: Optional[Dict[str, str]] = None
        # The child widget that should own the keyboard (see _on_focus_in).
        self._focus_target: Optional[tk.Misc] = None
        # WINDOWS: transient() is deliberately NOT used together with
        # overrideredirect(True). Measured on this Tk build: the wrapper HWND
        # of a TRANSIENT + override-redirect toplevel is created as
        # WS_CHILD (style 0x56000008) with no parent - a child of the DESKTOP.
        # Such a window can never be activated (SetForegroundWindow fails) nor
        # hold the keyboard focus (SetFocus -> ERROR_INVALID_PARAMETER), and it
        # sinks to the bottom of the z-order: exactly the "app is frozen, no
        # dialog visible, every click swallowed by the grab" bug. Without
        # transient() the wrapper is a normal WS_POPUP (0x96000008) that can be
        # owned, raised and activated - the owner link is (re)established in
        # _reassert_stacking(), which is what transient() was there for.
        self._transient_fallback = False
        if os.name != "nt":
            self.transient(owner if owner is not None else self)
        # NOTE: grab_set() deliberately happens at the very END of __init__.
        # A grab held by a half-built window that then fails to appear is a
        # silent, total application freeze (the console is hidden, so the
        # traceback is invisible) - see the guarded block below.
        try:
            self.resizable(True, True)
            # Replace the OS chrome with a custom title bar (below). The 1px
            # floor lets ``fit()`` size the window to its content with no gap.
            self.overrideredirect(True)
            self.minsize(self._width, 1)
            try:
                from ..icon_helper import set_window_icon
                set_window_icon(self)
            except Exception:
                pass

            # Custom title bar drawn ABOVE the rounded surface.
            self._build_title_bar()

            self._surface = RoundedSurface(self, radius=RADIUS["lg"], border=True)
            self._surface.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=0, pady=0)
            self.content = self._surface.body

            self.bind("<Escape>", lambda _e: self.destroy())
            self.bind("<FocusIn>", self._on_focus_in, add="+")
            self.protocol("WM_DELETE_WINDOW", self.destroy)

            self._center_over(parent)
            register_themed(self)
            self._try_apply_initial()
            # Auto-fit only once content actually exists; subclasses build
            # their widgets after super().__init__() and should call fit()
            # again at the end of their own __init__.
            if hasattr(self, "content") and self.content is not None:
                self.fit()
            # Children (labels/frames) are added by subclasses/callers AFTER
            # this __init__ returns. A timer callback (unlike after_idle) is
            # not drained by the update_idletasks() inside fit(), so this fires
            # once those children exist and they get recolored instead of
            # staying white.
            if self._tokens is not None:
                self.after(0, self._apply_content_theme)
            # Owner + raise BEFORE the modal grab, so the grab can only ever be
            # held by a window that is built, placed and actually on top.
            self._reassert_stacking()
            self.grab_set()
        except BaseException:
            # Never leave a modal grab (or a stray window) behind on failure.
            try:
                self.grab_release()
            except Exception:
                pass
            try:
                self.destroy()
            except Exception:
                pass
            raise

    # -- public api --------------------------------------------------------
    def fit(self) -> None:
        """Resize the dialog to fit its content, never smaller than the
        configured default width/height."""
        self.update_idletasks()
        self.geometry(
            f"{max(self._width, self.winfo_reqwidth())}x"
            f"{max(self._height, self.winfo_reqheight())}"
        )
        # Belt-and-braces: anything built since the last recolor gets painted.
        self._apply_content_theme()
        # A resize can re-map the wrapper window; make sure it is still owned
        # by (and above) the parent afterwards.
        self._reassert_stacking()

    def apply_theme(self, merged: Dict[str, str]) -> None:
        self._tokens = build_tokens(merged)
        bg = self._tokens["bg"]
        try:
            self.configure(background=bg)
        except tk.TclError:
            try:
                self.configure(bg=bg)
            except tk.TclError:
                pass
        # Recolor plain (non-ttk) content children so labels stay readable on
        # the themed surface instead of defaulting to black-on-dark.
        self._apply_content_theme()
        # Recolor the custom title bar too (not part of ``self.content``).
        self._style_title_bar()

    def destroy(self) -> None:
        # Order matters: the grab MUST be released even if the bookkeeping
        # below misbehaves, or the app is left deaf with no window to click.
        try:
            unregister_themed(self)
        except Exception:
            pass
        try:
            self.grab_release()
        except Exception:
            pass
        super().destroy()

    # -- theming helpers ---------------------------------------------------
    def _apply_content_theme(self) -> None:
        """Paint ``self.content``'s plain ``tk`` labels/frames with the active
        tokens. ttk widgets (buttons/entries) manage their own styling."""
        if self._tokens is None or not hasattr(self, "content"):
            return
        surface = self._tokens["surface"]
        text = self._tokens["text"]
        try:
            self._recolor(self.content, surface, text)
        except Exception:
            pass
        # Keep the custom title bar (outside ``self.content``) in sync too.
        self._style_title_bar()

    def _recolor(self, widget: tk.Misc, surface: str, text: str) -> None:
        tokens = self._tokens or {}
        for child in widget.winfo_children():
            # ttk widgets (incl. PrimaryButton/DangerButton/reveal Button) are
            # theme-driven elsewhere; never repaint them directly.
            if isinstance(child, ttk.Widget):
                continue
            try:
                if isinstance(child, tk.Label):
                    child.configure(bg=surface, fg=text)
                elif isinstance(child, tk.Scrollbar):
                    child.configure(
                        bg=tokens["surface"],
                        troughcolor=tokens["bg"],
                        activebackground=tokens["accent"],
                        bd=0,
                        highlightthickness=0,
                    )
                elif isinstance(child, tk.Frame):
                    child.configure(bg=surface)
                    self._recolor(child, surface, text)
            except (tk.TclError, KeyError):
                pass

    # -- internals ---------------------------------------------------------
    def _reassert_stacking(self) -> None:
        """Put this dialog back where the user can see it. Never raises.

        ``overrideredirect(True)`` (the custom title bar depends on it) makes
        Tk destroy and re-create the wrapper HWND as an UNOWNED popup, throwing
        away any parent relationship, and Tk maps override-redirect toplevels
        without activating them. The result is a fully built, mapped, grab
        holding dialog buried deep in the z-order - the app looks frozen.

        Two independent belts:

        * Windows only: set ``GWLP_HWNDPARENT`` so the dialog is a real OWNED
          window (an owned window is always above its owner and stays there
          when the parent is clicked), then ACTIVATE it, because an
          override-redirect toplevel is mapped without activation and the
          keyboard would stay attached to the main window.
        * Everywhere: ``lift()``, plus ``focus_force()`` as the fallback when
          the native activation is unavailable (non-Windows) or failed.

        Focus is handled carefully: ``focus_force()`` on the TOPLEVEL would
        cancel the pending ``entry.focus_set()`` that subclasses issue while
        their widgets are still unmapped (Tk defers such a request until the
        widget is mapped), leaving a dialog that is visible and active but
        swallows every keystroke. So the known focus child is forced instead,
        and when none is known yet nothing is forced as long as the window was
        natively activated.
        """
        try:
            try:
                self.update_idletasks()
            except tk.TclError:
                return
            activated = False
            if os.name == "nt":
                try:
                    if not self._reassert_owner():
                        self._transient_last_resort()
                    activated = activate_window(native_hwnd(self))
                except Exception:
                    activated = False
            try:
                self.lift()
            except tk.TclError:
                pass
            keep = self._focus_child() or self._focus_target
            if keep is not None:
                self._focus_target = keep
                try:
                    keep.focus_force()
                except tk.TclError:
                    pass
            elif not activated:
                # No child owns the focus yet and the OS would not activate us:
                # forcing the toplevel is better than a dead dialog.
                try:
                    self.focus_force()
                except tk.TclError:
                    pass
        except Exception:
            pass

    def _focus_child(self) -> Optional[tk.Misc]:
        """The widget INSIDE this dialog that should keep the keyboard focus."""
        try:
            # str(): Tk returns a Tcl_Obj here, which nametowidget() rejects.
            name = str(self.tk.call("focus", "-lastfor", self._w) or "")
            if not name:
                return None
            widget = self.nametowidget(name)
        except Exception:
            return None
        if widget is self or not isinstance(widget, tk.Misc):
            return None
        try:
            return widget if widget.winfo_toplevel() is self else None
        except Exception:
            return None

    def _on_focus_in(self, event: tk.Event) -> None:
        """Keep the keyboard on the dialog's own input widget.

        Activating the window makes Tk hand the focus to the TOPLEVEL when it
        processes the (asynchronous) WM_ACTIVATE, which silently takes it off
        the password entry - the dialog then looks focused but swallows every
        keystroke. Whenever the toplevel itself is focused, the focus is handed
        straight back to the child that last had it.
        """
        try:
            widget = event.widget
            if widget is self:
                target = self._focus_target
                if target is None or target is self:
                    return
                try:
                    if target.winfo_exists():
                        target.focus_set()
                except tk.TclError:
                    self._focus_target = None
            elif isinstance(widget, tk.Misc):
                self._focus_target = widget
        except Exception:
            pass

    def _reassert_owner(self) -> bool:
        """Re-establish the native OWNER link to the parent toplevel."""
        owner = getattr(self, "_owner", None)
        if owner is None:
            return False
        try:
            if not owner.winfo_exists():
                return False
        except Exception:
            return False
        return set_window_owner(native_hwnd(self), native_hwnd(owner))

    def _transient_last_resort(self) -> None:
        """If the native owner could not be set, fall back to Tk's transient.

        That yields the old WS_CHILD wrapper (not activatable), but a child
        window still cannot be covered by its parent, so the dialog remains
        visible instead of vanishing behind the app. Applied at most once.
        """
        if self._transient_fallback:
            return
        self._transient_fallback = True
        owner = getattr(self, "_owner", None)
        if owner is None:
            return
        try:
            self.transient(owner)
        except tk.TclError:
            pass

    def _try_apply_initial(self) -> None:
        try:
            if tk._default_root is not None:
                self.apply_theme(get_active_merged())
        except Exception:
            pass

    def _center_over(self, parent: tk.Misc) -> None:
        """Center over ``parent``, always inside the visible work area.

        A minimized parent reports ``rootx/rooty == -32000`` (Windows parks
        minimized windows there). Centering on that put the dialog at
        ``+-31600+-31680``: mapped, viewable and holding a modal grab, but
        permanently off-screen - the same "frozen app" symptom by a second
        route. So the parent's geometry is sanity-checked first, and the final
        position is clamped into the monitor's work area either way.
        """
        self.update_idletasks()
        origin = self._parent_origin(parent)
        if origin is not None:
            px, py, pw, ph = origin
            area = work_area(parent if isinstance(parent, tk.Misc) else None)
            x = px + max(0, (pw - self._width) // 2)
            y = py + max(0, (ph - self._height) // 2)
        else:
            # No usable parent geometry (minimized / not yet mapped): center on
            # the primary monitor instead of following it off-screen.
            area = work_area(None)
            ax, ay, aw, ah = area
            x = ax + max(0, (aw - self._width) // 2)
            y = ay + max(0, (ah - self._height) // 2)
        x, y = self._clamp_to_area(x, y, area)
        self.geometry(f"{self._width}x{self._height}+{x}+{y}")

    @staticmethod
    def _parent_origin(parent: tk.Misc):
        """``(x, y, w, h)`` of ``parent`` if it is really on-screen, else None."""
        for widget in (parent, getattr(parent, "winfo_toplevel", lambda: None)()):
            if not isinstance(widget, tk.Misc):
                continue
            try:
                pw = widget.winfo_width()
                ph = widget.winfo_height()
                px = widget.winfo_rootx()
                py = widget.winfo_rooty()
            except Exception:
                continue
            # Minimized (-32000) or never-mapped (1x1) parents are unusable.
            if pw <= 1 or ph <= 1 or px < -10000 or py < -10000:
                continue
            return (px, py, pw, ph)
        return None

    def _clamp_to_area(self, x: int, y: int, area) -> tuple:
        ax, ay, aw, ah = area
        x = min(max(x, ax), max(ax, ax + aw - self._width))
        y = min(max(y, ay), max(ay, ay + ah - self._height))
        return (int(x), int(y))

    # -- custom title bar --------------------------------------------------
    def _build_title_bar(self) -> None:
        """Draw a themed title bar (no OS chrome) with drag-to-move plus
        minimize/close square buttons."""
        self._title_bar = tk.Frame(self, bd=0, highlightthickness=0)
        self._title_bar.pack(side=tk.TOP, fill=tk.X)

        self._title_label = tk.Label(
            self._title_bar, text=self._title, font=font_role("body"),
            anchor=tk.W, bd=0, highlightthickness=0,
        )
        self._title_label.pack(side=tk.LEFT, padx=SPACING["md"], pady=SPACING["xs"])

        spacer = tk.Frame(self._title_bar, bd=0, highlightthickness=0)
        spacer.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self._min_btn = self._make_title_button("–", self.iconify)
        self._min_btn.pack(side=tk.RIGHT, padx=(0, SPACING["xs"]), pady=SPACING["xs"])
        self._close_btn = self._make_title_button("✕", self.destroy)
        self._close_btn.pack(side=tk.RIGHT, padx=(0, SPACING["xs"]), pady=SPACING["xs"])

        # Drag-to-move on the bar background, title, and spacer (not the btns).
        for w in (self._title_bar, self._title_label, spacer):
            w.bind("<ButtonPress-1>", self._start_move)
            w.bind("<B1-Motion>", self._do_move)

    def _make_title_button(self, glyph: str, command: Callable[[], None]) -> tk.Frame:
        size = 30
        btn = tk.Frame(
            self._title_bar, width=size, height=size, bd=0,
            highlightthickness=0, cursor="hand2",
        )
        btn.pack_propagate(False)
        lbl = tk.Label(btn, text=glyph, font=font_role("body"), bd=0, highlightthickness=0)
        lbl.pack(expand=True, fill=tk.BOTH)
        btn._label = lbl
        for target in (btn, lbl):
            target.bind("<Button-1>", lambda _e, c=command: c())
            target.bind("<Enter>", lambda _e, b=btn: self._title_btn_hover(b, True))
            target.bind("<Leave>", lambda _e, b=btn: self._title_btn_hover(b, False))
        return btn

    def _title_btn_hover(self, btn: tk.Frame, on: bool) -> None:
        if self._tokens is None:
            return
        bg = self._tokens["hover"] if on else self._tokens["bg"]
        try:
            btn.configure(bg=bg)
            btn._label.configure(bg=bg)
        except (tk.TclError, AttributeError):
            pass

    def _start_move(self, event: tk.Event) -> None:
        self._drag_x = event.x_root - self.winfo_x()
        self._drag_y = event.y_root - self.winfo_y()

    def _do_move(self, event: tk.Event) -> None:
        x = event.x_root - self._drag_x
        y = event.y_root - self._drag_y
        self.geometry(f"+{x}+{y}")

    def _style_title_bar(self) -> None:
        if self._tokens is None or not hasattr(self, "_title_bar"):
            return
        tb = self._tokens["bg"]
        text = self._tokens["text"]
        try:
            self._title_bar.configure(bg=tb)
            self._title_label.configure(bg=tb, fg=text)
            for btn in (self._min_btn, self._close_btn):
                btn.configure(bg=tb)
                btn._label.configure(bg=tb, fg=text)
        except (tk.TclError, AttributeError):
            pass


class ThemedPasswordDialog(Dialog):
    """A compact password entry dialog with a reveal toggle and an optional
    Generate button (new-vault flow only).

    The entered value is returned by :meth:`show` (``None`` if cancelled). Uses
    :class:`faraday.generator.password.PasswordGenerator` to fill the field.

    Signature:
        ``ThemedPasswordDialog(parent, title="Unlock Vault", confirm=False,
        show_generate=True)`` then ``show() -> str | None``.

    ``prompt`` / ``ok_label`` are accepted for backward compatibility with the
    legacy callers but are not part of the new contract.
    """

    def __init__(
        self,
        parent: tk.Misc,
        title: str = "Unlock Vault",
        confirm: bool = False,
        show_generate: bool = True,
        prompt: str = "Password",
        ok_label: str = "OK",
        **kw,
    ) -> None:
        # Fit the window to its actual content instead of forcing a tall 240px
        # floor; the entry group and the bottom-pinned button row must sit close
        # together with no large empty gap. confirm mode needs a little more.
        height = 200 if confirm else 120
        super().__init__(parent, title=title, width=380, height=height, **kw)
        # Override the base 240 min-height so the dialog can shrink to content.
        self.minsize(self._width, height)
        self.result: Optional[str] = None
        self._confirm = confirm
        self._show_generate = show_generate
        self._revealed = False

        # Button row packed FIRST (and anchored to the bottom) so content can
        # never squeeze/clip it, even at large font scales.
        btns = tk.Frame(self.content, bd=0, highlightthickness=0)
        btns.pack(
            side=tk.BOTTOM, fill=tk.X,
            padx=SPACING["md"], pady=(SPACING["xs"], SPACING["md"]),
        )
        ok_btn = PrimaryButton(btns, text=ok_label, command=self._ok)
        ok_btn.configure(padding=(10, 4))
        ok_btn.pack(side=tk.RIGHT, padx=(SPACING["sm"], 0))
        cancel_btn = DangerButton(btns, text="Cancel", command=self.destroy)
        cancel_btn.configure(padding=(10, 4))
        cancel_btn.pack(side=tk.RIGHT)

        tk.Label(self.content, text=prompt, font=font_role("body"), anchor=tk.W).pack(
            anchor=tk.W, padx=SPACING["md"], pady=(SPACING["md"], SPACING["xs"])
        )
        self._entry = ttk.Entry(self.content, show="*")
        self._entry.pack(fill=tk.X, padx=SPACING["md"])
        self._entry.focus_set()

        ctrl = tk.Frame(self.content, bd=0, highlightthickness=0)
        ctrl.pack(fill=tk.X, padx=SPACING["md"], pady=(SPACING["sm"], 0))
        if self._show_generate:
            gen_btn = GhostButton(ctrl, text="Generate", command=self._generate)
            gen_btn.configure(padding=(10, 4))
            gen_btn.pack(side=tk.LEFT)
        self._reveal_btn = ttk.Button(ctrl, text="Show", command=self._toggle_reveal)
        self._reveal_btn.configure(padding=(10, 4))
        self._reveal_btn.pack(side=tk.LEFT, padx=(SPACING["sm"], 0))

        if self._confirm:
            tk.Label(self.content, text="Confirm password", font=font_role("body"), anchor=tk.W).pack(
                anchor=tk.W, padx=SPACING["md"], pady=(SPACING["sm"], SPACING["xs"])
            )
            self._entry2 = ttk.Entry(self.content, show="*")
            self._entry2.pack(fill=tk.X, padx=SPACING["md"])

        self.bind("<Return>", lambda _e: self._ok())
        self._entry.bind("<Return>", lambda _e: self._ok())
        if self._confirm:
            self._entry2.bind("<Return>", lambda _e: self._ok())

        self.fit()
        if self._tokens is not None:
            self._apply_content_theme()

    def show(self) -> Optional[str]:
        """Run modally and return the entered password, or ``None`` if cancelled."""
        # Re-raise first: a dialog that is re-shown (or that was built while
        # something else grabbed the foreground) must not wait behind the app.
        # _reassert_stacking() also (re)places the keyboard focus - calling
        # focus_set() on the toplevel here would take it off the entry.
        self._reassert_stacking()
        try:
            self.grab_set()
        except tk.TclError:
            pass
        self.wait_window(self)
        return self.result

    def _toggle_reveal(self) -> None:
        self._revealed = not self._revealed
        show = "" if self._revealed else "*"
        self._entry.configure(show=show)
        try:
            self._entry2.configure(show=show)
        except Exception:
            pass
        self._reveal_btn.configure(text="Hide" if self._revealed else "Show")

    def _generate(self) -> None:
        try:
            pwd = PasswordGenerator(length=20).generate()
        except Exception:
            pwd = "cH4!kP9$qW2#mZ8@xQ1v"
        self._entry.delete(0, tk.END)
        self._entry.insert(0, pwd)
        if self._confirm:
            self._entry2.delete(0, tk.END)
            self._entry2.insert(0, pwd)

    def _ok(self) -> None:
        pwd = self._entry.get()
        if not pwd:
            messagebox.showerror("Password", "Password cannot be empty.", parent=self)
            return
        if self._confirm and pwd != self._entry2.get():
            messagebox.showerror("Password", "Passwords do not match.", parent=self)
            return
        self.result = pwd
        self.destroy()


class PasswordGeneratorDialog(Dialog):
    """A configurable password generator dialog.

    Lets the user tune length, character classes, excluded characters, and
    similarity filtering, with a live read-only preview, copy, and a "Use"
    button that accepts the generated value.

    Signature:
        ``PasswordGeneratorDialog(parent, title="Password Generator")`` then
        ``show() -> str | None``.

    ``callback`` is accepted for backward compatibility (fired with the chosen
    password when the user clicks Use/Copy) but is not part of the contract.
    """

    def __init__(
        self,
        parent: tk.Misc,
        title: str = "Password Generator",
        callback: Optional[Callable[[str], None]] = None,
        **kw,
    ) -> None:
        super().__init__(parent, title=title, width=560, height=320, **kw)
        self.result: Optional[str] = None
        self._callback = callback
        self._revealed = False

        # --- Length control -------------------------------------------------
        length_frame = tk.Frame(self.content, bd=0, highlightthickness=0)
        length_frame.pack(fill=tk.X, padx=SPACING["md"], pady=(SPACING["md"], SPACING["xs"]))
        tk.Label(length_frame, text="Length", font=font_role("body"), anchor=tk.W).pack(
            side=tk.LEFT
        )
        self._length = tk.IntVar(value=20)
        spin = ttk.Spinbox(
            length_frame, from_=8, to=64, textvariable=self._length, width=8
        )
        spin.pack(side=tk.LEFT, padx=(SPACING["sm"], 0))
        self._length.trace_add("write", lambda *_a: self._generate())

        # --- Character set checkboxes --------------------------------------
        opts_frame = tk.Frame(self.content, bd=0, highlightthickness=0)
        opts_frame.pack(fill=tk.X, padx=SPACING["md"], pady=(SPACING["xs"], SPACING["xs"]))
        self._uppercase = tk.BooleanVar(value=True)
        self._lowercase = tk.BooleanVar(value=True)
        self._digits = tk.BooleanVar(value=True)
        self._symbols = tk.BooleanVar(value=True)
        self._exclude_similar = tk.BooleanVar(value=False)
        checks = [
            ("Uppercase", self._uppercase),
            ("Lowercase", self._lowercase),
            ("Digits", self._digits),
            ("Symbols", self._symbols),
            ("Exclude similar", self._exclude_similar),
        ]
        for i, (label, var) in enumerate(checks):
            cb = ttk.Checkbutton(opts_frame, text=label, variable=var)
            cb.grid(row=i // 3, column=i % 3, sticky=tk.W, padx=SPACING["sm"], pady=SPACING["xs"])
            var.trace_add("write", lambda *_a: self._generate())

        # --- Exclude field --------------------------------------------------
        excl_frame = tk.Frame(self.content, bd=0, highlightthickness=0)
        excl_frame.pack(fill=tk.X, padx=SPACING["md"], pady=(SPACING["xs"], SPACING["xs"]))
        tk.Label(excl_frame, text="Exclude", font=font_role("body"), anchor=tk.W).pack(
            side=tk.LEFT
        )
        self._exclude = tk.StringVar()
        excl_entry = ttk.Entry(excl_frame, textvariable=self._exclude)
        excl_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(SPACING["sm"], 0))
        self._exclude.trace_add("write", lambda *_a: self._generate())

        # --- Live preview ---------------------------------------------------
        prev_frame = tk.Frame(self.content, bd=0, highlightthickness=0)
        prev_frame.pack(fill=tk.X, padx=SPACING["md"], pady=(SPACING["xs"], SPACING["xs"]))
        self._preview_var = tk.StringVar()
        self._preview = ttk.Entry(
            prev_frame, textvariable=self._preview_var, font=font_role("mono"),
            show="*", state="readonly",
        )
        self._preview.pack(side=tk.LEFT, fill=tk.X, expand=True)
        reveal_btn = IconButton(
            prev_frame, icon_name="eye", text_fallback="show",
            command=self._toggle_reveal,
        )
        reveal_btn.pack(side=tk.LEFT, padx=(SPACING["xs"], 0))
        copy_btn = IconButton(
            prev_frame, icon_name="copy", text_fallback="copy",
            command=self._copy,
        )
        copy_btn.pack(side=tk.LEFT, padx=(SPACING["xs"], 0))

        # --- Action buttons -------------------------------------------------
        btns = tk.Frame(self.content, bd=0, highlightthickness=0)
        btns.pack(side=tk.BOTTOM, fill=tk.X, padx=SPACING["md"], pady=(SPACING["xs"], SPACING["md"]))
        use_btn = PrimaryButton(btns, text="Use", command=self._use)
        use_btn.configure(padding=(10, 4))
        use_btn.pack(side=tk.RIGHT, padx=(SPACING["sm"], 0))
        gen_btn = GhostButton(btns, text="Generate", command=self._generate)
        gen_btn.configure(padding=(10, 4))
        gen_btn.pack(side=tk.RIGHT, padx=(SPACING["sm"], 0))
        close_btn = DangerButton(btns, text="Close", command=self.destroy)
        close_btn.configure(padding=(10, 4))
        close_btn.pack(side=tk.LEFT)

        self._generate()

        self.fit()
        if self._tokens is not None:
            self._apply_content_theme()

    def show(self) -> Optional[str]:
        """Run modally and return the generated password, or ``None`` if cancelled."""
        self._reassert_stacking()
        try:
            self.grab_set()
        except tk.TclError:
            pass
        self.wait_window(self)
        return self.result

    # -- internals ---------------------------------------------------------
    def _toggle_reveal(self) -> None:
        self._revealed = not self._revealed
        self._preview.configure(show="" if self._revealed else "*")

    def _build_exclude(self) -> str:
        excl = self._exclude.get()
        if self._exclude_similar.get():
            excl += _SIMILAR_CHARS
        return excl

    def _generate(self) -> None:
        try:
            use_u = self._uppercase.get()
            use_l = self._lowercase.get()
            use_d = self._digits.get()
            use_s = self._symbols.get()
            gen = PasswordGenerator(
                length=self._length.get(),
                use_uppercase=use_u,
                use_lowercase=use_l,
                use_digits=use_d,
                use_symbols=use_s,
                exclude_chars=self._build_exclude(),
            )
            pwd = gen.generate()
        except Exception as exc:  # empty charset, invalid length, etc.
            messagebox.showerror("Generator", str(exc), parent=self)
            return
        self._preview_var.set(pwd)
        self._preview.configure(show="" if self._revealed else "*")

    def _copy(self) -> None:
        pwd = self._preview_var.get()
        if not pwd:
            return
        try:
            copy_to_clipboard(pwd, "sensitive", self.winfo_toplevel())
        except Exception:
            try:
                self.clipboard_clear()
                self.clipboard_append(pwd)
            except Exception:
                pass
        self.result = pwd
        if self._callback is not None:
            self._callback(pwd)
        self.destroy()

    def _use(self) -> None:
        pwd = self._preview_var.get()
        if not pwd:
            return
        self.result = pwd
        if self._callback is not None:
            self._callback(pwd)
        self.destroy()


class AboutDialog(Dialog):
    """Shows app identity, version and a short description."""

    def __init__(self, parent: tk.Misc, **kw) -> None:
        super().__init__(parent, title="About Faraday", width=380, height=250, **kw)
        icon = load_icon("lock")
        if icon:
            tk.Label(self.content, image=icon, bd=0, highlightthickness=0).pack(
                pady=(SPACING["md"], SPACING["sm"])
            )
        tk.Label(self.content, text="Faraday 3.0.0", font=font_role("display")).pack()
        tk.Label(self.content, text="Copyright © Pure Tech", font=font_role("caption")).pack(
            pady=(SPACING["xs"], SPACING["sm"])
        )
        tk.Label(
            self.content,
            text=("Faraday is a calm, minimalist offline vault for passwords, "
                  "crypto keys, and secure notes. Your data stays encrypted on "
                  "this device."),
            font=font_role("body"), wraplength=300, justify=tk.CENTER,
        ).pack(padx=SPACING["md"], pady=SPACING["sm"])
        ok_btn = PrimaryButton(self.content, text="OK", command=self.destroy)
        ok_btn.configure(padding=(10, 4))
        ok_btn.pack(pady=SPACING["md"])

        self.fit()
        if self._tokens is not None:
            self._apply_content_theme()


def open_theme_settings(
    parent: tk.Misc,
    root: tk.Tk,
    style: ttk.Style,
    menus: Optional[list] = None,
    on_applied: Optional[Callable[[dict], None]] = None,
):
    """Thin launcher for the existing :class:`ui_theme.ThemeSettingsDialog`.

    Reuses the FTP-style theme editor rather than reimplementing it.
    """
    from ..ui_theme import ThemeSettingsDialog

    return ThemeSettingsDialog(
        parent, root, style, menus=menus, on_applied=on_applied,
    )
