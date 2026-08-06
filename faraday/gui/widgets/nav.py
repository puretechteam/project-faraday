"""
Navigation widgets: ``Sidebar`` and ``NavItem``.

The sidebar shows a branded header and a vertical list of icon+label items with
a collapsible (icons-only) mode. The active item gets an accent left-bar and an
accent-tinted background. Icons are loaded from ``assets/icons``; when a PNG is
missing the item gracefully shows label text only.
"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional, Tuple

import tkinter as tk

from ..design_system import RADIUS, SPACING, TYPOGRAPHY, build_tokens, font_role, get_active_merged
from ..ui_theme import register_themed, unregister_themed
from ._icons import load_icon


# Sidebar geometry. When collapsed, the frame width below is the ONLY thing
# that may stay visible: every child is clamped to it (and the frame keeps
# geometry propagation disabled) so no nav content can spill out and leave a
# "half sidebar" strip next to the content area.
SIDEBAR_EXPANDED_WIDTH = 220
SIDEBAR_COLLAPSED_WIDTH = 64
# A nav item is packed with SPACING["xs"] padding on both sides inside the rail.
NAV_ITEM_COLLAPSED_WIDTH = SIDEBAR_COLLAPSED_WIDTH - 2 * SPACING["xs"]
NAV_ITEM_MIN_HEIGHT = 28


class NavItem(tk.Frame):
    """A single navigation entry: icon + label with an active accent state."""

    def __init__(
        self,
        master: tk.Misc,
        key: str,
        label: str,
        icon: Optional[tk.PhotoImage] = None,
        on_select: Optional[Callable[[str], None]] = None,
        collapsed: bool = False,
        collapsed_width: int = NAV_ITEM_COLLAPSED_WIDTH,
        **kw,
    ) -> None:
        super().__init__(master, **kw)
        self._key = key
        self._label_text = label
        self._icon = icon
        self._on_select = on_select
        self._collapsed = collapsed
        self._collapsed_width = max(1, int(collapsed_width))
        # Icon-only fallback glyph: builds without the PNG asset bundle would
        # otherwise render an empty, unclickable rail when collapsed.
        self._initial = (label or "?").strip()[:1].upper() or "?"
        self._active = False
        self._tokens: Optional[Dict[str, str]] = None

        self._indicator = tk.Frame(self, width=3, bd=0, highlightthickness=0)
        self._indicator.pack(side=tk.LEFT, fill=tk.Y)

        self._icon_label = tk.Label(self, image=icon, bd=0, highlightthickness=0)
        self._icon_label.pack(side=tk.LEFT, padx=(SPACING["sm"], 0))

        self._text_label = tk.Label(self, text=label, anchor=tk.W)
        self._text_label.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=SPACING["sm"])

        for w in (self, self._icon_label, self._text_label):
            w.bind("<Button-1>", self._on_click)

        self._apply_collapsed()
        register_themed(self)
        self._try_apply_initial()

    # -- public api --------------------------------------------------------
    def set_active(self, active: bool) -> None:
        self._active = bool(active)
        self._apply_style()

    def set_collapsed(self, collapsed: bool) -> None:
        self._collapsed = bool(collapsed)
        self._apply_collapsed()
        self._apply_style()

    def apply_theme(self, merged: Dict[str, str]) -> None:
        self._tokens = build_tokens(merged)
        self._apply_style()

    def destroy(self) -> None:
        unregister_themed(self)
        super().destroy()

    # -- internals ---------------------------------------------------------
    def _try_apply_initial(self) -> None:
        try:
            if tk._default_root is not None:
                self.apply_theme(get_active_merged())
        except Exception:
            pass

    def _on_click(self, _e=None) -> None:
        if self._on_select is not None:
            self._on_select(self._key)

    def _apply_collapsed(self) -> None:
        """Icon-only (hard clamped) when collapsed, icon + label when expanded.

        Collapsing hides the text label AND pins the item's own width to the
        collapsed rail width with geometry propagation off, so nothing wider
        than the collapsed sidebar can ever be rendered/clipped into view.
        """
        if self._collapsed:
            self._text_label.pack_forget()
            if self._icon is None:
                # No PNG icon available: show a single centered initial that
                # always fits inside the narrow rail.
                self._icon_label.configure(
                    text=self._initial, font=font_role("caption"), width=2,
                )
            self._icon_label.pack_configure(
                side=tk.LEFT, fill=tk.BOTH, expand=True, padx=0,
            )
            # Capture the natural height BEFORE propagation is disabled, else
            # the item would request height 0 and vanish from the rail.
            height = max(self.winfo_reqheight(), NAV_ITEM_MIN_HEIGHT)
            self.configure(width=self._collapsed_width, height=height)
            self.pack_propagate(False)
        else:
            self.pack_propagate(True)
            self._icon_label.configure(text="", width=0)
            self._icon_label.pack_configure(
                side=tk.LEFT, fill=tk.NONE, expand=False, padx=(SPACING["sm"], 0),
            )
            self._text_label.pack(
                side=tk.LEFT, fill=tk.X, expand=True, padx=SPACING["sm"], after=self._icon_label
            )

    def _apply_style(self) -> None:
        if not self._tokens:
            return
        t = self._tokens
        if self._active:
            self.configure(bg=t["hover"])
            self._indicator.configure(bg=t["accent"])
            self._text_label.configure(fg=t["text"])
            self._icon_label.configure(fg=t["text"])
        else:
            self.configure(bg=t["bg"])
            self._indicator.configure(bg=t["bg"])
            self._text_label.configure(fg=t["muted"])
            self._icon_label.configure(fg=t["muted"])
        self._icon_label.configure(bg=self.cget("bg"))
        self._text_label.configure(bg=self.cget("bg"))


class Sidebar(tk.Frame):
    """Branded, collapsible left navigation sidebar."""

    def __init__(
        self,
        master: tk.Misc,
        items: Optional[List[Tuple[str, str, Optional[str]]]] = None,
        on_select: Optional[Callable[[str], None]] = None,
        app_name: str = "Faraday",
        subtitle: str = "Secure Vault",
        **kw,
    ) -> None:
        collapsed_width = kw.pop("collapsed_width", SIDEBAR_COLLAPSED_WIDTH)
        super().__init__(master, **kw)
        try:
            self._expanded_width = int(kw.get("width") or SIDEBAR_EXPANDED_WIDTH)
        except (TypeError, ValueError):
            self._expanded_width = SIDEBAR_EXPANDED_WIDTH
        try:
            self._collapsed_width = int(collapsed_width)
        except (TypeError, ValueError):
            self._collapsed_width = SIDEBAR_COLLAPSED_WIDTH
        if "width" in kw:
            # An explicit width means the caller owns the sidebar size; keep
            # propagation off so collapse/expand actually resizes the frame.
            self.pack_propagate(False)
        self._items: Dict[str, NavItem] = {}
        self._on_select = on_select
        self._app_name = app_name
        self._subtitle = subtitle
        self._active: Optional[str] = None
        self._collapsed = False
        self._tokens: Optional[Dict[str, str]] = None

        self._build_header()
        self._nav = tk.Frame(self, bd=0, highlightthickness=0)
        self._nav.pack(side=tk.TOP, fill=tk.BOTH, expand=True, pady=(SPACING["sm"], 0))

        if items:
            for key, label, icon_name in items:
                self.add_item(key, label, icon_name)

        register_themed(self)
        self._try_apply_initial()

    # -- public api --------------------------------------------------------
    def add_item(self, key: str, label: str, icon_name: Optional[str] = None) -> NavItem:
        icon = load_icon(icon_name) if icon_name else None
        item = NavItem(
            self._nav, key=key, label=label, icon=icon,
            on_select=self._handle_select, collapsed=self._collapsed,
            collapsed_width=max(1, self._collapsed_width - 2 * SPACING["xs"]),
        )
        item.pack(side=tk.TOP, fill=tk.X, padx=SPACING["xs"], pady=SPACING["xs"])
        if self._active == key:
            item.set_active(True)
        self._items[key] = item
        return item

    def set_active(self, key: str) -> None:
        self._active = key
        for k, item in self._items.items():
            item.set_active(k == key)

    def get_active(self) -> Optional[str]:
        return self._active

    def collapse(self) -> None:
        self._set_collapsed(True)

    def expand(self) -> None:
        self._set_collapsed(False)

    def toggle(self) -> None:
        self._set_collapsed(not self._collapsed)

    def is_collapsed(self) -> bool:
        return self._collapsed

    def apply_theme(self, merged: Dict[str, str]) -> None:
        self._tokens = build_tokens(merged)
        bg = self._tokens["bg"]
        self.configure(bg=bg)
        self._nav.configure(bg=bg)
        if self._brand is not None:
            self._brand.configure(bg=bg)
        if self._app_label is not None:
            self._app_label.configure(bg=bg, fg=self._tokens["text"])
        if self._sub_label is not None:
            self._sub_label.configure(bg=bg, fg=self._tokens["muted"])

    def destroy(self) -> None:
        unregister_themed(self)
        super().destroy()

    # -- internals ---------------------------------------------------------
    def _try_apply_initial(self) -> None:
        try:
            if tk._default_root is not None:
                self.apply_theme(get_active_merged())
        except Exception:
            pass

    def _handle_select(self, key: str) -> None:
        self.set_active(key)
        if self._on_select is not None:
            self._on_select(key)

    def _set_collapsed(self, collapsed: bool) -> None:
        """Collapse/expand the rail *including* the frame's own width.

        Previously only the item labels were hidden, so the frame kept its
        expanded width (or snapped back to it via geometry propagation) and a
        strip of nav content stayed visible next to a "collapsed" sidebar.
        """
        self._collapsed = bool(collapsed)
        # Propagation must stay off or the frame resizes itself to its children
        # and the configured width below is ignored.
        self.pack_propagate(False)
        self.configure(
            width=self._collapsed_width if self._collapsed else self._expanded_width
        )
        for item in self._items.values():
            item.set_collapsed(self._collapsed)
        self._apply_collapsed_header()
        try:
            self.update_idletasks()
        except Exception:
            pass

    def _apply_collapsed_header(self) -> None:
        """Hide the brand text when collapsed so it can never be half-clipped."""
        if getattr(self, "_brand", None) is None:
            return
        if self._collapsed:
            if self._app_label is not None:
                self._app_label.configure(
                    text=(self._app_name or "")[:1].upper(), font=font_role("title"),
                )
            if self._sub_label is not None:
                self._sub_label.pack_forget()
            self._brand.pack_configure(padx=SPACING["xs"])
        else:
            if self._app_label is not None:
                self._app_label.configure(text=self._app_name, font=font_role("display"))
            if self._sub_label is not None:
                self._sub_label.configure(text=self._subtitle)
                self._sub_label.pack(side=tk.TOP, anchor=tk.W, pady=(2, 0))
            self._brand.pack_configure(padx=SPACING["md"])

    def _build_header(self) -> None:
        self._brand = tk.Frame(self, bd=0, highlightthickness=0)
        self._brand.pack(side=tk.TOP, fill=tk.X, padx=SPACING["md"], pady=SPACING["md"])
        self._app_label = tk.Label(
            self._brand, text=self._app_name, anchor=tk.W, font=font_role("display"),
        )
        self._app_label.pack(side=tk.TOP, anchor=tk.W)
        self._sub_label = tk.Label(
            self._brand, text=self._subtitle, anchor=tk.W, font=font_role("caption"),
        )
        self._sub_label.pack(side=tk.TOP, anchor=tk.W, pady=(2, 0))
