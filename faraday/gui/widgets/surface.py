"""
Reusable surface widgets: ``RoundedSurface`` (a Frame with a canvas-drawn
rounded-rectangle background) and ``Panel`` (a titled card built on top of it).
"""

from __future__ import annotations

import math
from typing import Dict, Optional

import tkinter as tk

from ..design_system import RADIUS, SPACING, TYPOGRAPHY, build_tokens, font_role, get_active_merged, _lighten
from ..ui_theme import register_themed, unregister_themed

# Tokens relied upon (from design_system.build_tokens): bg, bg_elev, border,
# text, muted, accent, danger, surface, hover, on_accent.


def _rounded_rect_points(x: float, y: float, width: float, height: float, radius: float):
    """Return a list of (x, y) points describing a rounded rectangle polygon."""
    radius = min(radius, width / 2.0, height / 2.0)
    if radius <= 0:
        return [(x, y), (x + width, y), (x + width, y + height), (x, y + height)]
    x2, y2 = x + width, y + height
    pts = []

    def _arc(cx, cy, r, start_deg, end_deg):
        steps = max(2, int(abs(end_deg - start_deg) / 15))
        out = []
        for i in range(steps + 1):
            ang = math.radians(start_deg + (end_deg - start_deg) * i / steps)
            out.append((cx + r * math.cos(ang), cy + r * math.sin(ang)))
        return out

    pts.append((x + radius, y))
    pts.append((x2 - radius, y))
    pts.extend(_arc(x2 - radius, y + radius, radius, 270, 360))
    pts.append((x2, y + radius))
    pts.append((x2, y2 - radius))
    pts.extend(_arc(x2 - radius, y2 - radius, radius, 0, 90))
    pts.append((x2 - radius, y2))
    pts.append((x + radius, y2))
    pts.extend(_arc(x + radius, y2 - radius, radius, 90, 180))
    pts.append((x, y2 - radius))
    pts.append((x, y + radius))
    pts.extend(_arc(x + radius, y + radius, radius, 180, 270))
    return pts


class RoundedSurface(tk.Frame):
    """A Frame whose background is a canvas-drawn rounded rectangle.

    Children should be added to ``self.body`` (the inner content area). The
    rounded corners show the surrounding window background, so place instances
    directly on the app background, not on another elevated surface.
    """

    def __init__(
        self,
        master: Optional[tk.Misc] = None,
        bg: Optional[str] = None,
        radius: int = RADIUS["md"],
        border: bool = True,
        **kw,
    ) -> None:
        super().__init__(master, **kw)
        self._radius = radius
        self._use_border = border
        self._bg_override = bg
        self._tokens: Optional[Dict[str, str]] = None

        self.canvas = tk.Canvas(self, highlightthickness=0, bd=0)
        self.canvas.place(x=0, y=0, relwidth=1, relheight=1)
        # The body is ``pack``ed (inset by the radius) rather than ``place``d so
        # the surface's requested size follows its content. The canvas (drawn
        # behind) still shows the rounded corners in the inset ring.
        self.body = tk.Frame(self, bd=0, highlightthickness=0)
        self.body.pack(
            fill=tk.BOTH, expand=True,
            padx=self._radius, pady=self._radius,
        )

        self.bind("<Configure>", lambda _e: self._redraw())
        register_themed(self)
        self._try_apply_initial()

    # -- public api --------------------------------------------------------
    def set_background(self, color: str) -> None:
        """Override the surface fill color (otherwise ``tokens['surface']``)."""
        self._bg_override = color
        self._redraw()

    def apply_theme(self, merged: Dict[str, str]) -> None:
        self._tokens = build_tokens(merged)
        # Color unconditionally: ``_redraw`` early-returns while the widget is
        # unmapped / 1x1 (every card, panel and dialog before its first paint),
        # which would otherwise leave a white SystemButtonFace surface.
        self.configure(bg=self._tokens["bg"])
        self.canvas.configure(bg=self._tokens["bg"])
        self.body.configure(bg=self._fill())
        self._redraw()

    def destroy(self) -> None:
        unregister_themed(self)
        super().destroy()

    # -- drawing -----------------------------------------------------------
    def _try_apply_initial(self) -> None:
        try:
            if tk._default_root is not None:
                self.apply_theme(get_active_merged())
        except Exception:
            pass

    def _fill(self) -> str:
        return self._bg_override or (self._tokens or {}).get("surface", "#000000")

    def _redraw(self) -> None:
        if not self._tokens:
            return
        w = self.winfo_width()
        h = self.winfo_height()
        if w <= 1 or h <= 1:
            return
        fill = self._fill()
        outline = self._tokens["border"] if self._use_border else fill
        inset = 1 if self._use_border else 0
        r = self._radius

        self.canvas.delete("all")
        pts = _rounded_rect_points(inset, inset, w - 2 * inset, h - 2 * inset, r)
        flat = [coord for pt in pts for coord in pt]
        self.canvas.create_polygon(
            *flat,
            fill=fill,
            outline=outline,
            width=1 if self._use_border else 0,
            smooth=False,
        )

        # The body is packed (inset by the radius) in __init__; keep its
        # background in sync. The body is created after the canvas, so it is
        # already stacked on top; nudge it explicitly above the canvas so the
        # rounded corners remain visible and children are never occluded.
        self.body.configure(bg=fill)
        self.body.lift(self.canvas)


class Panel(RoundedSurface):
    """A titled card surface with an optional header label."""

    def __init__(
        self,
        master: Optional[tk.Misc] = None,
        title: Optional[str] = None,
        subtitle: Optional[str] = None,
        radius: int = RADIUS["md"],
        **kw,
    ) -> None:
        # These must exist before ``super().__init__`` because the base class
        # registers for theming and applies the initial theme, which calls
        # ``apply_theme`` -> ``_style_header`` on this (still unbuilt) instance.
        self._title_text = title
        self._subtitle_text = subtitle
        self._header: Optional[tk.Frame] = None
        self._title_label: Optional[tk.Label] = None
        self._subtitle_label: Optional[tk.Label] = None
        self.content: Optional[tk.Frame] = None
        super().__init__(master, radius=radius, **kw)
        self._build_header()

    def _build_header(self) -> None:
        # The content frame always exists, even for a plain ``Panel(master)``
        # with no title/subtitle, so callers can always use ``panel.content``.
        self.content = tk.Frame(self.body, bd=0, highlightthickness=0)
        if not self._title_text and not self._subtitle_text:
            self.content.pack(
                side=tk.TOP, fill=tk.BOTH, expand=True,
                padx=SPACING["md"], pady=SPACING["md"],
            )
            self._style_header()
            return
        self._header = tk.Frame(self.body, bd=0, highlightthickness=0)
        self._header.pack(
            side=tk.TOP, fill=tk.X,
            padx=SPACING["md"], pady=(SPACING["md"], SPACING["xs"]),
        )
        if self._title_text:
            self._title_label = tk.Label(
                self._header, text=self._title_text,
                font=font_role("title"), anchor=tk.W,
            )
            self._title_label.pack(side=tk.TOP, anchor=tk.W)
        if self._subtitle_text:
            self._subtitle_label = tk.Label(
                self._header, text=self._subtitle_text,
                font=font_role("caption"), anchor=tk.W,
            )
            self._subtitle_label.pack(side=tk.TOP, anchor=tk.W, pady=(2, 0))
        # Content frame for user widgets, below the header.
        self.content.pack(
            side=tk.TOP, fill=tk.BOTH, expand=True,
            padx=SPACING["md"], pady=(0, SPACING["md"]),
        )
        self._style_header()

    def _style_header(self) -> None:
        if not self._tokens:
            return
        bg = self._fill()
        if self._header is not None:
            self._header.configure(bg=bg)
        if self.content is not None:
            self.content.configure(bg=bg)
        if self._title_label is not None:
            self._title_label.configure(bg=bg, fg=self._tokens["text"])
        if self._subtitle_label is not None:
            self._subtitle_label.configure(bg=bg, fg=self._tokens["muted"])

    def apply_theme(self, merged: Dict[str, str]) -> None:
        super().apply_theme(merged)
        self._style_header()
