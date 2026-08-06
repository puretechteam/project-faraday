"""
Threat model and illustrative offline-cracking statistics (honest disclaimers, no secret logging).
Shows metadata only for stored passwords (length / charset); never displays or copies vault secrets here.

Restyle (Faraday 3.0.0): built on faraday.gui.widgets (RoundedSurface/Panel, themed EntryCards,
themed buttons). All crypto/logic (Argon2id timing, metadata-only analysis, scoring) is preserved
byte-for-byte. The class is a nav view following the same contract as the other sections:
it does NOT subclass Frame; it creates ``self.frame`` and implements ``refresh`` and ``filter``.
"""

from __future__ import annotations

import math
import queue
import re
import threading
import time
from typing import Callable, List, Optional, Tuple

import argon2.low_level
import tkinter as tk
from tkinter import ttk, messagebox

from ..models.credential_entry import CredentialEntry
from ..models.wifi_entry import WifiEntry
from ..vault.crypto import ARGON2_HASH_LENGTH, ARGON2_TIME_COST, ARGON2_MEMORY_COST, ARGON2_PARALLELISM
from ..vault.manager import VaultManager
from ..vault.storage import parse_vault_header
from .design_system import RADIUS, SPACING, font_role, get_active_merged, build_tokens
from .ui_theme import register_themed
from .widgets import EntryCard, Panel, PrimaryButton

SECONDS_PER_YEAR = 365.25 * 24 * 3600
SECONDS_PER_DAY = 24 * 3600
SECONDS_PER_HOUR = 3600
SECONDS_PER_MINUTE = 60


def _plain_hundredths(value: float) -> str:
    """Grouped number with exactly two decimal places (no scientific notation)."""
    if math.isnan(value) or math.isinf(value):
        return str(value)
    return f"{value:,.2f}"


def _format_plain_with_sci_paren(value: float, unit: str) -> str:
    """Drawn-out number plus unit, then scientific form in parentheses (e.g. seconds)."""
    if math.isnan(value) or math.isinf(value):
        return f"{value} {unit}".strip()
    plain = _plain_hundredths(value)
    sci = f"{value:.3e}"
    return f"{plain} {unit} ({sci})".strip() if unit else f"{plain} ({sci})"


def _format_years_drawn_out_sci(years: float) -> str:
    """Years: drawn-out value + years + (scientific years)."""
    plain = _plain_hundredths(years)
    sci = f"{years:.3e}"
    return f"{plain} years ({sci})"


def _format_span_seconds(sec: float) -> str:
    """
    Human span from a duration in seconds (no leading ~).
    Under one year: days if >= 1 day, else hours / minutes / seconds (seconds use drawn-out + SN).
    One year or more: drawn-out years + scientific years in parentheses.
    """
    if math.isnan(sec) or math.isinf(sec):
        return str(sec)
    sec = abs(sec)
    if sec >= SECONDS_PER_YEAR:
        return _format_years_drawn_out_sci(sec / SECONDS_PER_YEAR)
    if sec >= SECONDS_PER_DAY:
        return f"{_plain_hundredths(sec / SECONDS_PER_DAY)} days"
    if sec >= SECONDS_PER_HOUR:
        return f"{_plain_hundredths(sec / SECONDS_PER_HOUR)} hours"
    if sec >= SECONDS_PER_MINUTE:
        return f"{_plain_hundredths(sec / SECONDS_PER_MINUTE)} minutes"
    return _format_plain_with_sci_paren(sec, "s")


def _read_vault_kdf_params(vault_path: str) -> Tuple[int, int, int]:
    """time_cost, memory_cost (KiB), parallelism from file header."""
    with open(vault_path, "rb") as f:
        hl = int.from_bytes(f.read(4), "big")
        header_bytes = f.read(hl)
    h = parse_vault_header(header_bytes)
    kp = h.get("kdf_params") or {}
    tc = int(kp.get("time_cost", ARGON2_TIME_COST))
    mc = int(kp.get("memory_cost", ARGON2_MEMORY_COST))
    par = int(kp.get("parallelism", ARGON2_PARALLELISM))
    return tc, mc, par


def _benchmark_argon2id(time_cost: int, memory_kib: int, parallelism: int, rounds: int = 2) -> float:
    """Seconds per Argon2id hash (raw), same shape as vault KDF. Discards first run as warm-up."""
    salt = b"faradaybench0000"  # 16 bytes, not a real vault salt
    secret = b"benchmark-password-not-secret"
    for _ in range(1):
        argon2.low_level.hash_secret_raw(
            secret=secret,
            salt=salt,
            time_cost=time_cost,
            memory_cost=memory_kib,
            parallelism=parallelism,
            hash_len=ARGON2_HASH_LENGTH,
            type=argon2.low_level.Type.ID,
        )
    t0 = time.perf_counter()
    for _ in range(rounds):
        argon2.low_level.hash_secret_raw(
            secret=secret,
            salt=salt,
            time_cost=time_cost,
            memory_cost=memory_kib,
            parallelism=parallelism,
            hash_len=ARGON2_HASH_LENGTH,
            type=argon2.low_level.Type.ID,
        )
    return (time.perf_counter() - t0) / rounds


def naive_charset_bits(password: str) -> Tuple[int, float]:
    """
    Upper bound on entropy if password were uniform over a merged charset from detected classes.
    Real human passwords are usually far weaker; this is not min-entropy.
    """
    if not password:
        return 0, 0.0
    size = 0
    if re.search(r"[a-z]", password):
        size += 26
    if re.search(r"[A-Z]", password):
        size += 26
    if re.search(r"[0-9]", password):
        size += 10
    if re.search(r"[^a-zA-Z0-9\s]", password):
        size += 33
    if size == 0:
        if password.isdigit():
            size = 10
        else:
            size = 95
    bits = len(password) * math.log2(size)
    return size, bits


def format_duration_log10_years(log10_sec: float) -> str:
    """Human-readable span from log10(seconds)."""
    log10_y = log10_sec - math.log10(SECONDS_PER_YEAR)
    if log10_y >= 6:
        return f"~10^{log10_y:.1f} years (order of magnitude)"
    total_sec = 10**log10_sec
    return "~" + _format_span_seconds(total_sec)


def time_to_exhaust_bits(bits: float, seconds_per_guess: float) -> str:
    """
    Illustrative time if every guess cost `seconds_per_guess` and the secret had `bits` of entropy
    (uniform random). Uses log domain for large bits.
    """
    if bits <= 0 or seconds_per_guess <= 0:
        return "n/a"
    log10_sec = bits * math.log10(2) + math.log10(seconds_per_guess)
    if log10_sec < 6:
        sec = (2**bits) * seconds_per_guess
        return "~" + _format_span_seconds(sec) + " (illustrative)"
    return format_duration_log10_years(log10_sec) + " (illustrative)"


def _time_to_exhaust_bits_table_cell(bits: float, seconds_per_guess: float) -> str:
    """
    Same duration wording as the rest of the threat panel (full words, DO(SN) for years/seconds).
    """
    if bits <= 0 or seconds_per_guess <= 0:
        return "n/a"
    log10_sec = bits * math.log10(2) + math.log10(seconds_per_guess)
    log10_y = log10_sec - math.log10(SECONDS_PER_YEAR)
    if log10_y >= 6:
        return f"~10^{log10_y:.1f} years (order of magnitude)"
    if log10_sec < 6:
        sec = (2**bits) * seconds_per_guess
    else:
        sec = 10**log10_sec
    return "~" + _format_span_seconds(sec)


# Relative speed vs this PC for one Argon2id derivation (illustrative only).
# First string = column header (plain language; no "…" truncation in the UI).
SCENARIO_MULTIPLIERS: List[Tuple[str, float, str]] = [
    ("This PC", 1.0, "Single machine, same KDF parameters as your vault."),
    ("Slower PC", 0.2, "Illustrative small or low-power device (e.g. Raspberry Pi class); often slower per guess."),
    ("Faster PC", 8.0, "Illustrative high-end desktop; not a guarantee."),
    ("1,000 PCs", 1000.0, "Illustrative: many machines guessing different passwords at the same time."),
    ("1 million PCs", 1_000_000.0, "Illustrative fiction only—not a real facility claim."),
]

# Fixed entropy rows for the illustrative offline-time table (uniform-random model).
ENTROPY_TABLE_BIT_ROWS: List[int] = [28, 40, 56, 80, 100, 200, 300]


DISCLAIMER = (
    "These numbers are educational only. They assume random secrets and simple math; real attacks use "
    "wordlists, leaks, phishing, and malware. Argon2 slows each guess but cannot fix a weak password. "
    "Quantum computers do not mean 'instant crack' for password-based vaults in any honest, simple model."
)


class ThreatModelPanel:
    """Scrollable threat model + illustrative stats (no plaintext secrets shown). Nav view contract."""

    def __init__(self, parent, vault_manager: VaultManager, vault_path: Optional[str] = None):
        self.vault_manager = vault_manager
        self.vault_path = vault_path
        self.frame = ttk.Frame(parent)
        self._kdf: Tuple[int, int, int] = (
            ARGON2_TIME_COST,
            ARGON2_MEMORY_COST,
            ARGON2_PARALLELISM,
        )
        self._t_hash: float = 0.5
        self._measured: bool = False
        self._cred_cards: List[EntryCard] = []
        self._wifi_cards: List[EntryCard] = []
        # (widget, bg_role, fg_role) triples recolored by ``apply_theme``.
        self._themed_labels: List[Tuple[tk.Label, str, str]] = []
        self._themed_frames: List[Tuple[tk.Misc, str]] = []
        # Labels whose ``wraplength`` follows the canvas width.
        self._wrap_labels: List[tk.Label] = []
        self._cred_placeholder: Optional[tk.Label] = None
        self._wifi_placeholder: Optional[tk.Label] = None
        # Argon2id benchmark plumbing (see the "benchmarking" block below).
        self._bench_busy: bool = False
        self._bench_results: "queue.Queue[tuple]" = queue.Queue()
        self._bench_poll_id: Optional[str] = None
        self._build_ui()
        # The Argon2id benchmark is deliberately slow (it derives real keys with
        # the vault's own KDF cost, which can be seconds on a high-cost vault),
        # so it runs on a worker thread. Show a placeholder until it lands.
        self._show_benchmark_pending()
        self.frame.after(400, self._run_benchmark)
        self._refresh_entry_cards()

    def _track_label(self, label: tk.Label, bg_role: str = "surface", fg_role: str = "text",
                     wrapped: bool = False) -> tk.Label:
        """Remember *label* so live theme changes (and resizes) reach it."""
        self._themed_labels.append((label, bg_role, fg_role))
        if wrapped:
            self._wrap_labels.append(label)
        return label

    def _build_ui(self) -> None:
        self._page_bg = "#1e1e1e"
        try:
            _t = build_tokens(get_active_merged())
            bg = _t["bg"]
            self._surface = _t["surface"]
            self._text_fg = _t["text"]
            self._muted_fg = _t["muted"]
        except Exception:
            bg = self._page_bg
            self._surface = "#252526"
            self._text_fg = "#d4d4d4"
            self._muted_fg = "#9d9d9d"

        outer = tk.Frame(self.frame, bg=bg)
        outer.pack(fill=tk.BOTH, expand=True)
        self._themed_frames.append((outer, "bg"))

        canvas = tk.Canvas(outer, bg=bg, highlightthickness=0)
        vsb = ttk.Scrollbar(outer, orient=tk.VERTICAL, command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._canvas = canvas
        self._themed_frames.append((canvas, "bg"))

        inner = tk.Frame(canvas, bg=bg)
        self._inner = inner
        self._themed_frames.append((inner, "bg"))
        win = canvas.create_window((0, 0), window=inner, anchor=tk.NW)

        def _on_cfg(_evt=None):
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.itemconfigure(win, width=canvas.winfo_width())
            self._apply_wraplength()

        inner.bind("<Configure>", _on_cfg)

        def _on_canvas_cfg(e):
            canvas.itemconfigure(win, width=e.width)
            self._apply_wraplength()

        canvas.bind("<Configure>", _on_canvas_cfg)

        def _wheel(evt):
            canvas.yview_scroll(int(-1 * (evt.delta / 120)), "units")

        def _mw_enter(_):
            canvas.bind_all("<MouseWheel>", _wheel)

        def _mw_leave(_):
            canvas.unbind_all("<MouseWheel>")

        canvas.bind("<Enter>", _mw_enter)
        canvas.bind("<Leave>", _mw_leave)

        # Sits directly on the page background (not on a Panel), so it must use
        # the page bg or it reads as a mismatched slab.
        self._disclaimer_lbl = tk.Label(
            inner, text=DISCLAIMER, wraplength=720, justify=tk.LEFT, font=font_role("caption"),
            bg=self._page_bg, fg=self._muted_fg,
        )
        self._disclaimer_lbl.pack(anchor=tk.W, padx=SPACING["md"], pady=SPACING["sm"])
        self._track_label(self._disclaimer_lbl, "bg", "muted", wrapped=True)

        # --- Master password / vault KDF ---
        master = Panel(inner, title="Master password & vault key derivation",
                       subtitle="How long each guessing attempt costs on this PC.")
        master.pack(fill=tk.X, padx=SPACING["md"], pady=SPACING["sm"])

        self._master_info = tk.Label(master.content, text="", wraplength=700, justify=tk.LEFT,
                                     font=font_role("body"), bg=self._surface, fg=self._text_fg)
        self._master_info.pack(anchor=tk.W, padx=SPACING["md"])
        self._track_label(self._master_info, "surface", "text", wrapped=True)

        bench_fr = tk.Frame(master.content, bg=self._surface)
        bench_fr.pack(fill=tk.X, pady=SPACING["sm"])
        self._themed_frames.append((bench_fr, "surface"))
        PrimaryButton(bench_fr, text="Re-run Argon2id timing on this PC",
                      command=self._rebench).pack(side=tk.LEFT)

        candidate_hint = tk.Label(
            master.content,
            text=(
                "Optional: type a candidate passphrase to see a naive upper bound (not min-entropy). "
                "Avoid on shared or untrusted machines. Nothing is stored or sent."
            ),
            wraplength=700,
            justify=tk.LEFT,
            font=font_role("caption"),
            bg=self._surface, fg=self._muted_fg,
        )
        candidate_hint.pack(anchor=tk.W, padx=SPACING["md"], pady=(SPACING["sm"], SPACING["xs"]))
        self._track_label(candidate_hint, "surface", "muted", wrapped=True)
        row = tk.Frame(master.content, bg=self._surface)
        row.pack(fill=tk.X)
        self._themed_frames.append((row, "surface"))
        self._candidate_var = tk.StringVar()
        ent = ttk.Entry(row, textvariable=self._candidate_var, width=50, show="*")
        ent.pack(side=tk.LEFT, padx=(0, SPACING["sm"]))
        PrimaryButton(row, text="Estimate", command=self._estimate_candidate).pack(side=tk.LEFT)

        self._candidate_result = tk.Label(master.content, text="", wraplength=700, justify=tk.LEFT,
                                          font=font_role("body"), bg=self._surface, fg=self._text_fg)
        self._candidate_result.pack(anchor=tk.W, padx=SPACING["md"], pady=SPACING["sm"])
        self._track_label(self._candidate_result, "surface", "text", wrapped=True)

        # Scenario table (fixed entropy rows)
        table_caption = tk.Label(
            master.content,
            text="Illustrative offline time vs passphrase strength (uniform random, same KDF cost per guess):",
            wraplength=700,
            font=font_role("body"),
            bg=self._surface, fg=self._text_fg,
        )
        table_caption.pack(anchor=tk.W, padx=SPACING["md"], pady=(SPACING["md"], SPACING["xs"]))
        self._track_label(table_caption, "surface", "text", wrapped=True)
        col_ids = [f"c{i}" for i in range(len(SCENARIO_MULTIPLIERS))]
        tree_wrap = tk.Frame(master.content, bg=self._surface)
        tree_wrap.pack(fill=tk.X, pady=SPACING["xs"])
        self._themed_frames.append((tree_wrap, "surface"))
        self._tree_master = ttk.Treeview(
            tree_wrap,
            columns=col_ids,
            show="tree headings",
            height=len(ENTROPY_TABLE_BIT_ROWS),
        )
        # No horizontal scrollbar: the columns below stretch to fill the panel
        # width, so the table never needs (or shows) the ugly native-looking
        # bar beneath it. The main panel's vertical scrollbar stays themed ttk.
        self._tree_master.heading("#0", text="Bits")
        self._tree_master.column("#0", width=48, minwidth=40, stretch=False, anchor=tk.CENTER)
        for cid, (label, _m, _n) in zip(col_ids, SCENARIO_MULTIPLIERS):
            self._tree_master.heading(cid, text=label)
            self._tree_master.column(cid, width=150, minwidth=110, stretch=True, anchor=tk.W)
        self._tree_master.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        q_frame = Panel(inner, title="Quantum (honest summary)")
        q_frame.pack(fill=tk.X, padx=SPACING["md"], pady=SPACING["sm"])
        quantum_lbl = tk.Label(
            q_frame.content,
            text=(
                "Grover's algorithm (hypothetical large quantum computer) is often discussed for searching a "
                "fixed symmetric key. Your vault key is derived from a password with Argon2id, not a published "
                "256-bit random key. There is no credible public method to plug in a simple 'quantum speedup' "
                "number for Argon2 + password guessing. For AES-256 with a uniform random key, some oversimplified "
                "accounts suggest a quadratic speedup in idealized models—that still does not translate to "
                "'password vault cracked tomorrow' and ignores memory, noise, and engineering reality."
            ),
            wraplength=700,
            justify=tk.LEFT,
            font=font_role("body"),
            bg=self._surface, fg=self._text_fg,
        )
        quantum_lbl.pack(anchor=tk.W, padx=SPACING["md"])
        self._track_label(quantum_lbl, "surface", "text", wrapped=True)

        scope = Panel(inner, title="What this app does and does not assume")
        scope.pack(fill=tk.X, padx=SPACING["md"], pady=SPACING["sm"])
        scope_lbl = tk.Label(
            scope.content,
            text=(
                "Designed for: stolen vault file, offline guessing cost raised by Argon2id and AES-GCM.\n"
                "Not a substitute for: malware-free PC, phishing awareness, backups, or protection if someone "
                "forces you to unlock. Python cannot guarantee secrets never appear in memory while unlocked."
            ),
            wraplength=700,
            justify=tk.LEFT,
            font=font_role("body"),
            bg=self._surface, fg=self._text_fg,
        )
        scope_lbl.pack(anchor=tk.W, padx=SPACING["md"])
        self._track_label(scope_lbl, "surface", "text", wrapped=True)

        # --- Stored passwords (themed list of entry cards) ---
        cred = Panel(inner, title="Stored credentials (metadata only)")
        cred.pack(fill=tk.BOTH, expand=True, padx=SPACING["md"], pady=SPACING["sm"])
        self._cred_container = tk.Frame(cred.content, bg=self._surface)
        self._cred_container.pack(fill=tk.BOTH, expand=True)
        self._themed_frames.append((self._cred_container, "surface"))

        wifi = Panel(inner, title="Wi-Fi entries (metadata only)")
        wifi.pack(fill=tk.BOTH, expand=True, padx=SPACING["md"], pady=SPACING["sm"])
        self._wifi_container = tk.Frame(wifi.content, bg=self._surface)
        self._wifi_container.pack(fill=tk.BOTH, expand=True)
        self._themed_frames.append((self._wifi_container, "surface"))

        PrimaryButton(inner, text="Refresh entry cards",
                      command=self._refresh_entry_cards).pack(anchor=tk.W, padx=SPACING["md"], pady=SPACING["md"])

        register_themed(self)

    # ------------------------------------------------------------- theming
    def apply_theme(self, merged) -> None:
        """Recolor this panel's own (non-widget-kit) labels and frames."""
        tokens = build_tokens(merged)
        self._page_bg = tokens["bg"]
        self._surface = tokens["surface"]
        self._text_fg = tokens["text"]
        self._muted_fg = tokens["muted"]
        colors = {
            "bg": self._page_bg,
            "surface": self._surface,
            "text": self._text_fg,
            "muted": self._muted_fg,
        }
        for widget, bg_role in list(self._themed_frames):
            try:
                widget.configure(bg=colors.get(bg_role, self._page_bg))
            except tk.TclError:
                pass
        for label, bg_role, fg_role in list(self._themed_labels):
            try:
                label.configure(
                    bg=colors.get(bg_role, self._surface),
                    fg=colors.get(fg_role, self._text_fg),
                )
            except tk.TclError:
                pass

    def _apply_wraplength(self) -> None:
        """Keep wrapped text inside the visible canvas width (no clipping)."""
        try:
            width = self._canvas.winfo_width()
        except (AttributeError, tk.TclError):
            return
        target = max(320, width - 4 * SPACING["md"])
        for lbl in list(self._wrap_labels):
            try:
                if int(lbl.cget("wraplength")) != target:
                    lbl.configure(wraplength=target)
            except tk.TclError:
                pass

    def _show_benchmark_pending(self, note: str = "Measuring… Argon2id timing on this PC (runs shortly).",
                                cell: str = "Measuring…") -> None:
        """Fill the KDF text/table with a placeholder while no timing exists yet."""
        tc, mc, par = self._kdf
        self._master_info.configure(
            text=(
                f"Vault KDF: Argon2id  |  time_cost={tc}, memory={mc} KiB, parallelism={par}\n"
                f"{note}"
            )
        )
        for i in self._tree_master.get_children():
            self._tree_master.delete(i)
        for bits in ENTROPY_TABLE_BIT_ROWS:
            self._tree_master.insert(
                "", tk.END, text=str(bits),
                values=tuple(cell for _ in SCENARIO_MULTIPLIERS),
            )

    # --------------------------------------------------------- benchmarking
    # The benchmark derives Argon2id keys with the VAULT'S OWN cost parameters.
    # On a high-cost vault that is several seconds of pure CPU, so it must never
    # run on the Tk main thread (that is a hard UI freeze right after unlock).
    #
    # Threading contract:
    #   * the worker thread only reads the vault file HEADER (read-only, no
    #     decryption, no writes) and times Argon2id -- it NEVER touches Tk;
    #   * it hands the result to a ``queue.Queue``;
    #   * a main-thread ``after`` poller drains that queue, so every widget
    #     update happens on the main thread.
    # A worker failure can only produce an error record; it can never raise into
    # the app or the Tk event loop.

    def _run_benchmark(self, on_done: Optional[Callable[[Optional[float], Optional[str]], None]] = None) -> None:
        """Start the Argon2id timing off the main thread (returns immediately).

        ``on_done(t_hash, error)`` is invoked on the MAIN thread when the run
        finishes (``error`` is ``None`` on success).
        """
        if self._bench_busy:
            if on_done is not None:
                on_done(None, "An Argon2id timing run is already in progress.")
            return
        self._bench_busy = True
        try:
            threading.Thread(
                target=self._benchmark_worker,
                args=(self.vault_path, on_done),
                name="faraday-argon2-benchmark",
                daemon=True,
            ).start()
        except Exception as e:  # thread could not start: stay usable
            self._bench_busy = False
            if on_done is not None:
                on_done(None, str(e) or e.__class__.__name__)
            return
        self._schedule_bench_poll()

    def _benchmark_worker(self, vault_path: Optional[str],
                          on_done: Optional[Callable[[Optional[float], Optional[str]], None]]) -> None:
        """Worker thread: read the KDF params and time Argon2id. No Tk here."""
        try:
            try:
                kdf = _read_vault_kdf_params(vault_path)
            except Exception:
                kdf = (ARGON2_TIME_COST, ARGON2_MEMORY_COST, ARGON2_PARALLELISM)
            t_hash = _benchmark_argon2id(kdf[0], kdf[1], kdf[2])
            self._bench_results.put((kdf, t_hash, None, on_done))
        except Exception as e:  # never let a background failure reach the app
            try:
                self._bench_results.put((None, None, str(e) or e.__class__.__name__, on_done))
            except Exception:
                pass

    def _schedule_bench_poll(self) -> None:
        """Main thread: re-arm the queue poll (no-op once the frame is gone)."""
        try:
            self._bench_poll_id = self.frame.after(100, self._poll_benchmark)
        except (tk.TclError, RuntimeError):
            self._bench_poll_id = None

    def _poll_benchmark(self) -> None:
        """Main thread: apply a finished benchmark or keep waiting for it."""
        self._bench_poll_id = None
        try:
            kdf, t_hash, error, on_done = self._bench_results.get_nowait()
        except queue.Empty:
            if self._bench_busy:
                self._schedule_bench_poll()
            return
        self._bench_busy = False
        if error is None:
            self._apply_benchmark(kdf, t_hash)
        if on_done is not None:
            try:
                on_done(t_hash, error)
            except Exception:
                pass

    def _apply_benchmark(self, kdf: Tuple[int, int, int], t_hash: float) -> None:
        """Main thread: publish a measured timing into the UI."""
        self._kdf = kdf
        self._t_hash = t_hash
        self._measured = True
        try:
            if not self.frame.winfo_exists():
                return
            self._fill_master_text()
            self._fill_entropy_table()
            # Cards built before the (deferred) measurement carry placeholder
            # timings, so rebuild them with the measured value.
            self._refresh_entry_cards()
        except tk.TclError:
            pass

    def _rebench(self) -> None:
        # Paint the "Measuring…" state first; the benchmark itself runs on a
        # worker thread, so the button stays responsive while it works.
        if self._bench_busy:
            messagebox.showinfo("Timing", "An Argon2id timing run is already in progress.")
            return
        self._show_benchmark_pending("Measuring… (re-running Argon2id timing on this PC).")
        try:
            self.frame.update_idletasks()
        except tk.TclError:
            pass
        self._run_benchmark(on_done=self._rebench_done)

    def _rebench_done(self, t_hash: Optional[float], error: Optional[str]) -> None:
        """Main-thread completion callback for the "Re-run timing" button."""
        if error is not None:
            self._show_benchmark_pending(
                "Argon2id timing could not be measured on this PC.", cell="n/a",
            )
            messagebox.showerror("Benchmark failed", error)
            return
        messagebox.showinfo("Timing", f"~{(t_hash or 0.0) * 1000:.2f} ms per Argon2id hash (this PC).")

    def _fill_master_text(self) -> None:
        tc, mc, par = self._kdf
        ms = self._t_hash * 1000
        gps = 1.0 / self._t_hash if self._t_hash > 0 else 0
        self._master_info.configure(
            text=(
                f"Vault KDF: Argon2id  |  time_cost={tc}, memory={mc} KiB, parallelism={par}\n"
                f"Measured on this PC: ~{ms:.2f} ms per full derivation (benchmark secret, same parameters).\n"
                f"Illustrative max guesses/s on this PC (one core path): ~{gps:.2f} (parallel attackers try many passwords at once)."
            )
        )

    def _fill_entropy_table(self) -> None:
        for i in self._tree_master.get_children():
            self._tree_master.delete(i)
        for bits in ENTROPY_TABLE_BIT_ROWS:
            vals = []
            for _name, mult, _note in SCENARIO_MULTIPLIERS:
                t_g = self._t_hash / mult if mult > 0 else self._t_hash
                vals.append(_time_to_exhaust_bits_table_cell(float(bits), t_g))
            self._tree_master.insert("", tk.END, text=str(bits), values=tuple(vals))

    def _estimate_candidate(self) -> None:
        s = self._candidate_var.get()
        if not s:
            self._candidate_result.configure(text="")
            return
        _cs, bits = naive_charset_bits(s)
        t_g = self._t_hash
        line = (
            f"Naive upper bound (uniform random over detected classes): ~{bits:.2f} bits. "
            f"On this PC (measured Argon2): {time_to_exhaust_bits(bits, t_g)} to exhaust that idealized space sequentially."
        )
        self._candidate_result.configure(text=line)

    def refresh(self) -> None:
        """Re-scan vault entries (same benchmark timing; use Re-run for new Argon2 timing)."""
        self._refresh_entry_cards()

    def filter(self, query: str) -> None:
        """Topbar search: hide entry cards that don't match the query (no-op when empty)."""
        q = (query or "").strip().lower()
        if not q:
            for card in self._cred_cards + self._wifi_cards:
                card.pack(fill=tk.X, pady=SPACING["xs"])
            self._sync_placeholder(self._cred_placeholder, bool(self._cred_cards))
            self._sync_placeholder(self._wifi_placeholder, bool(self._wifi_cards))
            return
        cred_hit = False
        wifi_hit = False
        for card in self._cred_cards:
            if card.matches(q):
                card.pack(fill=tk.X, pady=SPACING["xs"])
                cred_hit = True
            else:
                card.pack_forget()
        for card in self._wifi_cards:
            if card.matches(q):
                card.pack(fill=tk.X, pady=SPACING["xs"])
                wifi_hit = True
            else:
                card.pack_forget()
        self._sync_placeholder(self._cred_placeholder, cred_hit)
        self._sync_placeholder(self._wifi_placeholder, wifi_hit)

    @staticmethod
    def _sync_placeholder(label: Optional[tk.Label], has_visible_cards: bool) -> None:
        """Hide the "nothing here" label while any card is visible, else show it."""
        if label is None:
            return
        try:
            if has_visible_cards:
                label.pack_forget()
            elif not label.winfo_ismapped():
                label.pack(anchor=tk.W)
        except tk.TclError:
            pass

    def _refresh_entry_cards(self) -> None:
        for w in self._cred_container.winfo_children():
            w.destroy()
        for w in self._wifi_container.winfo_children():
            w.destroy()
        self._cred_cards = []
        self._wifi_cards = []
        self._cred_placeholder = None
        self._wifi_placeholder = None
        # Drop handles to labels that were just destroyed.
        kept = []
        for item in self._themed_labels:
            try:
                if item[0].winfo_exists():
                    kept.append(item)
            except tk.TclError:
                pass
        self._themed_labels = kept

        if self.vault_manager.is_locked:
            return

        try:
            creds = self.vault_manager.list_entries(entry_type="credential")
        except Exception:
            creds = []
        cred_shown = 0
        for entry in creds:
            if not isinstance(entry, CredentialEntry):
                continue
            self._add_password_card(self._cred_container, self._cred_cards, "Credential",
                                    entry.site_note, entry.username, entry.password)
            cred_shown += 1
        self._cred_placeholder = tk.Label(self._cred_container, text="No credential entries.",
                                          bg=self._surface, fg=self._muted_fg)
        self._track_label(self._cred_placeholder, "surface", "muted")
        if cred_shown == 0:
            self._cred_placeholder.pack(anchor=tk.W)

        try:
            wifis = self.vault_manager.list_entries(entry_type="wifi")
        except Exception:
            wifis = []
        wifi_shown = 0
        for entry in wifis:
            if not isinstance(entry, WifiEntry):
                continue
            self._add_password_card(
                self._wifi_container, self._wifi_cards, "Wi-Fi",
                entry.network_name, entry.security_type or "", entry.password,
            )
            wifi_shown += 1
        self._wifi_placeholder = tk.Label(self._wifi_container, text="No Wi-Fi entries.",
                                          bg=self._surface, fg=self._muted_fg)
        self._track_label(self._wifi_placeholder, "surface", "muted")
        if wifi_shown == 0:
            self._wifi_placeholder.pack(anchor=tk.W)

    def _add_password_card(self, parent, store: List[EntryCard], kind: str,
                           title: str, subtitle: str, password: str) -> None:
        pw = password or ""
        _cs, bits = naive_charset_bits(pw)
        n = len(pw)
        title_disp = (title or "(no title)")[:60]
        sub_disp = (subtitle or "")[:80]
        meta_lines = [
            f"Password length: {n} characters",
            f"Naive max entropy if uniform (not real min-entropy): ~{bits:.2f} bits",
        ]
        if n > 0:
            for _name, mult, _n in SCENARIO_MULTIPLIERS[:3]:
                t_g = self._t_hash / mult if mult > 0 else self._t_hash
                meta_lines.append(f"Illustrative TTC ({_name}): {time_to_exhaust_bits(bits, t_g)}")
        card = EntryCard(
            parent,
            title=f"{kind}: {title_disp}",
            subtitle=sub_disp,
            meta="\n".join(meta_lines),
        )
        card.pack(fill=tk.X, pady=SPACING["xs"])
        store.append(card)
