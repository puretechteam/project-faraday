"""Win32 z-order guard for Faraday's borderless modal dialogs.

Why a Tk-level test CANNOT catch this bug
-----------------------------------------
Faraday's dialogs are ``overrideredirect(True)`` toplevels. On Windows that
makes Tk destroy and re-create the toplevel's wrapper HWND as an UNOWNED
``WS_POPUP | WS_EX_TOOLWINDOW`` window parented to the desktop, silently
discarding the owner relationship that ``transient()`` had just established.
Ownership is the only mechanism on Windows that guarantees a child window stays
above its parent, so the dialog then sinks hundreds of windows deep in the
native z-order - geometrically inside the main window's rect, with no taskbar
button and no Alt+Tab entry - while still holding a modal grab. Every click the
user makes is swallowed by that grab and the app looks frozen.

Tk reports nothing wrong in that state: ``winfo_exists()``, ``winfo_ismapped()``
and ``winfo_viewable()`` all return 1, the geometry is correct and the grab is
held. Only the NATIVE stacking order (``EnumWindows`` enumerates top-level
windows front-to-back) plus a hit test at the dialog's centre
(``WindowFromPoint``) can prove that the dialog is really in front of the main
window and reachable by a real mouse click.

Run from the repo root::

    python scripts/check_dialog_stacking.py

The script is self-killing: a watchdog hard-exits the process if the GUI ever
hangs, so it can never leave a stuck window behind.

Exit codes: 0 = OK, 1 = stacking regression, 2 = harness error,
3 = watchdog timeout (GUI hung and was hard-killed).
"""

import ctypes
import os
import sys
import threading
import time
from ctypes import wintypes

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

WATCHDOG_SECONDS = 30

GWLP_HWNDPARENT = -8
GWL_STYLE = -16
GWL_EXSTYLE = -20
WS_CHILD = 0x40000000
WS_POPUP = 0x80000000
GA_ROOT = 2
SW_MINIMIZE = 6
SW_RESTORE = 9
SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79


# --------------------------------------------------------------------- win32
class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


user32 = ctypes.windll.user32 if os.name == "nt" else None
_get_long = None


def _bind_win32():
    """Give every API we call an explicit signature (64-bit safe)."""
    global _get_long
    user32.GetParent.restype = ctypes.c_void_p
    user32.GetParent.argtypes = [ctypes.c_void_p]
    user32.GetAncestor.restype = ctypes.c_void_p
    user32.GetAncestor.argtypes = [ctypes.c_void_p, ctypes.c_uint]
    user32.WindowFromPoint.restype = ctypes.c_void_p
    user32.WindowFromPoint.argtypes = [POINT]
    user32.GetWindowRect.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.RECT)]
    user32.IsWindowVisible.argtypes = [ctypes.c_void_p]
    user32.IsWindow.argtypes = [ctypes.c_void_p]
    user32.GetWindowTextW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int]
    user32.ShowWindow.argtypes = [ctypes.c_void_p, ctypes.c_int]
    user32.GetForegroundWindow.restype = ctypes.c_void_p
    _get_long = getattr(user32, "GetWindowLongPtrW", None) or user32.GetWindowLongW
    _get_long.restype = ctypes.c_ssize_t
    _get_long.argtypes = [ctypes.c_void_p, ctypes.c_int]


def hwnd_of(widget):
    """Native wrapper HWND of a Tk widget (same pattern as MainWindow._hwnd)."""
    try:
        widget.update_idletasks()
        wid = widget.winfo_id()
        parent = user32.GetParent(ctypes.c_void_p(wid))
        return int(parent or wid)
    except Exception:
        return 0


def owner_of(hwnd):
    value = int(_get_long(ctypes.c_void_p(hwnd), GWLP_HWNDPARENT))
    return value & 0xFFFFFFFFFFFFFFFF if value else 0


def style_of(hwnd):
    return int(_get_long(ctypes.c_void_p(hwnd), GWL_STYLE)) & 0xFFFFFFFF


def title_of(hwnd):
    buf = ctypes.create_unicode_buffer(256)
    user32.GetWindowTextW(ctypes.c_void_p(hwnd), buf, 256)
    return buf.value


def rect_of(hwnd):
    rect = wintypes.RECT()
    user32.GetWindowRect(ctypes.c_void_p(hwnd), ctypes.byref(rect))
    return (rect.left, rect.top, rect.right, rect.bottom)


def z_order():
    """Visible top-level HWNDs, front-to-back (EnumWindows is z-ordered)."""
    found = []
    proto = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def _cb(hwnd, _lparam):
        if user32.IsWindowVisible(ctypes.c_void_p(hwnd)):
            found.append(int(hwnd))
        return True

    user32.EnumWindows(proto(_cb), 0)
    return found


def z_index(order, hwnd):
    try:
        return order.index(hwnd)
    except ValueError:
        return None


def window_at(x, y):
    """Top-level window under a screen point (the real hit test)."""
    hit = user32.WindowFromPoint(POINT(int(x), int(y)))
    if not hit:
        return 0
    root = user32.GetAncestor(ctypes.c_void_p(hit), GA_ROOT)
    return int(root or hit)


def virtual_screen():
    return (
        user32.GetSystemMetrics(SM_XVIRTUALSCREEN),
        user32.GetSystemMetrics(SM_YVIRTUALSCREEN),
        user32.GetSystemMetrics(SM_CXVIRTUALSCREEN),
        user32.GetSystemMetrics(SM_CYVIRTUALSCREEN),
    )


# ------------------------------------------------------------------ harness
class Report:
    def __init__(self):
        self.failures = []

    def check(self, ok, label, detail=""):
        print(f"  [{'PASS' if ok else 'FAIL'}] {label}" + (f"  {detail}" if detail else ""))
        if not ok:
            self.failures.append(label)
        return ok

    def info(self, label, detail=""):
        print(f"  [info] {label}" + (f"  {detail}" if detail else ""))


def pump(root, seconds=0.35):
    """Run the Tk event loop for a while without entering mainloop()."""
    end = time.time() + seconds
    while time.time() < end:
        try:
            root.update()
        except Exception:
            return
        time.sleep(0.01)


def watchdog(seconds=WATCHDOG_SECONDS):
    def _kill():
        sys.stderr.write(f"\nWATCHDOG: no verdict after {seconds}s - hard-killing.\n")
        sys.stderr.flush()
        os._exit(3)

    timer = threading.Timer(seconds, _kill)
    timer.daemon = True
    timer.start()
    return timer


def describe(label, hwnd, order):
    idx = z_index(order, hwnd)
    print(
        f"  {label:<12} hwnd=0x{hwnd:X}  z={idx if idx is not None else 'not-visible'}"
        f"  owner=0x{owner_of(hwnd):X}  rect={rect_of(hwnd)}  title={title_of(hwnd)!r}"
    )


def run():
    from faraday.gui.main_window import MainWindow
    from faraday.gui.widgets import ThemedPasswordDialog

    report = Report()
    app = MainWindow()
    root = app.root
    pump(root, 0.8)
    main_hwnd = hwnd_of(root)

    # ---------------------------------------------------------- phase 1 ---
    print("\n[phase 1] password dialog over a normal main window")
    dlg = ThemedPasswordDialog(
        root, title="Unlock Vault", prompt="Enter master password:", show_generate=False
    )
    pump(root, 0.6)
    dlg_hwnd = hwnd_of(dlg)
    order = z_order()
    describe("MAIN WINDOW", main_hwnd, order)
    describe("PWD DIALOG", dlg_hwnd, order)

    z_main = z_index(order, main_hwnd)
    z_dlg = z_index(order, dlg_hwnd)
    report.check(bool(dlg_hwnd), "dialog has a native window", f"hwnd=0x{dlg_hwnd:X}")
    report.check(z_dlg is not None, "dialog is a VISIBLE native top-level window")
    report.check(
        z_dlg is not None and z_main is not None and z_dlg < z_main,
        "dialog is IN FRONT of the main window in the Win32 z-order",
        f"z(dialog)={z_dlg} z(main)={z_main}",
    )
    owner = owner_of(dlg_hwnd)
    report.info(
        "dialog owner",
        f"0x{owner:X}" + (" == main window (owned)" if owner == main_hwnd else " (not owned by main)"),
    )

    # The wrapper of a TRANSIENT + override-redirect toplevel is created by Tk
    # as a WS_CHILD window (a child of the DESKTOP): it can never be activated
    # or hold the keyboard focus, so the app looks alive but eats every key.
    style = style_of(dlg_hwnd)
    report.check(
        not style & WS_CHILD and bool(style & WS_POPUP),
        "dialog wrapper is a real WS_POPUP (not a WS_CHILD desktop child)",
        f"style=0x{style:08X}",
    )
    foreground = int(user32.GetForegroundWindow() or 0)
    report.check(
        foreground == dlg_hwnd,
        "dialog is the ACTIVE (foreground) window - keystrokes reach it",
        f"foreground=0x{foreground:X} {title_of(foreground)!r}",
    )
    try:
        focused = dlg.focus_get()
    except Exception:
        focused = None
    report.check(
        focused is getattr(dlg, "_entry", None),
        "keyboard focus is the password entry",
        f"focus={focused}",
    )

    left, top, right, bottom = rect_of(dlg_hwnd)
    cx, cy = (left + right) // 2, (top + bottom) // 2
    hit = window_at(cx, cy)
    detail = f"point=({cx},{cy}) -> 0x{hit:X} {title_of(hit)!r}"
    if hit == main_hwnd:
        detail += "  <-- OCCLUDED BY THE MAIN WINDOW"
    report.check(hit == dlg_hwnd, "hit test at the dialog's centre returns the dialog", detail)
    report.check(hit != main_hwnd, "dialog is NOT occluded by the main window", "")

    vx, vy, vw, vh = virtual_screen()
    on_screen = left >= vx and top >= vy and right <= vx + vw and bottom <= vy + vh
    report.check(on_screen, "dialog is on-screen", f"rect=({left},{top},{right},{bottom}) screen=({vx},{vy},{vw},{vh})")

    # --------------------------------------------------- phase 1b: raise ---
    # A click on the main window must NOT bury the dialog again (this is what
    # ownership buys; lift() alone would only survive until the next raise).
    root.lift()
    root.focus_force()
    pump(root, 0.5)
    order = z_order()
    z_main = z_index(order, main_hwnd)
    z_dlg = z_index(order, dlg_hwnd)
    hit = window_at(cx, cy)
    report.check(
        z_dlg is not None and z_main is not None and z_dlg < z_main,
        "dialog STAYS in front after the main window is raised",
        f"z(dialog)={z_dlg} z(main)={z_main} hit=0x{hit:X}",
    )

    try:
        dlg.destroy()
    except Exception:
        pass
    pump(root, 0.3)
    report.check(
        not user32.IsWindow(ctypes.c_void_p(dlg_hwnd)) or not user32.IsWindowVisible(ctypes.c_void_p(dlg_hwnd)),
        "dialog is gone after destroy()",
    )
    try:
        grab = root.grab_current()
    except Exception:
        grab = None
    report.check(not grab, "no modal grab is left behind", f"grab_current={grab!r}")

    # ---------------------------------------------------------- phase 2 ---
    # A dialog built while the parent is minimized must not land off-screen at
    # -32000 (Windows' parking coordinates for minimized windows).
    print("\n[phase 2] password dialog built while the main window is minimized")
    user32.ShowWindow(ctypes.c_void_p(main_hwnd), SW_MINIMIZE)
    pump(root, 0.5)
    report.info("parent origin while minimized", f"({root.winfo_rootx()},{root.winfo_rooty()})")
    dlg2 = ThemedPasswordDialog(
        root, title="Unlock Vault", prompt="Enter master password:", show_generate=False
    )
    pump(root, 0.5)
    dlg2_hwnd = hwnd_of(dlg2)
    left, top, right, bottom = rect_of(dlg2_hwnd)
    describe("PWD DIALOG", dlg2_hwnd, z_order())
    on_screen = left >= vx and top >= vy and right <= vx + vw and bottom <= vy + vh
    report.check(
        on_screen,
        "dialog built over a MINIMIZED parent is still on-screen",
        f"rect=({left},{top},{right},{bottom})",
    )
    try:
        dlg2.destroy()
    except Exception:
        pass
    pump(root, 0.2)
    user32.ShowWindow(ctypes.c_void_p(main_hwnd), SW_RESTORE)
    pump(root, 0.3)

    # ------------------------------------------------------------ teardown -
    try:
        app._on_closing()
    except Exception:
        try:
            root.destroy()
        except Exception:
            pass

    print()
    if report.failures:
        print("RESULT: FAIL -", len(report.failures), "check(s) failed:")
        for name in report.failures:
            print("   !!", name)
        return 1
    print("RESULT: PASS - the dialog is natively in front, clickable and on-screen.")
    return 0


def main():
    if os.name != "nt":
        print("SKIP: this guard measures the Win32 z-order; it only runs on Windows.")
        return 0
    _bind_win32()
    watchdog()
    try:
        return run()
    except Exception as exc:  # harness failure, not a stacking verdict
        import traceback

        traceback.print_exc()
        print("RESULT: ERROR -", exc)
        return 2


if __name__ == "__main__":
    code = main()
    sys.stdout.flush()
    # Hard exit: the tray icon and Tk both keep non-daemon threads/handles
    # alive; this guard must never linger.
    os._exit(code)
