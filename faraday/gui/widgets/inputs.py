"""
Input controls: themed buttons, ``SearchBar``, ``LabeledEntry``, ``SecretField``
and ``LabeledText``.

Button styling uses dedicated ttk styles (``Accent.TButton`` / ``Danger.TButton``
/ ``Ghost.TButton``) so the active/pressed states are theme-aware. ``IconButton``
is a borderless ``tk.Button`` (icon with a text fallback). ``SearchBar`` draws
its own 1px edge *inside* its bounds (no Tk highlight ring, no ttk focus ring).
Every widget implements ``apply_theme`` and registers itself.
"""

from __future__ import annotations

from typing import Callable, Dict, Optional

import tkinter as tk
from tkinter import ttk

from ..clipboard_helper import copy_to_clipboard
from ..design_system import RADIUS, SPACING, TYPOGRAPHY, _darken, _lighten, build_tokens, font_role, get_active_merged
from ..ui_theme import register_themed, unregister_themed
from ._icons import load_icon

# Reused ttk style names (configured in ``_apply_button_styles``).
_STYLE_ACCENT = "FaradayAccent.TButton"
_STYLE_DANGER = "FaradayDanger.TButton"
_STYLE_GHOST = "FaradayGhost.TButton"

# Flat entry style used inside ``SearchBar`` (see ``_apply_search_entry_style``).
_STYLE_SEARCH_ENTRY = "FaradaySearch.TEntry"

# Width in pixels of the ``SearchBar`` edge. The frame paints it itself and
# insets its content by the same amount, so the line always stays *inside* the
# widget bounds (unlike a Tk highlight ring, which reads as a floating outline).
_SEARCH_BORDER = 1


def _apply_button_styles(style: ttk.Style, tokens: Dict[str, str]) -> None:
    """(Re)configure the shared button styles from the current tokens."""
    a = tokens["accent"]
    d = tokens["danger"]
    style.configure(
        _STYLE_ACCENT,
        background=a, foreground=tokens["on_accent"],
        borderwidth=0, focusthickness=0,
        padding=(SPACING["md"], SPACING["sm"]),
    )
    style.map(
        _STYLE_ACCENT,
        background=[
            ("disabled", _darken(a, 0.45)),
            ("pressed", _darken(a, 0.12)),
            ("active", _lighten(a, 0.12)),
        ],
        foreground=[
            ("disabled", tokens["muted"]),
            ("pressed", tokens["on_accent"]),
            ("active", tokens["on_accent"]),
        ],
    )
    style.configure(
        _STYLE_DANGER,
        background=d, foreground=tokens["on_accent"],
        borderwidth=0, focusthickness=0,
        padding=(SPACING["md"], SPACING["sm"]),
    )
    style.map(
        _STYLE_DANGER,
        background=[
            ("disabled", _darken(d, 0.45)),
            ("pressed", _darken(d, 0.12)),
            ("active", _lighten(d, 0.12)),
        ],
        foreground=[
            ("disabled", tokens["muted"]),
            ("pressed", tokens["on_accent"]),
            ("active", tokens["on_accent"]),
        ],
    )
    style.configure(
        _STYLE_GHOST,
        background=tokens["surface"], foreground=tokens["text"],
        borderwidth=1, bordercolor=tokens["border"], focusthickness=0,
        padding=(SPACING["md"], SPACING["sm"]),
    )
    style.map(
        _STYLE_GHOST,
        background=[
            ("disabled", tokens["surface"]),
            ("pressed", tokens["border"]),
            ("active", tokens["hover"]),
        ],
        foreground=[
            ("disabled", tokens["muted"]),
            ("pressed", tokens["text"]),
            ("active", tokens["text"]),
        ],
    )


def _apply_search_entry_style(style: ttk.Style, tokens: Dict[str, str]) -> None:
    """(Re)configure the flat entry style used inside :class:`SearchBar`.

    The clam theme normally gives ``TEntry`` a 3D border *and* swaps in a bright
    focus ring (``bordercolor``/``lightcolor``/``darkcolor`` are mapped on the
    ``focus`` state). Both are neutralized here — zero border width plus every
    border color pinned to the field background, focused or not — so the only
    visible edge is the SearchBar's own contained 1px line.
    """
    surface = tokens["surface"]
    flat = [("focus", surface), ("!focus", surface)]
    style.configure(
        _STYLE_SEARCH_ENTRY,
        fieldbackground=surface, background=surface,
        foreground=tokens["text"], insertcolor=tokens["text"],
        selectbackground=tokens["accent"], selectforeground=tokens["on_accent"],
        borderwidth=0, relief=tk.FLAT,
        bordercolor=surface, lightcolor=surface, darkcolor=surface,
        padding=(SPACING["xs"], 2),
    )
    style.map(
        _STYLE_SEARCH_ENTRY,
        fieldbackground=[("readonly", surface), ("disabled", surface)],
        bordercolor=flat, lightcolor=flat, darkcolor=flat,
    )


def apply_shared_input_styles(style: ttk.Style, merged: Dict[str, str]) -> None:
    """Re-derive every shared input style from a merged theme palette.

    Called by :func:`faraday.gui.ui_theme.apply_ttk_styles` on every theme
    change so the accent-derived button styles and the search entry style
    follow the new palette even when no instance of those widgets is currently
    alive (an instance would otherwise be the only thing that refreshes them,
    leaving the previous theme's accent in the style database).
    """
    tokens = build_tokens(merged)
    _apply_button_styles(style, tokens)
    _apply_search_entry_style(style, tokens)


class _ThemedButton(ttk.Button):
    """Base ttk button that registers for live theming."""

    _STYLE_NAME = "TButton"

    def __init__(self, master: tk.Misc, **kw) -> None:
        kw.setdefault("style", self._STYLE_NAME)
        super().__init__(master, **kw)
        register_themed(self)
        self._try_apply_initial()

    def _try_apply_initial(self) -> None:
        try:
            if tk._default_root is not None:
                self.apply_theme(get_active_merged())
        except Exception:
            pass

    def apply_theme(self, merged: Dict[str, str]) -> None:
        _apply_button_styles(ttk.Style(self), build_tokens(merged))

    def destroy(self) -> None:
        unregister_themed(self)
        super().destroy()


class PrimaryButton(_ThemedButton):
    _STYLE_NAME = _STYLE_ACCENT


class DangerButton(_ThemedButton):
    _STYLE_NAME = _STYLE_DANGER


class GhostButton(_ThemedButton):
    _STYLE_NAME = _STYLE_GHOST


class IconButton(tk.Button):
    """A borderless icon button (text fallback when the icon is missing)."""

    def __init__(
        self,
        master: tk.Misc,
        icon_name: Optional[str] = None,
        text_fallback: str = "",
        command: Optional[Callable[[], None]] = None,
        **kw,
    ) -> None:
        self._icon = load_icon(icon_name)
        self._text_fallback = text_fallback
        kw.setdefault("bd", 0)
        kw.setdefault("relief", tk.FLAT)
        kw.setdefault("highlightthickness", 0)
        kw.setdefault("padx", SPACING["sm"])
        kw.setdefault("pady", SPACING["xs"])
        kw.setdefault("cursor", "hand2")
        super().__init__(
            master, image=self._icon, text=text_fallback if self._icon is None else "",
            compound=tk.LEFT, command=command, **kw,
        )
        register_themed(self)
        self._tokens: Optional[Dict[str, str]] = None
        self._try_apply_initial()

    def _try_apply_initial(self) -> None:
        try:
            if tk._default_root is not None:
                self.apply_theme(get_active_merged())
        except Exception:
            pass

    def set_text_fallback(self, text: str) -> None:
        """Update the text shown when no icon image is available."""
        self._text_fallback = text
        if self._icon is None:
            self.configure(text=text)

    def apply_theme(self, merged: Dict[str, str]) -> None:
        self._tokens = build_tokens(merged)
        self.configure(
            bg=self._tokens["surface"],
            activebackground=self._tokens["hover"],
            fg=self._tokens["text"],
            activeforeground=self._tokens["text"],
            disabledforeground=self._tokens["muted"],
        )

    def destroy(self) -> None:
        unregister_themed(self)
        super().destroy()


class SearchBar(tk.Frame):
    """A themed Entry with a search icon on the left.

    The edge is drawn by the frame itself: the frame is filled with the border
    color and its content sits on an inner ``surface`` frame inset by
    ``_SEARCH_BORDER`` pixels. Tk highlight rings — which paint *around* the
    content and look like an outline floating outside the widget — are disabled
    on every part (frame, icon, entry), including on focus.
    """

    def __init__(
        self,
        master: tk.Misc,
        on_change: Optional[Callable[[str], None]] = None,
        placeholder: str = "Search...",
        **kw,
    ) -> None:
        kw.setdefault("bd", 0)
        kw.setdefault("relief", tk.FLAT)
        kw.setdefault("highlightthickness", 0)
        super().__init__(master, **kw)
        self._on_change = on_change
        self._placeholder = placeholder
        self._tokens: Optional[Dict[str, str]] = None
        self._has_text = False
        self._focused = False

        # Inner surface holding the icon + entry; the 1px gap it leaves around
        # itself is the (fully contained) border of the search bar.
        self._field = tk.Frame(self, bd=0, relief=tk.FLAT, highlightthickness=0)
        self._field.pack(
            side=tk.TOP, fill=tk.BOTH, expand=True,
            padx=_SEARCH_BORDER, pady=_SEARCH_BORDER,
        )

        self._icon = load_icon("search")
        self._icon_label: Optional[tk.Label] = None
        if self._icon is not None:
            self._icon_label = tk.Label(self._field, image=self._icon, bd=0, highlightthickness=0)
            self._icon_label.pack(side=tk.LEFT, padx=(SPACING["sm"], SPACING["xs"]))

        self.entry = ttk.Entry(self._field, style=_STYLE_SEARCH_ENTRY)
        self.entry.pack(
            side=tk.LEFT, fill=tk.X, expand=True,
            padx=(SPACING["sm"] if self._icon_label is None else 0, SPACING["sm"]),
        )
        self.entry.insert(0, placeholder)
        self._has_text = False
        self._apply_placeholder_style()

        self.entry.bind("<KeyRelease>", self._on_key)
        self.entry.bind("<FocusIn>", self._on_focus_in)
        self.entry.bind("<FocusOut>", self._on_focus_out)

        register_themed(self)
        self._try_apply_initial()

    # -- public api --------------------------------------------------------
    def get(self) -> str:
        val = self.entry.get()
        return "" if (not self._has_text and val == self._placeholder) else val

    def set(self, text: str) -> None:
        self.entry.delete(0, tk.END)
        if text:
            self.entry.insert(0, text)
            self._has_text = True
        else:
            self.entry.insert(0, self._placeholder)
            self._has_text = False
        self._apply_placeholder_style()

    def apply_theme(self, merged: Dict[str, str]) -> None:
        self._tokens = build_tokens(merged)
        _apply_search_entry_style(ttk.Style(self), self._tokens)
        surface = self._tokens["surface"]
        edge = self._edge_color()
        # No highlight ring anywhere: the frame's own inset fill is the border,
        # so nothing can bleed outside the widget's bounds (focused or not).
        self.configure(
            bg=edge,
            bd=0,
            relief=tk.FLAT,
            highlightthickness=0,
            highlightbackground=edge,
            highlightcolor=edge,
        )
        self._field.configure(bg=surface)
        if self._icon_label is not None:
            self._icon_label.configure(bg=surface)
        self._apply_placeholder_style()

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

    def _on_key(self, _e=None) -> None:
        val = self.entry.get()
        self._has_text = bool(val) and val != self._placeholder
        self._apply_placeholder_style()
        if self._on_change is not None:
            self._on_change(self.get())

    def _on_focus_in(self, _e=None) -> None:
        self._focused = True
        self._sync_edge()
        if not self._has_text:
            self.entry.delete(0, tk.END)
            self._apply_placeholder_style()

    def _on_focus_out(self, _e=None) -> None:
        self._focused = False
        self._sync_edge()
        if not self.entry.get():
            self.entry.insert(0, self._placeholder)
            self._has_text = False
        self._apply_placeholder_style()

    def _edge_color(self) -> str:
        """Color of the 1px contained edge (accent while focused)."""
        if self._tokens is None:
            return "#3c3c3c"
        return self._tokens["accent"] if self._focused else self._tokens["border"]

    def _sync_edge(self) -> None:
        """Repaint the inset edge; never touches highlight/border thickness."""
        if self._tokens is None:
            return
        edge = self._edge_color()
        try:
            self.configure(bg=edge, highlightbackground=edge, highlightcolor=edge)
        except tk.TclError:
            pass

    def _apply_placeholder_style(self) -> None:
        """Show the placeholder in the muted color, typed text in the normal one."""
        if self._tokens is None:
            return
        showing_placeholder = not self._has_text and self.entry.get() == self._placeholder
        color = self._tokens["muted"] if showing_placeholder else self._tokens["text"]
        try:
            self.entry.configure(foreground=color)
        except Exception:
            pass


class LabeledEntry(tk.Frame):
    """A caption label above a themed Entry."""

    def __init__(
        self,
        master: tk.Misc,
        label: str = "",
        value: str = "",
        on_change: Optional[Callable[[str], None]] = None,
        **kw,
    ) -> None:
        super().__init__(master, **kw)
        self._on_change = on_change
        self._tokens: Optional[Dict[str, str]] = None

        self._label = tk.Label(self, text=label, anchor=tk.W, font=font_role("caption"))
        self._label.pack(side=tk.TOP, fill=tk.X, pady=(0, SPACING["xs"]))
        self.entry = ttk.Entry(self)
        self.entry.pack(side=tk.TOP, fill=tk.X)
        if value:
            self.entry.insert(0, value)
        self.entry.bind("<KeyRelease>", self._on_key)

        register_themed(self)
        self._try_apply_initial()

    def get(self) -> str:
        return self.entry.get()

    def set(self, text: str) -> None:
        self.entry.delete(0, tk.END)
        self.entry.insert(0, text)

    def apply_theme(self, merged: Dict[str, str]) -> None:
        self._tokens = build_tokens(merged)
        self.configure(bg=self._tokens["surface"])
        self._label.configure(fg=self._tokens["muted"], bg=self._tokens["surface"])

    def destroy(self) -> None:
        unregister_themed(self)
        super().destroy()

    def _try_apply_initial(self) -> None:
        try:
            if tk._default_root is not None:
                self.apply_theme(get_active_merged())
        except Exception:
            pass

    def _on_key(self, _e=None) -> None:
        if self._on_change is not None:
            self._on_change(self.get())


class SecretField(tk.Frame):
    """A password field with reveal + copy controls and masked input."""

    def __init__(
        self,
        master: tk.Misc,
        label: str = "Secret",
        value: str = "",
        on_change: Optional[Callable[[str], None]] = None,
        **kw,
    ) -> None:
        super().__init__(master, **kw)
        self._on_change = on_change
        self._tokens: Optional[Dict[str, str]] = None
        self._revealed = False

        self._label = tk.Label(self, text=label, anchor=tk.W, font=font_role("caption"))
        self._label.pack(side=tk.TOP, fill=tk.X, pady=(0, SPACING["xs"]))

        self._row = tk.Frame(self, bd=0, highlightthickness=0)
        self._row.pack(side=tk.TOP, fill=tk.X)

        self.entry = ttk.Entry(self._row, show="*")
        self.entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        if value:
            self.entry.insert(0, value)
        self.entry.bind("<KeyRelease>", self._on_key)

        self._reveal_btn = IconButton(
            self._row, icon_name="eye", text_fallback="show",
            command=self._toggle_reveal,
        )
        self._reveal_btn.pack(side=tk.LEFT, padx=(SPACING["xs"], 0))
        self._copy_btn = IconButton(
            self._row, icon_name="copy", text_fallback="copy",
            command=self._copy,
        )
        self._copy_btn.pack(side=tk.LEFT, padx=(SPACING["xs"], 0))

        register_themed(self)
        self._try_apply_initial()

    def get(self) -> str:
        return self.entry.get()

    def set(self, text: str) -> None:
        self.entry.delete(0, tk.END)
        self.entry.insert(0, text)
        if self._on_change is not None:
            self._on_change(text)

    def apply_theme(self, merged: Dict[str, str]) -> None:
        self._tokens = build_tokens(merged)
        bg = self._tokens["surface"]
        self.configure(bg=bg)
        self._label.configure(fg=self._tokens["muted"], bg=bg)
        self._row.configure(bg=bg)

    def destroy(self) -> None:
        unregister_themed(self)
        super().destroy()

    def _try_apply_initial(self) -> None:
        try:
            if tk._default_root is not None:
                self.apply_theme(get_active_merged())
        except Exception:
            pass

    def _on_key(self, _e=None) -> None:
        if self._on_change is not None:
            self._on_change(self.get())

    def _toggle_reveal(self) -> None:
        self._revealed = not self._revealed
        self.entry.configure(show="" if self._revealed else "*")
        self._reveal_btn.set_text_fallback("hide" if self._revealed else "show")

    def _copy(self) -> None:
        value = self.get()
        if not value:
            return
        root = self.winfo_toplevel()
        try:
            copy_to_clipboard(value, "sensitive", root)
        except Exception:
            try:
                root.clipboard_clear()
                root.clipboard_append(value)
            except Exception:
                pass


class LabeledText(tk.Frame):
    """A caption label above a read-only value (monospace for secrets)."""

    def __init__(
        self,
        master: tk.Misc,
        label: str = "",
        value: str = "",
        mono: bool = False,
        **kw,
    ) -> None:
        super().__init__(master, **kw)
        self._mono = mono
        self._tokens: Optional[Dict[str, str]] = None

        self._label = tk.Label(self, text=label, anchor=tk.W, font=font_role("caption"))
        self._label.pack(side=tk.TOP, fill=tk.X, pady=(0, SPACING["xs"]))

        self._value_label = tk.Label(
            self, text=value, anchor=tk.W,
            font=font_role("mono" if mono else "body"),
            wraplength=400, justify=tk.LEFT,
        )
        self._value_label.pack(side=tk.TOP, fill=tk.X)

        register_themed(self)
        self._try_apply_initial()

    def set(self, text: str) -> None:
        self._value_label.configure(text=text)

    def get(self) -> str:
        return self._value_label.cget("text")

    def apply_theme(self, merged: Dict[str, str]) -> None:
        self._tokens = build_tokens(merged)
        bg = self._tokens["surface"]
        self.configure(bg=bg)
        self._label.configure(fg=self._tokens["muted"], bg=bg)
        self._value_label.configure(
            fg=self._tokens["text"], bg=bg,
            font=font_role("mono" if self._mono else "body"),
        )

    def destroy(self) -> None:
        unregister_themed(self)
        super().destroy()

    def _try_apply_initial(self) -> None:
        try:
            if tk._default_root is not None:
                self.apply_theme(get_active_merged())
        except Exception:
            pass
