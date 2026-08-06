"""
Main application shell for Project Faraday 3.0.0.

This is the Phase-4 "App Shell" rewrite: a borderless window (the OS title bar
is replaced by in-app chrome: drag-to-move plus minimize/close controls in the
topbar) with a hideable left ``Sidebar``, a ``Topbar`` (search + vault name +
lock + theme), a scrollable ``Content`` area, and a status bar. A locked vault
shows an inline ``UnlockScreen`` (built on
:class:`faraday.gui.widgets.surface.RoundedSurface`) instead of the old modal
:class:`PasswordDialog`.

--------------------------------------------------------------------------
SECTION VIEW CONTRACT (implemented by Phase 4 section rewrites)
--------------------------------------------------------------------------
Each migrated section class must follow this interface so ``MainWindow`` can
host it uniformly:

    class SomeSection:
        def __init__(self, parent: tk.Misc,
                     vault_manager: VaultManager,
                     vault_path: str = None):
            self.frame = ttk.Frame(parent)   # the view's root widget
            ...

        def filter(self, query: str) -> None:
            '''Filter the visible entries to those matching *query* (live,
            called from the Topbar SearchBar). No-op when *query* is empty.'''

        def refresh(self) -> None:
            '''Reload data from the VaultManager and rebuild the view.'''

Notes for Phase 4:
* ``parent`` is the scrollable content frame owned by ``MainWindow``; the
  section must create ``self.frame`` as a child of it and NOT pack it itself
  (``MainWindow`` packs/unpacks the active view).
* ``vault_path`` is optional; current sections ignore it, but it is forwarded
  when accepted (e.g. ``ThreatModelPanel``).
* ``MainWindow`` calls ``filter(query)`` on search and ``refresh()`` after
  unlock. For the current (pre-rewrite) sections, which expose the private
  ``_refresh_list()`` instead of ``refresh()``, ``MainWindow`` falls back to
  ``_refresh_list()`` so existing code keeps working verbatim.
* The home/"overview" nav key has no section class; ``MainWindow`` supplies the
  inline :class:`_OverviewView` dashboard (vault summary, per-category entry
  counts and quick actions). It replaced the old, redundant "Vault" placeholder.
"""

import inspect
import os
import shutil
import webbrowser
from datetime import datetime
from typing import Dict, Optional

import tkinter as tk
from tkinter import ttk, messagebox

from cryptography.exceptions import InvalidTag

from faraday import access_log

from ..vault.manager import VaultManager
from .credential_section import CredentialSection
from .crypto_section import CryptoSection
from .secure_note_section import SecureNoteSection
from .card_section import CardSection
from .identity_section import IdentitySection
from .emergency_contact_section import EmergencyContactSection
from .two_factor_section import TwoFactorSection
from .api_key_section import ApiKeySection
from .wifi_section import WifiSection
from .document_section import DocumentSection
from .threat_panel import ThreatModelPanel
from .tray_icon import TrayIcon, is_tray_available
from .console_toggle import toggle_console
from .icon_helper import set_window_icon
from .native_dialog import ask_open_filename, ask_save_as_filename
from .vault_history import load_recent_vaults, save_recent_vault
from .action_guard import (
    menu_change_action_pin,
    menu_disable_action_pin,
    menu_enable_or_change_action_pin,
)
from .ui_theme import (
    PRESET_LABELS,
    ThemeSettingsDialog,
    apply_saved_theme,
    apply_theme_to_popup_menus,
    merge_theme,
    normalize_preset_id,
    quick_apply_preset,
    register_themed,
)
from .design_system import RADIUS, SPACING, font_role, get_active_merged, build_tokens
from .widgets import (
    AboutDialog,
    EmptyState,
    GhostButton,
    IconButton,
    PrimaryButton,
    RoundedSurface,
    SearchBar,
    Sidebar,
    ThemedPasswordDialog,
    open_theme_settings,
)

try:  # ships with the access-log feature; keep the app usable if it is absent
    from .access_log_window import AccessLogDialog
except Exception:  # pragma: no cover - defensive import guard
    AccessLogDialog = None


# Sidebar navigation: (key, label, icon_name). The key maps 1:1 to a section
# class below; "overview" is the home dashboard view (no section class, see
# ``_OverviewView``). It replaced the old "Vault" entry, which only showed a
# static welcome placeholder and read as a duplicate of the app itself.
NAV_ITEMS = [
    ("overview", "Overview", "vault"),
    ("credentials", "Credentials", "key"),
    ("crypto", "Crypto", "crypto"),
    ("notes", "Secure Notes", "note"),
    ("cards", "Cards", "card"),
    ("identity", "Identity", "user"),
    ("emergency", "Emergency", "emergency"),
    ("security", "2FA", "shield"),
    ("api", "API Keys", "key"),
    ("wifi", "Wi-Fi", "wifi"),
    ("documents", "Documents", "file"),
    ("threat", "Threat Model", "threat"),
]

NAV_TITLES = {
    "overview": "Overview",
    "credentials": "Credentials",
    "crypto": "Crypto Addresses",
    "notes": "Secure Notes",
    "cards": "Cards",
    "identity": "Identity",
    "emergency": "Emergency Contacts",
    "security": "Two-Factor",
    "api": "API Keys",
    "wifi": "Wi-Fi",
    "documents": "Documents",
    "threat": "Threat Model",
}

# Home nav key + the categories the Overview dashboard counts:
# (nav key, tile label, VaultManager entry type).
HOME_KEY = "overview"
OVERVIEW_CATEGORIES = [
    ("credentials", "Credentials", "credential"),
    ("crypto", "Crypto", "crypto"),
    ("notes", "Secure Notes", "secure_note"),
    ("cards", "Cards", "card"),
    ("identity", "Identity", "identity"),
    ("emergency", "Emergency", "emergency_contact"),
    ("security", "2FA", "two_factor"),
    ("api", "API Keys", "api_key"),
    ("wifi", "Wi-Fi", "wifi"),
    ("documents", "Documents", "document"),
]

# Community links (sidebar footer + Help menu).
GITHUB_URL = "https://github.com/puretechteam"
DISCORD_URL = "https://discord.gg/dRMRGCG9Fk"

SIDEBAR_WIDTH = 220
SIDEBAR_WIDTH_COLLAPSED = 64

# The UnlockScreen card has a fixed height; more rows than this overflowed it,
# clipped the last entries and pushed the Open/New buttons out of the card.
MAX_RECENT_ROWS = 6


class _View:
    """Minimal view wrapper exposing the section interface.

    Used for the home/placeholder view (no underlying section class). Sections
    are duck-typed against this interface by ``MainWindow``.
    """

    frame: tk.Widget

    def filter(self, query: str) -> None:  # pragma: no cover - placeholder
        return None

    def refresh(self) -> None:  # pragma: no cover - placeholder
        return None


class _OverviewView(_View):
    """Home dashboard shown for the ``overview`` nav key.

    Replaces the old "Vault" placeholder (a static welcome card that merely
    duplicated the app/sidebar branding) with something useful: the open vault,
    a total entry count, one clickable tile per category showing its live count,
    and a row of quick actions. Implements the section view contract
    (``frame`` / ``filter`` / ``refresh``) and registers for live theming.
    """

    def __init__(self, parent: tk.Misc, window: "MainWindow") -> None:
        self._window = window
        tokens = window._theme_tokens()
        self.frame = tk.Frame(parent, bg=tokens["bg"])
        self._wrap = tk.Frame(self.frame, bd=0, highlightthickness=0, bg=tokens["bg"])
        self._wrap.pack(fill=tk.BOTH, expand=True, padx=SPACING["xl"], pady=SPACING["xl"])
        register_themed(self)
        self.refresh()

    # -- section interface -------------------------------------------------
    def filter(self, query: str) -> None:
        return None

    def refresh(self) -> None:
        """Rebuild the dashboard from the VaultManager and current tokens."""
        if not self._alive():
            return
        t = self._window._theme_tokens()
        self.frame.configure(bg=t["bg"])
        self._wrap.configure(bg=t["bg"])
        for child in list(self._wrap.winfo_children()):
            try:
                child.destroy()
            except Exception:
                pass
        counts, total = self._counts()
        self._build_header(t, total)
        self._build_tiles(t, counts)
        self._build_actions(t)

    def apply_theme(self, merged: Dict[str, str]) -> None:
        try:
            self.refresh()
        except Exception:
            pass

    # -- internals ---------------------------------------------------------
    def _alive(self) -> bool:
        try:
            return bool(self.frame.winfo_exists() and self._wrap.winfo_exists())
        except Exception:
            return False

    def _counts(self):
        counts: Dict[str, int] = {}
        total = 0
        manager = getattr(self._window, "vault_manager", None)
        if manager is None:
            return counts, 0
        try:
            entries = manager.list_entries()
        except Exception:
            return counts, 0
        for entry in entries:
            try:
                key = entry.get_entry_type()
            except Exception:
                continue
            counts[key] = counts.get(key, 0) + 1
            total += 1
        return counts, total

    def _build_header(self, t: Dict[str, str], total: int) -> None:
        card = RoundedSurface(self._wrap, radius=RADIUS["lg"], border=True)
        card.pack(fill=tk.X, pady=(0, SPACING["lg"]))
        body = card.body
        surface = t["surface"]
        tk.Label(
            body, text="Vault overview", font=font_role("display"), anchor=tk.W,
            bg=surface, fg=t["text"],
        ).pack(anchor=tk.W, padx=SPACING["lg"], pady=(SPACING["md"], 0))
        name = os.path.basename(self._window.vault_path or "") or "No vault"
        noun = "entry" if total == 1 else "entries"
        tk.Label(
            body, text=f"{name}  ·  {total} {noun}  ·  unlocked",
            font=font_role("caption"), anchor=tk.W, bg=surface, fg=t["muted"],
        ).pack(anchor=tk.W, padx=SPACING["lg"], pady=(SPACING["xs"], SPACING["md"]))

    def _build_tiles(self, t: Dict[str, str], counts: Dict[str, int]) -> None:
        grid = tk.Frame(self._wrap, bd=0, highlightthickness=0, bg=t["bg"])
        grid.pack(fill=tk.X)
        columns = 3
        for col in range(columns):
            grid.columnconfigure(col, weight=1, uniform="overview")
        for index, (nav_key, label, entry_type) in enumerate(OVERVIEW_CATEGORIES):
            self._tile(
                grid, t, nav_key, label, counts.get(entry_type, 0),
                index // columns, index % columns,
            )

    def _tile(self, parent, t, nav_key, label, count, row, col) -> None:
        tile = tk.Frame(
            parent, bd=0, highlightthickness=1,
            highlightbackground=t["border"], highlightcolor=t["border"],
            bg=t["surface"], cursor="hand2",
        )
        tile.grid(
            row=row, column=col, sticky="nsew",
            padx=(0 if col == 0 else SPACING["sm"], 0), pady=(0, SPACING["sm"]),
        )
        count_label = tk.Label(
            tile, text=str(count), font=font_role("display"), anchor=tk.W,
            bg=t["surface"], fg=t["accent"],
        )
        count_label.pack(anchor=tk.W, padx=SPACING["md"], pady=(SPACING["sm"], 0))
        name_label = tk.Label(
            tile, text=label, font=font_role("caption"), anchor=tk.W,
            bg=t["surface"], fg=t["muted"],
        )
        name_label.pack(anchor=tk.W, padx=SPACING["md"], pady=(0, SPACING["sm"]))
        parts = (tile, count_label, name_label)

        def _go(_e=None):
            self._window._on_nav(nav_key)

        def _enter(_e=None):
            for w in parts:
                w.configure(bg=t["hover"])
            tile.configure(highlightbackground=t["accent"], highlightcolor=t["accent"])

        def _leave(_e=None):
            for w in parts:
                w.configure(bg=t["surface"])
            tile.configure(highlightbackground=t["border"], highlightcolor=t["border"])

        for w in parts:
            w.bind("<Button-1>", _go)
            w.bind("<Enter>", _enter)
            w.bind("<Leave>", _leave)

    def _build_actions(self, t: Dict[str, str]) -> None:
        block = tk.Frame(self._wrap, bd=0, highlightthickness=0, bg=t["bg"])
        block.pack(fill=tk.X, pady=(SPACING["md"], 0))
        tk.Label(
            block, text="Quick actions", font=font_role("caption"), anchor=tk.W,
            bg=t["bg"], fg=t["muted"],
        ).pack(anchor=tk.W, pady=(0, SPACING["xs"]))
        bar = tk.Frame(block, bd=0, highlightthickness=0, bg=t["bg"])
        bar.pack(fill=tk.X)
        window = self._window
        actions = (
            ("Backup vault", window._backup_vault),
            ("Access log", window._show_access_log),
            ("Theme settings", window._theme_settings),
            ("Lock vault", window._lock_vault),
        )
        for label, command in actions:
            GhostButton(bar, text=label, command=command).pack(
                side=tk.LEFT, padx=(0, SPACING["sm"])
            )


class MainWindow:
    """Main application window (App Shell)."""

    # Themed (non-native looking) vertical scrollbar used by the content area.
    _SCROLLBAR_STYLE = "Content.Vertical.TScrollbar"

    def __init__(self):
        """Initialize main window."""
        self.root = tk.Tk()
        self.root.title("Faraday 3.0.0")

        # ---- custom window chrome ----------------------------------------
        # The OS title bar is removed; drag-to-move plus the minimize/close
        # controls live in the app's own bars (see _build_window_controls,
        # _bind_drag, _minimize_window). The root is painted with the theme
        # background so no white edge shows around the borderless window.
        self._borderless = True
        self._window_buttons: list = []
        self._drag_offset: Optional[tuple] = None
        self._maximized = False
        self._restore_geometry: Optional[str] = None
        self._restore_override_on_map = False
        self._sidebar_hidden = False
        # Re-entrancy guard for _fit_content_height (see that method).
        self._fitting = False
        self._theme_frames: list = []
        self._theme_labels: list = []
        try:
            self.root.overrideredirect(True)
        except Exception:
            self._borderless = False
        try:
            self.root.configure(bg=self._theme_tokens()["bg"])
        except Exception:
            pass

        self.root.geometry("1180x760")
        self.root.minsize(1024, 680)
        set_window_icon(self.root)
        self._ui_style = ttk.Style(self.root)
        self._themed_menus: list = []
        self._theme_merged = apply_saved_theme(self.root, self._ui_style)
        register_themed(self)
        self.vault_manager: Optional[VaultManager] = None
        self.vault_path = None
        self.tray_icon = None
        self._active_key: Optional[str] = None
        self._sections: Dict[str, object] = {}
        self._create_menus()
        apply_theme_to_popup_menus(self._themed_menus, self._theme_merged, root=self.root)
        self._create_widgets()
        if is_tray_available():
            self.tray_icon = TrayIcon(
                on_show=self._show_window,
                on_lock=self._lock_vault,
                on_exit=self._on_closing,
                on_toggle_console=toggle_console,
            )
            self.tray_icon.run()
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)
        self.root.bind("<Map>", self._on_root_map, add="+")
        self.apply_theme(self._theme_merged)
        # A borderless window is a tool window to Windows by default; restore
        # its taskbar button so minimize/restore from the taskbar still works.
        self._enable_taskbar_button()
        try:
            access_log.record("app_launched", source="gui")
        except Exception:
            pass

    # -------------------------------------------------------- window chrome
    def _hwnd(self) -> Optional[int]:
        """Return the native Win32 window handle of the root (or ``None``)."""
        if os.name != "nt":
            return None
        try:
            import ctypes

            self.root.update_idletasks()
            wid = self.root.winfo_id()
            parent = ctypes.windll.user32.GetParent(wid)
            return int(parent or wid)
        except Exception:
            return None

    def _enable_taskbar_button(self) -> None:
        """Give the borderless window a normal taskbar button (Windows)."""
        if not self._borderless or os.name != "nt":
            return
        hwnd = self._hwnd()
        if not hwnd:
            return
        try:
            import ctypes

            GWL_EXSTYLE = -20
            WS_EX_APPWINDOW = 0x00040000
            WS_EX_TOOLWINDOW = 0x00000080
            user32 = ctypes.windll.user32
            get_long = getattr(user32, "GetWindowLongPtrW", None) or user32.GetWindowLongW
            set_long = getattr(user32, "SetWindowLongPtrW", None) or user32.SetWindowLongW
            get_long.restype = ctypes.c_ssize_t
            get_long.argtypes = [ctypes.c_void_p, ctypes.c_int]
            set_long.restype = ctypes.c_ssize_t
            set_long.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_ssize_t]
            handle = ctypes.c_void_p(hwnd)
            style = get_long(handle, GWL_EXSTYLE)
            style = (style & ~WS_EX_TOOLWINDOW) | WS_EX_APPWINDOW
            set_long(handle, GWL_EXSTYLE, style)
            # The style change only takes effect after the window is re-shown.
            self.root.withdraw()
            self.root.after(10, self.root.deiconify)
        except Exception:
            pass

    def _minimize_window(self) -> None:
        """Minimize to the taskbar (works without an OS title bar)."""
        hwnd = self._hwnd()
        if hwnd:
            try:
                import ctypes

                ctypes.windll.user32.ShowWindow(ctypes.c_void_p(hwnd), 6)  # SW_MINIMIZE
                return
            except Exception:
                pass
        try:
            if self._borderless:
                # iconify() is refused for override-redirect windows; drop the
                # flag for the duration of the minimize and restore it on map.
                self.root.overrideredirect(False)
                self._restore_override_on_map = True
            self.root.iconify()
        except Exception:
            pass

    def _on_root_map(self, event=None) -> None:
        """Re-arm borderless mode after a fallback (non-native) minimize."""
        if event is not None and event.widget is not self.root:
            return
        if not self._restore_override_on_map:
            return
        self._restore_override_on_map = False
        try:
            self.root.overrideredirect(True)
        except Exception:
            pass

    def _style_window_button(self, btn: tk.Button, danger: bool, tokens=None) -> None:
        """Paint a window control and (re)bind its hover state."""
        t = tokens or self._theme_tokens()
        base_bg, base_fg = t["bg"], t["text"]
        hover_bg = t["danger"] if danger else t["hover"]
        hover_fg = t["on_accent"] if danger else t["text"]
        try:
            btn.configure(
                bg=base_bg, fg=base_fg,
                activebackground=hover_bg, activeforeground=hover_fg,
                highlightbackground=base_bg,
            )
        except tk.TclError:
            return
        btn.bind("<Enter>", lambda _e, b=btn: b.configure(bg=hover_bg, fg=hover_fg))
        btn.bind("<Leave>", lambda _e, b=btn: b.configure(bg=base_bg, fg=base_fg))

    def _window_button(self, parent, text: str, command, danger: bool = False) -> tk.Button:
        """Create a flat, square window control button (minimize/close)."""
        btn = tk.Button(
            parent, text=text, command=command,
            bd=0, relief=tk.FLAT, highlightthickness=0, takefocus=0,
            width=3, height=1, padx=0, pady=0, cursor="hand2",
            font=font_role("body"),
        )
        self._style_window_button(btn, danger)
        self._window_buttons.append((btn, danger))
        return btn

    def _build_window_controls(self, bar) -> None:
        """Pack minimize + close at the far right of ``bar``."""
        close_btn = self._window_button(bar, "✕", self._on_closing, danger=True)
        close_btn.pack(side=tk.RIGHT, padx=(0, SPACING["xs"]), pady=SPACING["xs"])
        min_btn = self._window_button(bar, "–", self._minimize_window)
        min_btn.pack(side=tk.RIGHT, padx=0, pady=SPACING["xs"])

    # Widget classes that must keep their own click behaviour (never drag).
    _DRAG_IGNORE = ("button", "entry", "text", "listbox", "scrollbar", "combobox", "checkbutton", "radiobutton")

    def _bind_drag(self, widget) -> None:
        """Make ``widget`` a drag handle that repositions the window."""
        widget.bind("<ButtonPress-1>", self._on_drag_start, add="+")
        widget.bind("<B1-Motion>", self._on_drag_motion, add="+")
        widget.bind("<ButtonRelease-1>", self._on_drag_end, add="+")
        widget.bind("<Double-Button-1>", self._on_drag_double, add="+")

    def _drag_allowed(self, widget) -> bool:
        try:
            cls = widget.winfo_class().lower()
        except Exception:
            return False
        return not any(token in cls for token in self._DRAG_IGNORE)

    def _on_drag_start(self, event) -> None:
        if not self._drag_allowed(event.widget):
            self._drag_offset = None
            return
        try:
            self._drag_offset = (
                event.x_root - self.root.winfo_x(),
                event.y_root - self.root.winfo_y(),
            )
        except Exception:
            self._drag_offset = None

    def _on_drag_motion(self, event) -> None:
        if not self._drag_offset:
            return
        if self._maximized:
            # Dragging a maximized window restores it and keeps it under the
            # cursor (the restored window is narrower, so clamp the offset).
            self._toggle_maximize()
            try:
                self.root.update_idletasks()
                limit = max(40, self.root.winfo_width() - 40)
            except Exception:
                limit = self._drag_offset[0]
            self._drag_offset = (min(self._drag_offset[0], limit), self._drag_offset[1])
        dx, dy = self._drag_offset
        try:
            self.root.geometry(f"+{event.x_root - dx}+{event.y_root - dy}")
        except Exception:
            pass

    def _on_drag_end(self, _event=None) -> None:
        self._drag_offset = None

    def _on_drag_double(self, event) -> None:
        """Double-clicking the drag area maximizes/restores the window."""
        if not self._drag_allowed(event.widget):
            return
        self._drag_offset = None
        self._toggle_maximize()

    def _work_area(self):
        """Return the usable screen rect (x, y, w, h), excluding the taskbar."""
        width = self.root.winfo_screenwidth()
        height = self.root.winfo_screenheight()
        if os.name == "nt":
            try:
                import ctypes
                from ctypes import wintypes

                rect = wintypes.RECT()
                if ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0):
                    return (
                        rect.left, rect.top,
                        rect.right - rect.left, rect.bottom - rect.top,
                    )
            except Exception:
                pass
        return (0, 0, width, height)

    def _toggle_maximize(self) -> None:
        if self._maximized:
            geometry = self._restore_geometry or "1180x760+80+60"
            self._maximized = False
            try:
                self.root.geometry(geometry)
            except Exception:
                pass
            return
        try:
            self._restore_geometry = self.root.geometry()
            x, y, w, h = self._work_area()
            self.root.geometry(f"{w}x{h}+{x}+{y}")
            self._maximized = True
        except Exception:
            self._maximized = False

    # ------------------------------------------------------------------ menu
    def _create_menus(self):
        """Build the File/Security/Theme/Help menus as a themed popup menu.

        The old native menubar strip is gone; the same actions live under a
        "More" hamburger :class:`IconButton` in the Topbar (see
        :meth:`_build_topbar` / :meth:`_open_more_menu`). The submenus are kept
        as real ``tk.Menu`` objects so cascade grouping and theming still work.
        """
        self._themed_menus = []

        def reg(m: tk.Menu) -> tk.Menu:
            self._themed_menus.append(m)
            return m

        self.file_menu = reg(tk.Menu(self.root, tearoff=0))
        self.file_menu.add_command(label="New Vault", command=self._new_vault)
        self.file_menu.add_command(label="Open Vault", command=self._open_vault)
        self.recent_menu = reg(tk.Menu(self.file_menu, tearoff=0))
        self.file_menu.add_cascade(label="Recent Vaults", menu=self.recent_menu)
        self._update_recent_menu()
        self.file_menu.add_separator()
        self.file_menu.add_command(label="Backup Vault", command=self._backup_vault, state=tk.DISABLED)
        self.file_menu.add_separator()
        self.file_menu.add_command(label="Lock Vault", command=self._lock_vault, state=tk.DISABLED)
        self.file_menu.add_separator()
        self.file_menu.add_command(label="Exit", command=self._on_closing)

        self.security_menu = reg(tk.Menu(self.root, tearoff=0))
        self.security_menu.add_command(label="Set up action PIN", command=lambda: menu_enable_or_change_action_pin(self.root))
        self.security_menu.add_command(label="Change action PIN", command=lambda: menu_change_action_pin(self.root))
        self.security_menu.add_command(label="Disable action PIN", command=lambda: menu_disable_action_pin(self.root))
        self.security_menu.add_separator()
        self.security_menu.add_command(label="View access log…", command=self._show_access_log)

        self.theme_menu = reg(tk.Menu(self.root, tearoff=0))
        self.theme_menu.add_command(label="Theme settings", command=self._theme_settings)
        self.theme_presets = reg(tk.Menu(self.theme_menu, tearoff=0))
        self.theme_menu.add_cascade(label="Quick preset", menu=self.theme_presets)
        for preset_id, preset_label in PRESET_LABELS:
            self.theme_presets.add_command(
                label=preset_label,
                command=lambda p=preset_id: self._quick_theme_preset(p),
            )

        self.help_menu = reg(tk.Menu(self.root, tearoff=0))
        self.help_menu.add_command(label="GitHub", command=self._open_github)
        self.help_menu.add_command(label="Discord", command=self._open_discord)
        self.help_menu.add_separator()
        self.help_menu.add_command(label="About", command=self._show_about)

        # Top-level "More" popup that groups the four menus above.
        self._more_menu = reg(tk.Menu(self.root, tearoff=0))
        self._more_menu.add_cascade(label="File", menu=self.file_menu)
        self._more_menu.add_cascade(label="Security", menu=self.security_menu)
        self._more_menu.add_cascade(label="Theme", menu=self.theme_menu)
        self._more_menu.add_cascade(label="Help", menu=self.help_menu)

    def _open_more_menu(self):
        """Post the aggregated File/Security/Theme/Help popup below the hamburger."""
        try:
            btn = self._more_btn
            x = btn.winfo_rootx()
            y = btn.winfo_rooty() + btn.winfo_height()
            self._more_menu.tk_popup(x, y)
        except Exception:
            pass

    # --------------------------------------------------------------- helpers
    def _theme_tokens(self) -> Dict[str, str]:
        """Return the current semantic design tokens, with a dark fallback."""
        try:
            return build_tokens(get_active_merged())
        except Exception:
            return {
                "bg": "#1e1e1e", "bg_elev": "#252526", "border": "#3c3c3c",
                "text": "#d4d4d4", "muted": "#9d9d9d", "accent": "#3b82f6",
                "danger": "#f87171", "surface": "#252526", "hover": "#2b2b2c",
                "on_accent": "#ffffff",
            }

    def apply_theme(self, merged):
        """Recolor the large background surfaces when the theme changes.

        These widgets were painted from build tokens at build time only, so a
        light->dark preset switch otherwise leaves white boxes in a dark theme.
        The locked screen is rebuilt outright because its card content (recent
        rows, headings) is painted with plain ``tk`` colors at build time.
        """
        from .design_system import build_tokens
        t = build_tokens(merged)
        bg = t["bg"]
        # The borderless root is visible around/behind everything: paint it or
        # a white edge shows where no child covers it.
        try:
            self.root.configure(bg=bg)
        except Exception:
            pass
        for name in ("content_canvas", "content_inner", "_locked_frame",
                     "_locked_stage", "_sidebar_footer", "_sidebar_footer_row"):
            w = getattr(self, name, None)
            if w is not None:
                try:
                    w.configure(bg=bg)
                except Exception:
                    pass
        # Surfaces that live ON a card must use the elevated surface color,
        # otherwise they punch a window-background hole through the card.
        recent_list = getattr(self, "_recent_list", None)
        if recent_list is not None:
            try:
                recent_list.configure(bg=t["surface"])
            except Exception:
                pass
        for frame in list(getattr(self, "_theme_frames", []) or []):
            try:
                frame.configure(bg=bg)
            except Exception:
                pass
        # re-color direct labels living on those surfaces
        for lbl in getattr(self, "_theme_labels", []):
            try:
                lbl.configure(bg=bg)
            except Exception:
                pass
        # window controls (minimize/close) are plain tk buttons
        self._restyle_window_buttons(t)
        # repaint the content scrollbar from the new tokens (it uses a derived
        # style so it never falls back to the OS native look)
        scroll = getattr(self, "content_scroll", None)
        if scroll is not None:
            try:
                scroll.configure(style=self._scrollbar_style(t))
            except Exception:
                pass
        self._rebuild_locked_screen_for_theme()

    def _restyle_window_buttons(self, tokens=None) -> None:
        """Repaint the minimize/close controls and drop destroyed ones."""
        alive = []
        for btn, danger in list(getattr(self, "_window_buttons", [])):
            try:
                if not btn.winfo_exists():
                    continue
            except Exception:
                continue
            self._style_window_button(btn, danger, tokens)
            alive.append((btn, danger))
        self._window_buttons = alive

    def _rebuild_locked_screen_for_theme(self) -> None:
        """Rebuild the UnlockScreen so its tk-painted content follows the theme."""
        frame = getattr(self, "_locked_frame", None)
        if frame is None:
            return
        try:
            if not frame.winfo_exists():
                return
        except Exception:
            return
        if self.vault_manager is not None:
            return
        try:
            self._show_locked_screen()
        except Exception:
            pass

    # --------------------------------------------------------------- widgets
    def _create_widgets(self):
        """Create the body container and show the locked screen."""
        self.status_var = tk.StringVar(value="Vault not loaded")
        self._body = ttk.Frame(self.root)
        self._body.pack(fill=tk.BOTH, expand=True)
        self._show_locked_screen()

    # --------------------------------------------------------- locked screen
    def _show_locked_screen(self):
        """Tear down any unlocked UI and present the UnlockScreen.

        The window has no OS title bar, so the locked screen gets its own slim
        chrome row (drag area + minimize/close) above the card stage. The card
        is centered in the stage (``place`` with ``relx/rely=0.5`` +
        ``anchor=center``) and given an explicit size so its drawn rounded
        background is actually rendered.
        """
        self._clear_body()
        t = self._theme_tokens()
        bg = t["bg"]
        surface = t["surface"]

        self._locked_frame = tk.Frame(self._body, bg=bg)
        self._locked_frame.pack(fill=tk.BOTH, expand=True)

        # Window chrome (the OS title bar is gone; see __init__).
        chrome = tk.Frame(self._locked_frame, bd=0, highlightthickness=0, bg=bg)
        chrome.pack(side=tk.TOP, fill=tk.X)
        chrome_title = tk.Label(
            chrome, text="Faraday", font=font_role("caption"), anchor=tk.W,
            bg=bg, fg=t["muted"],
        )
        chrome_title.pack(side=tk.LEFT, padx=SPACING["md"], pady=SPACING["xs"])
        self._build_window_controls(chrome)
        for handle in (chrome, chrome_title):
            self._bind_drag(handle)

        # Stage: everything below the chrome row; the card is centered in it.
        self._locked_stage = tk.Frame(self._locked_frame, bd=0, highlightthickness=0, bg=bg)
        self._locked_stage.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        card = RoundedSurface(self._locked_stage, radius=RADIUS["lg"], border=True)
        card.configure(width=420, height=540)
        card.place(relx=0.5, rely=0.5, anchor=tk.CENTER)
        body = card.body

        tk.Label(
            body, text="Faraday", font=font_role("display"), anchor=tk.W,
            bg=surface, fg=t["text"],
        ).pack(anchor=tk.W, padx=SPACING["lg"], pady=(SPACING["lg"], 0))
        tk.Label(
            body, text="Sign in to your vault", font=font_role("caption"), anchor=tk.W,
            bg=surface, fg=t["muted"],
        ).pack(anchor=tk.W, padx=SPACING["lg"], pady=(SPACING["xs"], SPACING["md"]))

        tk.Label(
            body, text="Recent Vaults", font=font_role("title"), anchor=tk.W,
            bg=surface, fg=t["text"],
        ).pack(anchor=tk.W, padx=SPACING["lg"], pady=(SPACING["md"], SPACING["sm"]))

        # The action row is packed BEFORE the (expanding) list so the card's
        # fixed height is reserved for it first: with many recent vaults the
        # list used to eat the whole card and shove these buttons out of it.
        btn_row = tk.Frame(body, bd=0, highlightthickness=0, bg=surface)
        btn_row.pack(side=tk.BOTTOM, fill=tk.X, padx=SPACING["lg"],
                     pady=(SPACING["md"], SPACING["lg"]))
        PrimaryButton(btn_row, text="Open Vault", command=self._open_vault).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=(0, SPACING["sm"])
        )
        PrimaryButton(btn_row, text="New Vault", command=self._new_vault).pack(
            side=tk.LEFT, fill=tk.X, expand=True
        )

        self._recent_list = tk.Frame(body, bd=0, highlightthickness=0, bg=surface)
        self._recent_list.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=SPACING["lg"])
        self._populate_recent_list()

        # NOTE: no access-log entry point here on purpose — the log is only
        # reachable from inside an unlocked vault (Security ▸ View access log…).

    def _populate_recent_list(self):
        """Render the recent vaults list inside the UnlockScreen.

        Capped at :data:`MAX_RECENT_ROWS`: the card has a fixed height, so a
        longer list overflowed it (clipped/overlapping rows) instead of
        scrolling. Any surplus is summarized in a muted footer line.
        """
        for w in list(self._recent_list.winfo_children()):
            try:
                w.destroy()
            except Exception:
                pass
        t = self._theme_tokens()
        recent = load_recent_vaults(max_items=10)
        if not recent:
            EmptyState(
                self._recent_list,
                message="No recent vaults. Create or open one to begin.",
                icon_name="vault",
            ).pack(fill=tk.BOTH, expand=True)
            return
        for path in recent[:MAX_RECENT_ROWS]:
            self._recent_row(self._recent_list, path)
        surplus = len(recent) - MAX_RECENT_ROWS
        if surplus > 0:
            tk.Label(
                self._recent_list,
                text=f"+{surplus} more in More ▸ File ▸ Recent Vaults",
                font=font_role("caption"), anchor=tk.W,
                bg=t["surface"], fg=t["muted"],
            ).pack(anchor=tk.W, pady=(SPACING["xs"], 0))

    def _recent_row(self, parent, path):
        """One themed, hoverable recent-vault row.

        The "open" hint is packed FIRST (to the right) so a long filename can
        no longer squeeze it out of the row, and the name is ellipsized to keep
        every row exactly one line tall.
        """
        t = self._theme_tokens()
        surface = t["surface"]
        exists = os.path.exists(path)
        row = tk.Frame(
            parent, bd=0, highlightthickness=1,
            highlightbackground=t["border"], highlightcolor=t["border"],
            bg=surface, cursor="hand2",
        )
        row.pack(fill=tk.X, pady=(0, SPACING["xs"]))
        hint = tk.Label(
            row, text="open" if exists else "missing", font=font_role("caption"),
            anchor=tk.E, bg=surface, fg=t["muted"] if exists else t["danger"],
        )
        hint.pack(side=tk.RIGHT, padx=(SPACING["sm"], SPACING["md"]))
        filename = os.path.basename(path) or path
        if len(filename) > 30:
            filename = filename[:29] + "…"
        name = tk.Label(
            row, text=filename, font=font_role("body"), anchor=tk.W,
            bg=surface, fg=t["text"] if exists else t["muted"],
        )
        name.pack(side=tk.LEFT, fill=tk.X, expand=True,
                  padx=(SPACING["md"], 0), pady=SPACING["sm"])
        parts = (row, name, hint)

        def _open(_e=None):
            self._open_recent_vault(path)

        def _enter(_e=None):
            for w in parts:
                w.configure(bg=t["hover"])
            row.configure(highlightbackground=t["accent"], highlightcolor=t["accent"])

        def _leave(_e=None):
            for w in parts:
                w.configure(bg=surface)
            row.configure(highlightbackground=t["border"], highlightcolor=t["border"])

        for w in parts:
            w.bind("<Button-1>", _open)
            w.bind("<Enter>", _enter)
            w.bind("<Leave>", _leave)

    # ------------------------------------------------------- unlocked screen
    def _setup_unlocked_ui(self):
        """Build the sidebar + topbar + scrollable content and host sections."""
        self._clear_body()
        self.status_var.set(f"Vault: {os.path.basename(self.vault_path)}")

        self._app_frame = ttk.Frame(self._body)
        self._app_frame.pack(fill=tk.BOTH, expand=True)

        # Sidebar: fix its requested width so pack_propagate doesn't shrink it
        # to its children. The hamburger hides/shows the whole rail (see
        # ``_set_sidebar_hidden``), so it starts visible and expanded.
        self.sidebar = Sidebar(
            self._app_frame,
            items=NAV_ITEMS,
            on_select=self._on_nav,
            app_name="Faraday",
            subtitle="Secure Vault",
            width=SIDEBAR_WIDTH,
            collapsed_width=SIDEBAR_WIDTH_COLLAPSED,
        )
        # Alias kept so every collapse/reflow helper refers to one attribute.
        self._sidebar = self.sidebar
        self.sidebar.pack(side=tk.LEFT, fill=tk.Y)
        self.sidebar.pack_propagate(False)
        self._sidebar_hidden = False
        self._build_sidebar_footer()

        # 1px themed separator between the sidebar and the content column,
        # drawn with the `border` token via TSeparator so it recolors live.
        # Kept as an attribute: it must be hidden together with the sidebar.
        self._sidebar_sep = ttk.Separator(self._app_frame, orient=tk.VERTICAL)
        self._sidebar_sep.pack(side=tk.LEFT, fill=tk.Y)

        # Main column
        self._main_col = ttk.Frame(self._app_frame)
        self._main_col.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._build_topbar()
        self._build_content_area()
        self._build_sections()
        # The sections just changed the scrollable content, so re-measure it
        # explicitly rather than relying only on the <Configure> bindings.
        self._fit_content_height()

        # Status bar
        ttk.Label(
            self._main_col, textvariable=self.status_var, anchor=tk.W,
            padding=(SPACING["sm"], SPACING["xs"]),
        ).pack(side=tk.BOTTOM, fill=tk.X)

        self.sidebar.set_active(HOME_KEY)
        self._on_nav(HOME_KEY)

    def _build_sidebar_footer(self):
        """Community links pinned to the bottom of the sidebar.

        Packed with ``side=BOTTOM`` on the sidebar itself, so it is hidden and
        restored together with the rail and never interferes with the nav list.
        """
        t = self._theme_tokens()
        self._sidebar_footer = tk.Frame(
            self.sidebar, bd=0, highlightthickness=0, bg=t["bg"]
        )
        self._sidebar_footer.pack(
            side=tk.BOTTOM, fill=tk.X, padx=SPACING["xs"], pady=(0, SPACING["sm"])
        )
        ttk.Separator(self._sidebar_footer, orient=tk.HORIZONTAL).pack(
            side=tk.TOP, fill=tk.X, pady=(0, SPACING["xs"])
        )
        self._sidebar_footer_row = tk.Frame(
            self._sidebar_footer, bd=0, highlightthickness=0, bg=t["bg"]
        )
        self._sidebar_footer_row.pack(side=tk.TOP, fill=tk.X)
        # No icon PNGs ship with the app, so these render as text buttons.
        IconButton(
            self._sidebar_footer_row, icon_name=None, text_fallback="GitHub",
            command=self._open_github,
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, SPACING["xs"] // 2))
        IconButton(
            self._sidebar_footer_row, icon_name=None, text_fallback="Discord",
            command=self._open_discord,
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(SPACING["xs"] // 2, 0))

    def _build_topbar(self):
        bar = ttk.Frame(self._main_col)
        bar.pack(side=tk.TOP, fill=tk.X)
        self._topbar = bar

        IconButton(bar, icon_name="menu", text_fallback="≡", command=self._toggle_sidebar).pack(
            side=tk.LEFT, padx=SPACING["sm"], pady=SPACING["sm"]
        )

        t = self._theme_tokens()
        self._title_label = ttk.Label(bar, text=NAV_TITLES[HOME_KEY], font=font_role("title"))
        self._title_label.pack(side=tk.LEFT, padx=SPACING["md"], pady=SPACING["sm"])

        vault_name = os.path.basename(self.vault_path)
        if len(vault_name) > 28:
            vault_name = vault_name[:25] + "…"
        self._vault_name_label = ttk.Label(
            bar, text=vault_name, font=font_role("caption"),
            foreground=t["muted"],
        )
        self._vault_name_label.pack(side=tk.LEFT, padx=SPACING["sm"], pady=SPACING["sm"])

        # Spacer (expanding) keeps the title/vault name pinned left and pushes
        # the search bar + action icons to the right, so a long vault name
        # can never shove the Lock/Theme/More buttons off-screen.
        spacer = ttk.Frame(bar, width=0)
        spacer.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.search_bar = SearchBar(bar, on_change=self._on_search, placeholder="Search this view…")
        self.search_bar.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=SPACING["sm"], pady=SPACING["sm"])
        self.search_bar.configure(width=24)

        IconButton(bar, icon_name="lock", text_fallback="Lock", command=self._lock_vault).pack(
            side=tk.LEFT, padx=SPACING["sm"], pady=SPACING["sm"]
        )
        IconButton(bar, icon_name="settings", text_fallback="Theme", command=self._theme_settings).pack(
            side=tk.LEFT, padx=SPACING["sm"], pady=SPACING["sm"]
        )

        # "More" hamburger: aggregates File/Security/Theme/Help (the old native
        # menubar) into a themed popup so the chrome stays minimalist.
        self._more_btn = IconButton(bar, icon_name="more", text_fallback="More", command=self._open_more_menu)
        self._more_btn.pack(side=tk.LEFT, padx=SPACING["sm"], pady=SPACING["sm"])

        # Window controls replace the removed OS title bar: far right, after
        # the More button. The bar itself (and its inert labels) drag the
        # window; clicks on buttons/entries keep their own behaviour.
        self._build_window_controls(bar)
        for handle in (bar, spacer, self._title_label, self._vault_name_label):
            self._bind_drag(handle)

        # Clean 1px divider under the topbar (themed via TSeparator/border).
        ttk.Separator(self._main_col, orient=tk.HORIZONTAL).pack(
            side=tk.TOP, fill=tk.X
        )

    def _scrollbar_style(self, tokens: Optional[Dict[str, str]] = None) -> str:
        """Return the name of a themed, arrow-less vertical scrollbar style.

        The stock ttk scrollbar reads as the OS native widget; this derives a
        slim, flat variant painted from the active design tokens. Falls back to
        the (already themed) ``Vertical.TScrollbar`` if the active ttk theme
        does not expose the clam scrollbar elements.
        """
        t = tokens or self._theme_tokens()
        name = self._SCROLLBAR_STYLE
        try:
            self._ui_style.layout(
                name,
                [(
                    "Vertical.Scrollbar.trough",
                    {
                        "sticky": "ns",
                        "children": [
                            ("Vertical.Scrollbar.thumb", {"expand": "1", "sticky": "nswe"}),
                        ],
                    },
                )],
            )
        except tk.TclError:
            return "Vertical.TScrollbar"
        try:
            self._ui_style.configure(
                name,
                background=t["border"],
                troughcolor=t["bg"],
                bordercolor=t["bg"],
                darkcolor=t["border"],
                lightcolor=t["border"],
                arrowcolor=t["text"],
                relief=tk.FLAT,
                borderwidth=0,
                width=10,
                gripcount=0,
            )
            self._ui_style.map(
                name,
                background=[("pressed", t["accent"]), ("active", t["accent"])],
            )
        except tk.TclError:
            pass
        return name

    def _build_content_area(self):
        try:
            bg = build_tokens(get_active_merged())["bg"]
        except Exception:
            bg = self._theme_tokens()["bg"]

        # The canvas + scrollbar get their own wrapper so the scrollbar sits
        # flush against the window's right edge while the status bar can still
        # span the full width underneath them.
        self._content_wrap = ttk.Frame(self._main_col)
        self._content_wrap.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        self.content_canvas = tk.Canvas(
            self._content_wrap, highlightthickness=0, bd=0, bg=bg
        )
        self.content_scroll = ttk.Scrollbar(
            self._content_wrap,
            orient=tk.VERTICAL,
            command=self.content_canvas.yview,
            style=self._scrollbar_style(),
        )
        self.content_canvas.configure(yscrollcommand=self.content_scroll.set)
        self.content_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.content_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # Thin re-open rail shown at the TOP-LEFT of the content area while the
        # sidebar is hidden (created unpacked; see ``_show_sidebar_reopen``).
        self._sidebar_reopen = IconButton(
            self._content_wrap, icon_name=None, text_fallback="☰",
            command=self._toggle_sidebar,
        )

        self.content_inner = tk.Frame(self.content_canvas, bg=bg)
        self._canvas_win = self.content_canvas.create_window(
            (0, 0), window=self.content_inner, anchor=tk.NW
        )
        self.content_canvas.bind("<Configure>", self._on_canvas_configure)
        self.content_inner.bind("<Configure>", lambda _e: self._fit_content_height())
        self.content_canvas.bind("<MouseWheel>", self._on_mousewheel)
        self.content_inner.bind("<MouseWheel>", self._on_mousewheel)
        self._fitting = False

    def _on_canvas_configure(self, event):
        # Stretch the inner window to the full canvas width so the active
        # section fills the window horizontally. Setting the item width does
        # not resize the canvas itself, so this cannot re-trigger this handler.
        self.content_canvas.itemconfig(self._canvas_win, width=event.width)
        self._fit_content_height()

    def _fit_content_height(self):
        """Size the inner window to fill the canvas vertically, but never
        smaller than its content so tall sections can still scroll.

        Re-entrancy guard: this method resizes the canvas window item, which
        makes Tk emit ``<Configure>`` on ``content_inner`` (and possibly the
        canvas). Both events are bound back to this method, so a layout that
        did not converge would re-enter here forever and wedge the Tk event
        loop -- an unresponsive window that can only be force-quit. The flag
        makes that impossible. Dropping a nested call is safe: the outermost
        call still completes the sizing, and it reads the freshest geometry.
        """
        if self._fitting:
            return
        self._fitting = True
        canvas = self.content_canvas
        try:
            canvas_h = canvas.winfo_height()
            inner_h = self.content_inner.winfo_reqheight()
            height = max(canvas_h, inner_h)
            canvas.itemconfig(self._canvas_win, height=height)
            canvas.configure(scrollregion=canvas.bbox("all"))
        except Exception:
            pass
        finally:
            self._fitting = False

    def _on_mousewheel(self, event):
        try:
            self.content_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        except Exception:
            pass

    def _build_sections(self):
        """Instantiate every section view into the content area.

        Sections are constructed with their CURRENT signatures (verified
        against the existing files): most take ``(parent, vault_manager)``;
        ``ThreatModelPanel`` also accepts ``vault_path``. ``MainWindow``
        forwards ``vault_path`` only when the constructor accepts it, which is
        also the Phase-4 contract.
        """
        parent = self.content_inner
        self._sections = {}

        # Home dashboard (no section class): counts + quick actions.
        self._overview = _OverviewView(parent, self)
        self._sections[HOME_KEY] = self._overview

        self.credential_section = self._make_section(CredentialSection, parent)
        self.crypto_section = self._make_section(CryptoSection, parent)
        self.secure_note_section = self._make_section(SecureNoteSection, parent)
        self.card_section = self._make_section(CardSection, parent)
        self.identity_section = self._make_section(IdentitySection, parent)
        self.emergency_contact_section = self._make_section(EmergencyContactSection, parent)
        self.two_factor_section = self._make_section(TwoFactorSection, parent)
        self.api_key_section = self._make_section(ApiKeySection, parent)
        self.wifi_section = self._make_section(WifiSection, parent)
        self.document_section = self._make_section(DocumentSection, parent)
        self.threat_panel = self._make_section(ThreatModelPanel, parent)

        self._sections["credentials"] = self.credential_section
        self._sections["crypto"] = self.crypto_section
        self._sections["notes"] = self.secure_note_section
        self._sections["cards"] = self.card_section
        self._sections["identity"] = self.identity_section
        self._sections["emergency"] = self.emergency_contact_section
        self._sections["security"] = self.two_factor_section
        self._sections["api"] = self.api_key_section
        self._sections["wifi"] = self.wifi_section
        self._sections["documents"] = self.document_section
        self._sections["threat"] = self.threat_panel

        # Refresh each view once on unlock (refresh() in Phase 4, or the
        # current private _refresh_list() fallback).
        for view in self._sections.values():
            if hasattr(view, "refresh"):
                try:
                    view.refresh()
                except Exception:
                    pass
            elif hasattr(view, "_refresh_list"):
                try:
                    view._refresh_list()
                except Exception:
                    pass

    def _make_section(self, cls, parent):
        params = inspect.signature(cls.__init__).parameters
        if len(params) >= 3:
            return cls(parent, self.vault_manager, self.vault_path)
        return cls(parent, self.vault_manager)

    # ------------------------------------------------------------- nav logic
    def _on_nav(self, key):
        self.sidebar.set_active(key)
        self._title_label.configure(text=NAV_TITLES.get(key, NAV_TITLES[HOME_KEY]))
        if getattr(self, "search_bar", None) is not None:
            try:
                self.search_bar.set("")
            except Exception:
                pass
        for view in self._sections.values():
            try:
                view.frame.pack_forget()
            except Exception:
                pass
        view = self._sections.get(key)
        if view is None:
            return
        # The dashboard counts entries, so recompute them every time it is
        # opened (entries may have been added/removed in another section).
        if key == HOME_KEY:
            try:
                view.refresh()
            except Exception:
                pass
        view.frame.pack(fill=tk.BOTH, expand=True)
        self._active_key = key
        # Swapping the visible view changes the content height, so re-fit the
        # scroll area explicitly (keeps scrolling correct even if a nested
        # <Configure> was dropped by the re-entrancy guard).
        self._fit_content_height()

    def _on_search(self, query):
        view = self._sections.get(self._active_key)
        if view is not None and hasattr(view, "filter"):
            try:
                view.filter(query)
            except Exception:
                pass

    def _toggle_sidebar(self):
        """Hide/show the sidebar entirely (hamburger action)."""
        sidebar = getattr(self, "_sidebar", None)
        if sidebar is None:
            return
        try:
            if not sidebar.winfo_exists():
                return
        except Exception:
            return
        self._set_sidebar_hidden(not self._sidebar_hidden)

    def _set_sidebar_hidden(self, hidden: bool):
        """Fully remove the rail from the layout (or put it back).

        Narrowing the frame to an icons-only rail still left a visible strip,
        which is not what the hamburger promises, so the sidebar (and its
        separator) is now ``pack_forget``-ed outright and a thin "☰" button
        appears at the top-left of the content area to bring it back.
        """
        sidebar = getattr(self, "_sidebar", None)
        if sidebar is None:
            return
        separator = getattr(self, "_sidebar_sep", None)
        main_col = getattr(self, "_main_col", None)
        if hidden:
            try:
                sidebar.pack_forget()
            except Exception:
                pass
            if separator is not None:
                try:
                    separator.pack_forget()
                except Exception:
                    pass
        else:
            try:
                # Restore the original left-to-right order: rail, separator,
                # main column (``before`` keeps it independent of pack order).
                if separator is not None and main_col is not None:
                    separator.pack(side=tk.LEFT, fill=tk.Y, before=main_col)
                anchor = separator if separator is not None else main_col
                if anchor is not None:
                    sidebar.pack(side=tk.LEFT, fill=tk.Y, before=anchor)
                else:
                    sidebar.pack(side=tk.LEFT, fill=tk.Y)
                sidebar.pack_propagate(False)
                sidebar.configure(width=SIDEBAR_WIDTH)
                if sidebar.is_collapsed():
                    sidebar.expand()
            except Exception:
                pass
        self._sidebar_hidden = bool(hidden)
        self._show_sidebar_reopen(self._sidebar_hidden)
        try:
            self.root.update_idletasks()
        except Exception:
            pass
        self._reflow_content()

    def _show_sidebar_reopen(self, show: bool):
        """Show/hide the thin "☰" re-open button in the content area."""
        btn = getattr(self, "_sidebar_reopen", None)
        canvas = getattr(self, "content_canvas", None)
        if btn is None or canvas is None:
            return
        try:
            if not btn.winfo_exists():
                return
            if show:
                btn.pack(
                    side=tk.LEFT, anchor=tk.N,
                    padx=(SPACING["xs"], 0), pady=SPACING["xs"],
                    before=canvas,
                )
            else:
                btn.pack_forget()
        except Exception:
            pass

    def _reflow_content(self):
        """Re-stretch the scrollable content to the current canvas width."""
        canvas = getattr(self, "content_canvas", None)
        if canvas is None:
            return
        try:
            canvas.itemconfig(self._canvas_win, width=canvas.winfo_width())
        except Exception:
            pass
        self._fit_content_height()

    # ------------------------------------------------------ community links
    def _open_url(self, url: str) -> None:
        """Open ``url`` in the user's default browser."""
        try:
            webbrowser.open_new_tab(url)
        except Exception:
            messagebox.showerror("Open link", f"Could not open the browser.\n\n{url}")

    def _open_github(self) -> None:
        self._open_url(GITHUB_URL)

    def _open_discord(self) -> None:
        self._open_url(DISCORD_URL)

    # ----------------------------------------------------------- vault flows
    def _prompt_password(self, title, prompt, confirm=False, show_generate=True):
        """Delegate the master-password prompt to the themed dialog flow.

        ``show_generate`` is ``False`` when unlocking an EXISTING vault (no
        generator needed) and ``True`` when creating a NEW vault.
        """
        dlg = ThemedPasswordDialog(
            self.root, title=title, prompt=prompt, confirm=confirm,
            show_generate=show_generate,
        )
        self.root.wait_window(dlg)
        return dlg.result

    def _new_vault(self):
        """Create a new vault."""
        # ask_save_as_filename (not filedialog directly): the borderless window
        # can otherwise cover the native dialog and the app looks frozen.
        vault_path = ask_save_as_filename(
            self.root,
            title="Create New Vault",
            defaultextension=".vault",
            initialdir=get_vaults_directory(),
            filetypes=[("Vault files", "*.vault"), ("All files", "*.*")],
        )
        if not vault_path:
            return
        if os.path.exists(vault_path) and not messagebox.askyesno("Confirm", "File exists. Overwrite?"):
            return
        password = self._prompt_password(
            "Create New Vault", "Enter master password for new vault:",
            confirm=True, show_generate=True,
        )
        if not password:
            return
        try:
            manager = VaultManager(vault_path, password.encode('utf-8'))
            manager.create_vault()
            try:
                access_log.record("vault_created", vault_path=vault_path, source="gui")
            except Exception:
                pass
            self._set_vault(manager, vault_path)
            messagebox.showinfo("Success", "Vault created successfully")
        except Exception as e:
            messagebox.showerror("Vault Creation Failed", f"Unable to create vault:\n{e}")

    def _open_vault(self, vault_path: str = None):
        """Open existing vault."""
        if not vault_path:
            vault_path = ask_open_filename(
                self.root,
                title="Open Vault",
                initialdir=get_vaults_directory(),
                filetypes=[("Vault files", "*.vault"), ("All files", "*.*")],
            )
            if not vault_path:
                return
        password = self._prompt_password(
            "Open Vault", "Enter master password:", show_generate=False
        )
        if not password:
            try:
                access_log.record("unlock_cancelled", vault_path=self.vault_path, source="gui")
            except Exception:
                pass
            return
        try:
            manager = VaultManager(vault_path, password.encode('utf-8'))
            manager.unlock_vault()
            if self.vault_manager:
                self.vault_manager.lock_vault(reason="switch_vault")
            self._set_vault(manager, vault_path)
        except Exception as e:
            hint = (
                "If you are sure the password is correct, the encrypted file may be damaged "
                "(for example from an interrupted save). Try restoring a copy from File History, "
                "a previous backup, or shadow copies if available."
            )
            if isinstance(e, InvalidTag):
                detail = (
                    "Decryption failed: wrong master password, or the vault file was altered or corrupted.\n\n"
                    + hint
                )
            else:
                detail = f"{e}\n\nPlease verify the password and vault file integrity."
            messagebox.showerror("Vault Access Failed", detail)

    def _set_vault(self, manager: VaultManager, vault_path: str):
        """Set vault and update UI."""
        self.vault_manager = manager
        self.vault_path = vault_path
        save_recent_vault(vault_path)
        self._update_recent_menu()
        self._update_menu_state()
        self._setup_unlocked_ui()

    def _backup_vault(self):
        """Copy the encrypted vault file and attachment store to a user-chosen location."""
        if not self.vault_manager or self.vault_manager.is_locked:
            return
        try:
            self.vault_manager.save_vault()
        except Exception as e:
            messagebox.showerror("Backup Failed", f"Could not save the vault before backup:\n{e}")
            return
        base_name = os.path.basename(self.vault_path)
        root_name, ext = os.path.splitext(base_name)
        if not ext:
            ext = ".vault"
        stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        initial = f"{root_name}_backup_{stamp}{ext}"
        dest = ask_save_as_filename(
            self.root,
            title="Backup Vault (encrypted copy)",
            initialfile=initial,
            defaultextension=ext,
            filetypes=[("Vault files", "*.vault"), ("All files", "*.*")],
        )
        if not dest:
            return
        attachments_src = f"{self.vault_path}.attachments"
        attachments_dest = f"{dest}.attachments"
        try:
            shutil.copy2(self.vault_path, dest)
            if os.path.isdir(attachments_src):
                if os.path.exists(attachments_dest):
                    messagebox.showerror(
                        "Backup Failed",
                        "A file or folder with the attachment backup name already exists.\n"
                        "Choose a different backup filename.",
                    )
                    return
                shutil.copytree(attachments_src, attachments_dest)
        except OSError as e:
            messagebox.showerror("Backup Failed", str(e))
            return
        msg = f"Encrypted vault copied to:\n{dest}"
        if os.path.isdir(attachments_src):
            msg += f"\n\nAttachments copied to:\n{attachments_dest}"
        messagebox.showinfo("Backup Complete", msg)

    def _lock_vault(self):
        """Lock vault."""
        if not self.vault_manager:
            return
        self.vault_manager.lock_vault(reason="manual")
        self.vault_manager = None
        self.vault_path = None
        self._show_locked_screen()
        self._update_menu_state()
        messagebox.showinfo("Locked", "Vault has been locked")

    def _open_recent_vault(self, vault_path: str):
        """Open a vault from the recent vaults list."""
        if not os.path.exists(vault_path):
            messagebox.showerror("Error", f"Vault file not found: {vault_path}")
            self._update_recent_menu()
            return
        self._open_vault(vault_path)

    # --------------------------------------------------------- teardown/util
    def _clear_body(self):
        if getattr(self, "_locked_frame", None) is not None and self._locked_frame.winfo_exists():
            self._locked_frame.destroy()
        self._locked_frame = None
        self._locked_stage = None
        self._teardown_unlocked_ui()

    def _teardown_unlocked_ui(self):
        if getattr(self, "content_canvas", None) is not None:
            try:
                self.content_canvas.unbind("<MouseWheel>")
            except Exception:
                pass
        if getattr(self, "content_inner", None) is not None:
            try:
                self.content_inner.unbind("<MouseWheel>")
            except Exception:
                pass
        if getattr(self, "_app_frame", None) is not None and self._app_frame.winfo_exists():
            self._app_frame.destroy()
        self._sections = {}
        # Drop references into the destroyed tree so the chrome/sidebar helpers
        # (which can be reached while locked) no longer touch dead widgets.
        for name in ("_sidebar", "sidebar", "_sidebar_sep", "_sidebar_reopen",
                     "_sidebar_footer", "_sidebar_footer_row", "_topbar", "_overview",
                     "search_bar", "content_canvas", "content_inner", "content_scroll",
                     "_recent_list"):
            setattr(self, name, None)
        self._sidebar_hidden = False
        self._restyle_window_buttons()

    def _update_recent_menu(self):
        """Update the recent vaults menu."""
        self.recent_menu.delete(0, tk.END)
        recent_vaults = load_recent_vaults(max_items=10)
        if not recent_vaults:
            self.recent_menu.add_command(label="(No recent vaults)", state=tk.DISABLED)
        else:
            for vault_path in recent_vaults:
                filename = os.path.basename(vault_path)
                if len(filename) > 50:
                    filename = filename[:47] + "..."
                self.recent_menu.add_command(
                    label=filename, command=lambda path=vault_path: self._open_recent_vault(path)
                )

    def _update_menu_state(self):
        """Update menu item states based on vault status."""
        unlocked = bool(self.vault_manager and not self.vault_manager.is_locked)
        self.file_menu.entryconfig("Lock Vault", state=tk.NORMAL if self.vault_manager else tk.DISABLED)
        self.file_menu.entryconfig("Backup Vault", state=tk.NORMAL if unlocked else tk.DISABLED)

    def _quick_theme_preset(self, preset_id: str) -> None:
        quick_apply_preset(self.root, self._ui_style, preset_id, menus=self._themed_menus)
        self._theme_merged = merge_theme(normalize_preset_id(preset_id), {})
        self.apply_theme(self._theme_merged)

    def _theme_settings(self):
        """Open theme dialog (same presets and colors as courier/FTP frontend)."""
        open_theme_settings(
            self.root, self.root, self._ui_style,
            menus=self._themed_menus,
            on_applied=self._on_theme_applied,
        )

    def _on_theme_applied(self, *_args) -> None:
        """Refresh the cached palette, then repaint from the NEW colors.

        The dialog saves its payload before invoking this callback, so the
        active merged palette is re-read from disk. Repainting with the stale
        cached palette would undo the switch the dialog just applied and leave
        the previous theme's accent on the content surfaces.
        """
        try:
            self._theme_merged = get_active_merged()
        except Exception:
            pass
        self.apply_theme(self._theme_merged)

    def _show_about(self):
        """Show about dialog."""
        AboutDialog(self.root)

    def _show_access_log(self):
        """Show the access log viewer (vault-only entry point: Security menu).

        The manager is forwarded so the dialog can resolve vault-scoped data;
        older dialog builds without that parameter still work.
        """
        if AccessLogDialog is None:
            return
        try:
            AccessLogDialog(self.root, vault_path=self.vault_path, manager=self.vault_manager)
        except TypeError:
            try:
                AccessLogDialog(self.root, vault_path=self.vault_path)
            except Exception:
                pass
        except Exception:
            pass

    def _show_window(self):
        """Show main window (for tray icon / taskbar restore)."""
        hwnd = self._hwnd()
        if hwnd:
            try:
                import ctypes

                ctypes.windll.user32.ShowWindow(ctypes.c_void_p(hwnd), 9)  # SW_RESTORE
            except Exception:
                pass
        try:
            self.root.deiconify()
        except Exception:
            pass
        self.root.lift()
        self.root.focus_force()

    def _on_closing(self):
        """Handle window close."""
        try:
            access_log.record("app_closed", vault_path=self.vault_path, source="gui")
        except Exception:
            pass
        if self.vault_manager:
            self.vault_manager.lock_vault(reason="app_exit")
        if self.tray_icon:
            self.tray_icon.stop()
        self.root.clipboard_clear()
        self.root.destroy()

    def run(self):
        """Run the GUI application."""
        self.root.mainloop()


def get_vaults_directory():
    """Get the vaults directory path, creating it if it doesn't exist."""
    vaults_dir = os.path.join(os.getcwd(), "vaults")
    os.makedirs(vaults_dir, exist_ok=True)
    return vaults_dir


def main():
    """Main entry point for GUI."""
    MainWindow().run()


if __name__ == "__main__":
    main()
