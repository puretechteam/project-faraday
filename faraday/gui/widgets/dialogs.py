"""
Dialogs: a themed, centered, modal ``Dialog`` base plus reusable
``ThemedPasswordDialog``, ``AboutDialog``, and ``PasswordGeneratorDialog``.
Also a thin launcher for the existing ``ui_theme.ThemeSettingsDialog``.

API contracts (consumed by ``main_window.py`` / ``credential_section.py``):

    ThemedPasswordDialog(parent, title="Unlock Vault", confirm=False,
                          show_generate=True) -> .show() -> str | None
    PasswordGeneratorDialog(parent, title="Password Generator") -> .show() -> str | None
"""

from __future__ import annotations

from typing import Callable, Dict, Optional

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
        super().__init__(parent.winfo_toplevel() if isinstance(parent, tk.Misc) else None)
        self.title(title)
        self._width = width
        self._height = height
        self._title = title
        self._tokens: Optional[Dict[str, str]] = None
        self.transient(parent.winfo_toplevel() if isinstance(parent, tk.Misc) else self)
        self.grab_set()
        self.resizable(True, True)
        # Replace the OS chrome with a custom title bar (below). The 1px floor
        # lets ``fit()`` size the window to its actual content with no empty gap.
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
        self.protocol("WM_DELETE_WINDOW", self.destroy)

        self._center_over(parent)
        register_themed(self)
        self._try_apply_initial()
        # Auto-fit only once content actually exists; subclasses build their
        # widgets after super().__init__() and should call fit() again at the
        # end of their own __init__.
        if hasattr(self, "content") and self.content is not None:
            self.fit()
        # Children (labels/frames) are added by subclasses/callers AFTER this
        # __init__ returns. A timer callback (unlike after_idle) is not drained
        # by the update_idletasks() inside fit(), so this fires once those
        # children exist and they get recolored instead of staying white.
        if self._tokens is not None:
            self.after(0, self._apply_content_theme)

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
        unregister_themed(self)
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
    def _try_apply_initial(self) -> None:
        try:
            if tk._default_root is not None:
                self.apply_theme(get_active_merged())
        except Exception:
            pass

    def _center_over(self, parent: tk.Misc) -> None:
        self.update_idletasks()
        try:
            pw = parent.winfo_width()
            ph = parent.winfo_height()
            px = parent.winfo_rootx()
            py = parent.winfo_rooty()
        except Exception:
            pw, ph, px, py = 800, 600, 100, 100
        x = px + max(0, (pw - self._width) // 2)
        y = py + max(0, (ph - self._height) // 2)
        self.geometry(f"{self._width}x{self._height}+{x}+{y}")

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
        self.grab_set()
        self.focus_set()
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
        self.grab_set()
        self.focus_set()
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
