"""
List widgets: ``CardList`` (scrollable column of ``EntryCard``), ``EntryCard``
(a titled card with copy/edit/delete actions), and ``SectionHeader``.
"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional

import tkinter as tk
from tkinter import ttk

from ..design_system import RADIUS, SPACING, TYPOGRAPHY, build_tokens, font_role, get_active_merged
from ..ui_theme import register_themed, unregister_themed
from .inputs import IconButton, PrimaryButton
from .surface import RoundedSurface


class EntryCard(RoundedSurface):
    """A single card: title / subtitle / meta rows plus action icon buttons."""

    def __init__(
        self,
        master: tk.Misc,
        title: str = "",
        subtitle: str = "",
        meta: str = "",
        on_copy: Optional[Callable[[], None]] = None,
        on_edit: Optional[Callable[[], None]] = None,
        on_delete: Optional[Callable[[], None]] = None,
        **kw,
    ) -> None:
        # These must be set BEFORE ``super().__init__`` because the base class
        # registers for theming and applies the initial theme, which calls
        # ``apply_theme`` -> ``_style`` on this (still unbuilt) instance. After
        # super() runs, ``_try_apply_initial`` will have populated
        # ``self._tokens`` with the real tokens -- do not clobber it here.
        self._title_text = title
        self._subtitle_text = subtitle
        self._meta_text = meta
        self._tokens: Optional[Dict[str, str]] = None
        super().__init__(master, radius=RADIUS["md"], **kw)

        self._actions = tk.Frame(self.body, bd=0, highlightthickness=0)
        self._actions.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, SPACING["sm"]), pady=SPACING["md"])

        self._main = tk.Frame(self.body, bd=0, highlightthickness=0)
        self._main.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=SPACING["md"], pady=SPACING["md"])

        self._title = tk.Label(self._main, text=title, font=font_role("title"), anchor=tk.W, wraplength=360)
        self._title.pack(side=tk.TOP, fill=tk.X, anchor=tk.W)
        self._subtitle = tk.Label(self._main, text=subtitle, font=font_role("body"), anchor=tk.W, wraplength=360)
        self._subtitle.pack(side=tk.TOP, fill=tk.X, anchor=tk.W, pady=(2, 0))
        self._meta = tk.Label(self._main, text=meta, font=font_role("caption"), anchor=tk.W, wraplength=360)
        self._meta.pack(side=tk.TOP, fill=tk.X, anchor=tk.W, pady=(2, 0))

        if on_copy is not None:
            IconButton(self._actions, icon_name="copy", text_fallback="copy", command=on_copy).pack(side=tk.LEFT, padx=SPACING["xs"])
        if on_edit is not None:
            IconButton(self._actions, icon_name="edit", text_fallback="edit", command=on_edit).pack(side=tk.LEFT, padx=SPACING["xs"])
        if on_delete is not None:
            IconButton(self._actions, icon_name="trash", text_fallback="del", command=on_delete).pack(side=tk.LEFT, padx=SPACING["xs"])

        self._style()

        # Children now exist; apply the active theme once more so the canvas,
        # body and labels are colored immediately (before the first paint).
        try:
            from ..design_system import get_active_merged
            if tk._default_root is not None:
                self.apply_theme(get_active_merged())
        except Exception:
            pass

    # -- public api --------------------------------------------------------
    def set_data(self, title: str = "", subtitle: str = "", meta: str = "") -> None:
        self._title_text = title
        self._subtitle_text = subtitle
        self._meta_text = meta
        self._title.configure(text=title)
        self._subtitle.configure(text=subtitle)
        self._meta.configure(text=meta)

    def matches(self, query: str) -> bool:
        if not query:
            return True
        q = query.lower()
        return q in (self._title_text + " " + self._subtitle_text + " " + self._meta_text).lower()

    def apply_theme(self, merged: Dict[str, str]) -> None:
        self._tokens = build_tokens(merged)
        super().apply_theme(merged)
        self._style()

    # -- internals ---------------------------------------------------------
    def _style(self) -> None:
        if not self._tokens or not hasattr(self, "_main"):
            return
        fill = self._fill()
        for w in (self._main, self._actions):
            w.configure(bg=fill)
        self._title.configure(bg=fill, fg=self._tokens["text"])
        self._subtitle.configure(bg=fill, fg=self._tokens["muted"])
        self._meta.configure(bg=fill, fg=self._tokens["muted"])


class CardList(tk.Frame):
    """A scrollable column of :class:`EntryCard` widgets with filtering."""

    def __init__(self, master: tk.Misc, **kw) -> None:
        super().__init__(master, **kw)
        self._tokens: Optional[Dict[str, str]] = None
        self._cards: List[EntryCard] = []

        self.canvas = tk.Canvas(self, highlightthickness=0, bd=0)
        self.scroll = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scroll.set)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.inner = tk.Frame(self.canvas, bd=0, highlightthickness=0)
        self._canvas_win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", lambda _e: self._update_scrollregion())
        # Keep the inner frame as wide as the canvas so cards stretch full width.
        self.canvas.bind("<Configure>", lambda _e: self._resize_inner())
        # Only scroll when the pointer is actually over this list (not app-wide).
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)
        self.inner.bind("<MouseWheel>", self._on_mousewheel)

        register_themed(self)
        self._try_apply_initial()

    # -- public api --------------------------------------------------------
    def add(self, card: EntryCard) -> None:
        card.pack(in_=self.inner, fill=tk.X, padx=SPACING["sm"], pady=SPACING["xs"])
        self._cards.append(card)
        # Defense in depth: make sure the card is themed once it is parented
        # here, so it never renders with the default white SystemButtonFace.
        if self._tokens:
            try:
                card.apply_theme(get_active_merged())
            except Exception:
                pass
        self._bind_mousewheel(card)

    def _bind_mousewheel(self, widget: tk.Misc) -> None:
        widget.bind("<MouseWheel>", self._on_mousewheel)
        widget.bind("<Button-4>", self._on_mousewheel)
        widget.bind("<Button-5>", self._on_mousewheel)
        for child in widget.winfo_children():
            self._bind_mousewheel(child)

    def clear(self) -> None:
        for c in self._cards:
            try:
                c.destroy()
            except Exception:
                pass
        self._cards = []

    def filter(self, query: str) -> None:
        for c in self._cards:
            try:
                c.pack_forget() if not c.matches(query) else c.pack(
                    in_=self.inner, fill=tk.X, padx=SPACING["sm"], pady=SPACING["xs"]
                )
            except Exception:
                pass

    def apply_theme(self, merged: Dict[str, str]) -> None:
        self._tokens = build_tokens(merged)
        bg = self._tokens["bg"]
        self.configure(bg=bg)
        self.canvas.configure(bg=bg)
        self.inner.configure(bg=bg)

    def destroy(self) -> None:
        unregister_themed(self)
        try:
            self.canvas.unbind("<MouseWheel>")
            self.inner.unbind("<MouseWheel>")
        except Exception:
            pass
        super().destroy()

    # -- internals ---------------------------------------------------------
    def _try_apply_initial(self) -> None:
        try:
            if tk._default_root is not None:
                self.apply_theme(get_active_merged())
        except Exception:
            pass

    def _resize_inner(self) -> None:
        self.canvas.itemconfig(self._canvas_win, width=self.canvas.winfo_width())
        self._update_scrollregion()

    def _update_scrollregion(self) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        try:
            content_height = self.inner.winfo_reqheight()
            canvas_height = self.canvas.winfo_height()
            if canvas_height > 0 and content_height <= canvas_height:
                self.scroll.pack_forget()
            else:
                self.scroll.pack(side=tk.RIGHT, fill=tk.Y)
        except Exception:
            pass

    def _on_mousewheel(self, event) -> None:
        try:
            if event.num == 4:
                self.canvas.yview_scroll(-1, "units")
            elif event.num == 5:
                self.canvas.yview_scroll(1, "units")
            else:
                self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        except Exception:
            pass
        return "break"


class SectionHeader(tk.Frame):
    """Title + item count + an \"Add\" button for a section view."""

    def __init__(
        self,
        master: tk.Misc,
        title: str = "",
        count: int = 0,
        on_add: Optional[Callable[[], None]] = None,
        **kw,
    ) -> None:
        super().__init__(master, **kw)
        self._title_text = title
        self._count = count
        self._tokens: Optional[Dict[str, str]] = None

        self._left = tk.Frame(self, bd=0, highlightthickness=0)
        self._left.pack(side=tk.LEFT, fill=tk.Y)
        self._title = tk.Label(self._left, text=title, font=font_role("title"), anchor=tk.W)
        self._title.pack(side=tk.TOP, anchor=tk.W)
        self._count_label = tk.Label(self._left, text=self._count_text(), font=font_role("caption"), anchor=tk.W)
        self._count_label.pack(side=tk.TOP, anchor=tk.W, pady=(2, 0))

        self._add_btn = PrimaryButton(self, text="Add", command=on_add or (lambda: None))
        self._add_btn.pack(side=tk.RIGHT, anchor=tk.E)

        register_themed(self)
        self._try_apply_initial()

    def set_count(self, count: int) -> None:
        self._count = count
        self._count_label.configure(text=self._count_text())

    def set_title(self, title: str) -> None:
        self._title_text = title
        self._title.configure(text=title)

    def apply_theme(self, merged: Dict[str, str]) -> None:
        self._tokens = build_tokens(merged)
        bg = self._tokens["bg"]
        self.configure(bg=bg)
        self._left.configure(bg=bg)
        self._title.configure(bg=bg, fg=self._tokens["text"])
        self._count_label.configure(bg=bg, fg=self._tokens["muted"])

    def destroy(self) -> None:
        unregister_themed(self)
        super().destroy()

    def _try_apply_initial(self) -> None:
        try:
            if tk._default_root is not None:
                self.apply_theme(get_active_merged())
        except Exception:
            pass

    def _count_text(self) -> str:
        return f"{self._count} item{'s' if self._count != 1 else ''}"
