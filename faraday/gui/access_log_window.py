"""
Access Log viewer for the Faraday 3.0.0 GUI.

A themed, modal window that lists the audit-trail events recorded by
:mod:`faraday.access_log` (app launches, unlocks, failed sign-ins, locks...).

The viewer is only reachable from inside an unlocked vault, so it always has a
vault context to scope its events to.

The window is read-only: cards have no copy/edit/delete actions. A search bar
filters the visible cards, a "This vault" / "All vaults" toggle switches the
scope, and a "Clear log" button wipes the audit trail after the vault's MASTER
password is confirmed (not the short action PIN). Clearing itself is logged as
a ``log_cleared`` event, and those markers are deliberately kept so other users
can still see which vault cleared the log and when.

Every disk read is defensive: a missing, empty, or corrupt log file yields an
empty list and the window still opens (showing the empty state).

Usage::

    AccessLogDialog(parent, vault_path=current_vault_path,
                    manager=vault_manager).show()
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import tkinter as tk
from tkinter import ttk

from ..access_log import CLEAR_EVENT, clear, describe, load_events, record  # noqa: F401  (record re-exported for callers)
from .action_guard import require_master_password
from .design_system import SPACING, build_tokens, font_role, get_active_merged
from .widgets import (
    CardList,
    DangerButton,
    Dialog,
    EmptyState,
    EntryCard,
    GhostButton,
    PrimaryButton,
    SearchBar,
    show_status,
)

# Events rendered with the danger token so failures stand out at a glance.
_FAILURE_EVENTS = frozenset({"unlock_failed", "unlock_cancelled"})

# Matches ``access_log.load_events``' own default cap.
_MAX_EVENTS = 500

# Prefix marking the active scope button (Tk has no ttk toggle-button state
# that survives the shared Ghost style).
_SELECTED_MARK = "\u2022 "

# Middle dot used in the summary caption.
_DOT = "\u00b7"


# ---------------------------------------------------------------------------
# Timestamp formatting
# ---------------------------------------------------------------------------
def _parse_ts(value: object) -> Optional[datetime]:
    """Parse an ISO-8601 timestamp into a local-time ``datetime``.

    Returns ``None`` for anything unparseable so callers can fall back to the
    raw string instead of raising on a corrupt log entry.
    """
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z") or text.endswith("z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except (ValueError, TypeError):
        return None
    try:
        # Naive values are assumed to be local; aware values are converted.
        return parsed.astimezone()
    except (ValueError, OSError, OverflowError):
        return parsed


def friendly_timestamp(value: object) -> str:
    """Format a log timestamp as a friendly local time.

    ``"Today at 2:58 PM"`` / ``"Yesterday at 9:14 AM"`` / ``"Aug 5, 6:02 PM"``
    for the current year, and ``"Aug 5, 2026, 6:02 PM"`` for older entries.
    """
    moment = _parse_ts(value)
    if moment is None:
        return str(value) if value else "Unknown time"

    hour = moment.hour % 12 or 12
    clock = f"{hour}:{moment.minute:02d} {'AM' if moment.hour < 12 else 'PM'}"

    try:
        today = datetime.now().astimezone().date()
    except Exception:
        today = datetime.now().date()

    day = moment.date()
    if day == today:
        return f"Today at {clock}"
    if day == today - timedelta(days=1):
        return f"Yesterday at {clock}"
    month = moment.strftime("%b")
    if day.year == today.year:
        return f"{month} {day.day}, {clock}"
    return f"{month} {day.day}, {day.year}, {clock}"


# ---------------------------------------------------------------------------
# Cards
# ---------------------------------------------------------------------------
class _LogCard(EntryCard):
    """A read-only :class:`EntryCard` that can tint its title as a failure."""

    def __init__(self, master: tk.Misc, danger: bool = False, **kw) -> None:
        # Set before ``super().__init__`` because the base class applies the
        # initial theme (which calls ``_style``) while still constructing.
        self._danger = bool(danger)
        super().__init__(master, **kw)

    def _style(self) -> None:
        super()._style()
        if not self._danger or not self._tokens:
            return
        try:
            self._title.configure(fg=self._tokens["danger"])
        except (tk.TclError, AttributeError, KeyError):
            pass


# ---------------------------------------------------------------------------
# Dialog
# ---------------------------------------------------------------------------
class AccessLogDialog(Dialog):
    """Modal viewer for the local access log (audit trail)."""

    # Widgets that theme themselves via the registry; the base ``Dialog``
    # recolor pass must not repaint them (it would flatten card colors and
    # drop the danger tint).
    _SELF_THEMED = (CardList, EntryCard, EmptyState, SearchBar)

    def __init__(
        self,
        parent: tk.Misc,
        vault_path: Optional[str] = None,
        manager: Any = None,
        **kw,
    ) -> None:
        super().__init__(parent, title="Access Log", width=680, height=560, **kw)
        # ``manager`` is the unlocked VaultManager. It is optional for backward
        # compatibility, but without it the log cannot be cleared (clearing
        # requires verifying the vault's master password).
        self._manager = manager
        if vault_path is None and manager is not None:
            try:
                vault_path = getattr(manager, "vault_path", None)
            except Exception:
                vault_path = None
        self.vault_path = vault_path
        self._this_vault_only = bool(vault_path)
        self._empty: Optional[EmptyState] = None
        self._cards: List[_LogCard] = []

        # --- Action row (packed first so it can never be squeezed out) ------
        self._buttons = tk.Frame(self.content, bd=0, highlightthickness=0)
        self._buttons.pack(
            side=tk.BOTTOM, fill=tk.X, padx=SPACING["md"], pady=SPACING["md"]
        )
        close_btn = PrimaryButton(self._buttons, text="Close", command=self.destroy)
        close_btn.configure(padding=(10, 4))
        close_btn.pack(side=tk.RIGHT)
        self._clear_btn = DangerButton(
            self._buttons, text="Clear log", command=self._clear_log
        )
        self._clear_btn.configure(padding=(10, 4))
        self._clear_btn.pack(side=tk.LEFT)
        if self._manager is None:
            # Nothing to verify the master password against.
            try:
                self._clear_btn.configure(state=tk.DISABLED)
            except tk.TclError:
                pass

        # --- Toolbar: filter + scope toggle ---------------------------------
        self._toolbar = tk.Frame(self.content, bd=0, highlightthickness=0)
        self._toolbar.pack(
            side=tk.TOP, fill=tk.X,
            padx=SPACING["md"], pady=(SPACING["md"], SPACING["xs"]),
        )
        self._search = SearchBar(
            self._toolbar, on_change=self._on_search, placeholder="Filter events..."
        )
        self._search.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self._all_btn = GhostButton(
            self._toolbar, text="All vaults", command=lambda: self._set_scope(False)
        )
        self._all_btn.configure(padding=(10, 4))
        self._all_btn.pack(side=tk.RIGHT, padx=(SPACING["xs"], 0))
        self._this_btn = GhostButton(
            self._toolbar, text="This vault", command=lambda: self._set_scope(True)
        )
        self._this_btn.configure(padding=(10, 4))
        self._this_btn.pack(side=tk.RIGHT, padx=(SPACING["sm"], 0))
        if not vault_path:
            self._this_btn.configure(state=tk.DISABLED)

        # --- Summary caption -------------------------------------------------
        self._summary = tk.Label(
            self.content, text="", font=font_role("caption"), anchor=tk.W
        )
        self._summary.pack(
            side=tk.TOP, fill=tk.X, padx=SPACING["md"], pady=(0, SPACING["xs"])
        )

        # --- List / empty state ---------------------------------------------
        self._list_container = tk.Frame(self.content, bd=0, highlightthickness=0)
        self._list_container.pack(
            side=tk.TOP, fill=tk.BOTH, expand=True,
            padx=SPACING["md"], pady=(0, SPACING["xs"]),
        )
        self._card_list = CardList(self._list_container)
        self._card_list.pack(fill=tk.BOTH, expand=True)

        self._sync_scope_buttons()
        self._reload()

        self.bind("<Escape>", lambda _e: self.destroy())

        self.fit()
        if self._tokens is not None:
            self._apply_content_theme()

    # -- public api --------------------------------------------------------
    def show(self) -> None:
        """Run the dialog modally, returning once it is closed."""
        try:
            self.grab_set()
            self.focus_set()
        except tk.TclError:
            pass
        self.wait_window(self)
        return None

    def refresh(self) -> None:
        """Re-read the access log from disk and rebuild the card list."""
        self._reload()

    # -- scope -------------------------------------------------------------
    def _set_scope(self, this_vault_only: bool) -> None:
        if this_vault_only and not self.vault_path:
            return
        if this_vault_only == self._this_vault_only:
            return
        self._this_vault_only = this_vault_only
        self._sync_scope_buttons()
        self._reload()

    def _sync_scope_buttons(self) -> None:
        try:
            self._this_btn.configure(
                text=(_SELECTED_MARK + "This vault") if self._this_vault_only else "This vault"
            )
            self._all_btn.configure(
                text="All vaults" if self._this_vault_only else (_SELECTED_MARK + "All vaults")
            )
        except tk.TclError:
            pass

    # -- data --------------------------------------------------------------
    def _load(self) -> List[dict]:
        """Read the log defensively; never raises, worst case returns ``[]``."""
        try:
            scope = self.vault_path if self._this_vault_only else None
            events = load_events(vault_path=scope, limit=_MAX_EVENTS)
        except Exception:
            return []
        if not isinstance(events, list):
            return []
        return [ev for ev in events if isinstance(ev, dict)]

    def _reload(self) -> None:
        events = self._load()
        try:
            self._card_list.clear()
        except Exception:
            pass
        self._cards = []
        self._set_summary(len(events))

        if not events:
            self._show_empty()
            return

        self._hide_empty()
        # ``load_events`` returns oldest-first; a log reads best newest-first.
        for event in reversed(events):
            self._add_card(event)
        self._on_search(self._search.get())

    def _add_card(self, event: dict) -> None:
        try:
            title = describe(event)
        except Exception:
            title = str(event.get("event") or "Unknown event")
        vault_name = event.get("vault_name")
        subtitle = str(vault_name) if vault_name else "(no vault)"
        meta = friendly_timestamp(event.get("ts"))
        is_failure = str(event.get("event") or "") in _FAILURE_EVENTS

        card = _LogCard(
            self._card_list,
            danger=is_failure,
            title=str(title),
            subtitle=subtitle,
            meta=meta,
        )
        # Cards are created after the app-wide theme broadcast, so paint them
        # from the active palette immediately instead of waiting for one.
        try:
            card.apply_theme(get_active_merged())
        except Exception:
            pass
        self._card_list.add(card)
        self._cards.append(card)

    def _set_summary(self, count: int) -> None:
        scope = "this vault" if self._this_vault_only else "all vaults"
        text = f"{count} event{'' if count == 1 else 's'} {_DOT} {scope}"
        try:
            self._summary.configure(text=text)
        except tk.TclError:
            pass

    # -- empty state -------------------------------------------------------
    def _empty_message(self) -> str:
        if self._this_vault_only:
            return "No access events recorded for this vault yet."
        return "No access events recorded yet."

    def _show_empty(self) -> None:
        try:
            self._card_list.pack_forget()
        except Exception:
            pass
        self._destroy_empty()
        try:
            self._empty = EmptyState(
                self._list_container,
                message=self._empty_message(),
                icon_name="lock",
            )
            self._empty.pack(fill=tk.BOTH, expand=True)
        except Exception:
            self._empty = None

    def _hide_empty(self) -> None:
        self._destroy_empty()
        try:
            if not self._card_list.winfo_manager():
                self._card_list.pack(fill=tk.BOTH, expand=True)
        except Exception:
            pass

    def _destroy_empty(self) -> None:
        if self._empty is not None:
            try:
                self._empty.destroy()
            except Exception:
                pass
            self._empty = None

    # -- actions -----------------------------------------------------------
    def _on_search(self, query: str) -> None:
        try:
            self._card_list.filter(query or "")
        except Exception:
            pass

    def _clear_log(self) -> None:
        """Wipe the log after the vault's MASTER password is confirmed.

        The clear itself is recorded first, and ``log_cleared`` markers are
        retained, so the history of who cleared what (and when) survives.
        """
        # No vault manager -> nothing to verify against; refuse rather than
        # fall back to the (much weaker) action PIN.
        if self._manager is None:
            return
        try:
            confirmed = require_master_password(self, self._manager)
        except Exception:
            confirmed = False
        self._regrab()
        # A cancelled / wrong master password must be a silent no-op.
        if not confirmed:
            return

        vault_path = getattr(self._manager, "vault_path", None) or self.vault_path
        try:
            record(CLEAR_EVENT, vault_path=vault_path, source="gui")
        except Exception:
            pass
        try:
            # Keeps the just-recorded marker (and every older one) on disk.
            clear(keep_events=(CLEAR_EVENT,))
        except Exception:
            pass
        self._reload()
        try:
            label = show_status(self.content, "Access log cleared", "success")
            tokens = self._active_tokens()
            if tokens:
                label.configure(bg=tokens["surface"])
        except Exception:
            pass

    def _regrab(self) -> None:
        """Re-assert this window's modal grab after a nested dialog closes."""
        try:
            if self.winfo_exists():
                self.grab_set()
                self.focus_set()
        except tk.TclError:
            pass

    # -- theming -----------------------------------------------------------
    def _active_tokens(self) -> Dict[str, str]:
        if self._tokens:
            return self._tokens
        try:
            return build_tokens(get_active_merged())
        except Exception:
            return {}

    def _apply_content_theme(self) -> None:
        super()._apply_content_theme()
        self._style_chrome()

    def _recolor(self, widget: tk.Misc, surface: str, text: str) -> None:
        """Like ``Dialog._recolor`` but leaves self-theming widgets alone."""
        for child in widget.winfo_children():
            if isinstance(child, self._SELF_THEMED) or isinstance(child, ttk.Widget):
                continue
            try:
                if isinstance(child, tk.Label):
                    child.configure(bg=surface, fg=text)
                elif isinstance(child, tk.Frame):
                    child.configure(bg=surface)
                    self._recolor(child, surface, text)
            except tk.TclError:
                pass

    def _style_chrome(self) -> None:
        """Repaint the caption in the muted token after the generic pass."""
        tokens = self._active_tokens()
        summary = getattr(self, "_summary", None)
        if not tokens or summary is None:
            return
        try:
            summary.configure(bg=tokens["surface"], fg=tokens["muted"])
        except (tk.TclError, KeyError):
            pass


def open_access_log(
    parent: tk.Misc,
    vault_path: Optional[str] = None,
    manager: Any = None,
) -> AccessLogDialog:
    """Open the access log modally and return the (closed) dialog instance."""
    dialog = AccessLogDialog(parent, vault_path=vault_path, manager=manager)
    dialog.show()
    return dialog
