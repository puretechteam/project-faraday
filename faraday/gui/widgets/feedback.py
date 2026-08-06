"""
Feedback widgets: ``EmptyState``, a transient ``Toast``/status helper, and a
themed ``ConfirmDialog`` built on :class:`dialogs.Dialog`.
"""

from __future__ import annotations

from typing import Callable, Dict, Optional

import tkinter as tk

from ..design_system import RADIUS, SPACING, TYPOGRAPHY, build_tokens, font_role, get_active_merged
from ..ui_theme import register_themed, unregister_themed
from ._icons import load_icon
from .inputs import DangerButton, PrimaryButton
from .surface import RoundedSurface


class EmptyState(tk.Frame):
    """A centered icon + message + optional action button."""

    def __init__(
        self,
        master: tk.Misc,
        message: str = "Nothing here yet.",
        icon_name: Optional[str] = None,
        action_label: Optional[str] = None,
        on_action: Optional[Callable[[], None]] = None,
        **kw,
    ) -> None:
        super().__init__(master, **kw)
        self._tokens: Optional[Dict[str, str]] = None
        self._icon_img = load_icon(icon_name) if icon_name else None

        self._inner = tk.Frame(self, bd=0, highlightthickness=0)
        # ``pack(expand=True)`` centers the inner frame while still reporting a
        # real requested size (``place`` left the frame at 1x1, so the content
        # rendered off-canvas and the panel looked blank).
        self._inner.pack(expand=True, padx=SPACING["xl"], pady=SPACING["xl"])

        self._icon_label = tk.Label(self._inner, image=self._icon_img, bd=0, highlightthickness=0)
        self._icon_label.pack(pady=(0, SPACING["sm"]))
        self._msg = tk.Label(self._inner, text=message, font=font_role("body"), wraplength=320, justify=tk.CENTER)
        self._msg.pack()
        self._action: Optional[PrimaryButton] = None
        if action_label:
            self._action = PrimaryButton(self._inner, text=action_label, command=on_action or (lambda: None))
            self._action.pack(pady=(SPACING["md"], 0))

        register_themed(self)
        self._try_apply_initial()

    def apply_theme(self, merged: Dict[str, str]) -> None:
        self._tokens = build_tokens(merged)
        bg = self._tokens["bg"]
        # When this empty state sits on a surface card (e.g. the locked screen)
        # the parent background wins, otherwise the panel shows as a slab.
        try:
            pbg = self.master.cget("bg")
            if pbg:
                bg = pbg
        except Exception:
            pass
        self.configure(bg=bg)
        self._inner.configure(bg=bg)
        for w in (self._icon_label, self._msg):
            w.configure(bg=bg)
        self._icon_label.configure(fg=self._tokens["muted"])
        self._msg.configure(fg=self._tokens["muted"])

    def destroy(self) -> None:
        unregister_themed(self)
        super().destroy()

    def _try_apply_initial(self) -> None:
        try:
            if tk._default_root is not None:
                self.apply_theme(get_active_merged())
        except Exception:
            pass


def show_status(
    parent: tk.Misc,
    message: str,
    kind: str = "info",
    timeout_ms: int = 2600,
) -> tk.Label:
    """Show a transient, themed inline status label inside ``parent``.

    ``kind`` is one of ``"info"`` (accent), ``"success"``, ``"danger"``.
    Returns the created label (mostly useful for tests). The label is removed
    automatically after ``timeout_ms``.
    """
    tokens = build_tokens(get_active_merged())
    # ``build_tokens`` carries every raw palette color through, so a theme may
    # define its own ``success``; fall back to the accent instead of a
    # hardcoded green that clashes with the active palette.
    success = tokens.get("success") or tokens["accent"]
    color = {
        "info": tokens["accent"],
        "success": success,
        "danger": tokens["danger"],
    }.get(kind, tokens["accent"])

    # Match whatever the label is packed into (dialog/surface content) so it
    # doesn't render as a mismatched slab; fall back to the window background.
    bg = tokens["bg"]
    try:
        pbg = parent.cget("bg")
        if pbg:
            bg = pbg
    except Exception:
        pass

    label = tk.Label(
        parent, text=message, font=font_role("caption"),
        fg=color, bg=bg, padx=SPACING["sm"], pady=SPACING["xs"],
    )
    label.pack(side=tk.BOTTOM, fill=tk.X, padx=SPACING["md"], pady=(0, SPACING["xs"]))

    def _remove() -> None:
        try:
            label.destroy()
        except Exception:
            pass

    parent.after(timeout_ms, _remove)
    return label


class ConfirmDialog:
    """Themed Yes/No confirmation dialog (see :mod:`.dialogs`)."""

    def __init__(self, parent: tk.Misc, title: str, message: str, on_confirm: Callable[[], None],
                 confirm_label: str = "Yes", cancel_label: str = "No"):
        from .dialogs import Dialog

        self._confirmed = False
        self._on_confirm = on_confirm
        self._win = Dialog(parent, title=title, width=360, height=180)
        self._msg = tk.Label(
            self._win.content, text=message, font=font_role("body"),
            wraplength=300, justify=tk.LEFT,
        )
        self._msg.pack(padx=SPACING["md"], pady=SPACING["md"], anchor=tk.W)

        self._btn_row = tk.Frame(self._win.content, bd=0, highlightthickness=0)
        self._btn_row.pack(side=tk.BOTTOM, fill=tk.X, padx=SPACING["md"], pady=SPACING["md"])

        def _cancel() -> None:
            self._win.destroy()

        def _ok() -> None:
            self._confirmed = True
            _cancel()
            if self._on_confirm is not None:
                self._on_confirm()

        DangerButton(self._btn_row, text=confirm_label, command=_ok).pack(side=tk.RIGHT, padx=(SPACING["sm"], 0))
        PrimaryButton(self._btn_row, text=cancel_label, command=_cancel).pack(side=tk.RIGHT)

        try:
            self._surface_bg = build_tokens(get_active_merged())["surface"]
        except Exception:
            self._surface_bg = "#000000"
        self._msg.configure(bg=self._surface_bg)
        self._btn_row.configure(bg=self._surface_bg)

        # Register so live theme changes recolor this dialog's own widgets.
        register_themed(self)

    @property
    def confirmed(self) -> bool:
        return self._confirmed

    def apply_theme(self, merged: Dict[str, str]) -> None:
        self._tokens = build_tokens(merged)
        bg = self._tokens["surface"]
        self._msg.configure(bg=bg)
        self._btn_row.configure(bg=bg)

    def destroy(self) -> None:
        unregister_themed(self)
        self._win.destroy()
