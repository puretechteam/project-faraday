"""
Threat model and illustrative offline-cracking statistics (honest disclaimers, no secret logging).
Shows metadata only for stored passwords (length / charset); never displays or copies vault secrets here.
"""

from __future__ import annotations

import math
import re
import time
from typing import List, Optional, Tuple

import argon2.low_level
import tkinter as tk
from tkinter import ttk, messagebox

from ..models.credential_entry import CredentialEntry
from ..models.wifi_entry import WifiEntry
from ..vault.crypto import ARGON2_HASH_LENGTH, ARGON2_TIME_COST, ARGON2_MEMORY_COST, ARGON2_PARALLELISM
from ..vault.manager import VaultManager
from ..vault.storage import parse_vault_header

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
    """Scrollable threat model + illustrative stats (no plaintext secrets shown)."""

    def __init__(self, parent, vault_manager: VaultManager, vault_path: str):
        self.vault_manager = vault_manager
        self.vault_path = vault_path
        self.frame = ttk.Frame(parent)
        self._kdf: Tuple[int, int, int] = (
            ARGON2_TIME_COST,
            ARGON2_MEMORY_COST,
            ARGON2_PARALLELISM,
        )
        self._t_hash: float = 0.5
        self._build_ui()
        self._run_benchmark()
        self._refresh_entry_cards()

    def _build_ui(self) -> None:
        outer = ttk.Frame(self.frame)
        outer.pack(fill=tk.BOTH, expand=True)
        canvas = tk.Canvas(outer, highlightthickness=0)
        vsb = ttk.Scrollbar(outer, orient=tk.VERTICAL, command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        inner = ttk.Frame(canvas)
        self._inner = inner
        win = canvas.create_window((0, 0), window=inner, anchor=tk.NW)

        def _on_cfg(_evt=None):
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.itemconfigure(win, width=canvas.winfo_width())

        inner.bind("<Configure>", _on_cfg)
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(win, width=e.width))

        def _wheel(evt):
            canvas.yview_scroll(int(-1 * (evt.delta / 120)), "units")

        def _mw_enter(_):
            canvas.bind_all("<MouseWheel>", _wheel)

        def _mw_leave(_):
            canvas.unbind_all("<MouseWheel>")

        canvas.bind("<Enter>", _mw_enter)
        canvas.bind("<Leave>", _mw_leave)

        self._disclaimer_lbl = ttk.Label(inner, text=DISCLAIMER, wraplength=720, justify=tk.LEFT)
        self._disclaimer_lbl.pack(anchor=tk.W, padx=8, pady=6)

        # --- Master password / vault KDF ---
        master = ttk.LabelFrame(inner, text="Master password & vault key derivation", padding=10)
        master.pack(fill=tk.X, padx=8, pady=6)
        self._master_info = ttk.Label(master, text="", wraplength=700, justify=tk.LEFT)
        self._master_info.pack(anchor=tk.W)

        bench_fr = ttk.Frame(master)
        bench_fr.pack(fill=tk.X, pady=6)
        ttk.Button(bench_fr, text="Re-run Argon2id timing on this PC", command=self._rebench).pack(side=tk.LEFT)

        ttk.Label(
            master,
            text=(
                "Optional: type a candidate passphrase to see a naive upper bound (not min-entropy). "
                "Avoid on shared or untrusted machines. Nothing is stored or sent."
            ),
            wraplength=700,
            justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(8, 2))
        row = ttk.Frame(master)
        row.pack(fill=tk.X)
        self._candidate_var = tk.StringVar()
        ent = ttk.Entry(row, textvariable=self._candidate_var, width=50, show="*")
        ent.pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(row, text="Estimate", command=self._estimate_candidate).pack(side=tk.LEFT)

        self._candidate_result = ttk.Label(master, text="", wraplength=700, justify=tk.LEFT)
        self._candidate_result.pack(anchor=tk.W, pady=4)

        # Scenario table (fixed entropy rows)
        ttk.Label(
            master,
            text="Illustrative offline time vs passphrase strength (uniform random, same KDF cost per guess):",
            wraplength=700,
        ).pack(anchor=tk.W, pady=(10, 4))
        col_ids = [f"c{i}" for i in range(len(SCENARIO_MULTIPLIERS))]
        tree_wrap = ttk.Frame(master)
        tree_wrap.pack(fill=tk.X, pady=4)
        self._tree_master = ttk.Treeview(
            tree_wrap,
            columns=col_ids,
            show="tree headings",
            height=len(ENTROPY_TABLE_BIT_ROWS),
        )
        tree_hsb = ttk.Scrollbar(tree_wrap, orient=tk.HORIZONTAL, command=self._tree_master.xview)
        self._tree_master.configure(xscrollcommand=tree_hsb.set)
        self._tree_master.heading("#0", text="Bits")
        self._tree_master.column("#0", width=44, minwidth=40, stretch=False, anchor=tk.CENTER)
        for cid, (label, _m, _n) in zip(col_ids, SCENARIO_MULTIPLIERS):
            self._tree_master.heading(cid, text=label)
            self._tree_master.column(cid, width=200, minwidth=120, stretch=True, anchor=tk.W)
        self._tree_master.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        tree_hsb.pack(side=tk.BOTTOM, fill=tk.X)

        q_frame = ttk.LabelFrame(inner, text="Quantum (honest summary)", padding=10)
        q_frame.pack(fill=tk.X, padx=8, pady=6)
        ttk.Label(
            q_frame,
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
        ).pack(anchor=tk.W)

        scope = ttk.LabelFrame(inner, text="What this app does and does not assume", padding=10)
        scope.pack(fill=tk.X, padx=8, pady=6)
        ttk.Label(
            scope,
            text=(
                "Designed for: stolen vault file, offline guessing cost raised by Argon2id and AES-GCM.\n"
                "Not a substitute for: malware-free PC, phishing awareness, backups, or protection if someone "
                "forces you to unlock. Python cannot guarantee secrets never appear in memory while unlocked."
            ),
            wraplength=700,
            justify=tk.LEFT,
        ).pack(anchor=tk.W)

        # --- Stored passwords ---
        cred_hdr = ttk.LabelFrame(inner, text="Stored credentials (metadata only)", padding=10)
        cred_hdr.pack(fill=tk.BOTH, expand=True, padx=8, pady=6)
        self._cred_container = ttk.Frame(cred_hdr)
        self._cred_container.pack(fill=tk.BOTH, expand=True)

        wifi_hdr = ttk.LabelFrame(inner, text="Wi-Fi entries (metadata only)", padding=10)
        wifi_hdr.pack(fill=tk.BOTH, expand=True, padx=8, pady=6)
        self._wifi_container = ttk.Frame(wifi_hdr)
        self._wifi_container.pack(fill=tk.BOTH, expand=True)

        ttk.Button(inner, text="Refresh entry cards", command=self._refresh_entry_cards).pack(anchor=tk.W, padx=8, pady=8)

    def _rebench(self) -> None:
        try:
            self._run_benchmark()
            messagebox.showinfo("Timing", f"~{self._t_hash * 1000:.2f} ms per Argon2id hash (this PC).")
        except Exception as e:
            messagebox.showerror("Benchmark failed", str(e))

    def _run_benchmark(self) -> None:
        try:
            self._kdf = _read_vault_kdf_params(self.vault_path)
        except Exception:
            self._kdf = (ARGON2_TIME_COST, ARGON2_MEMORY_COST, ARGON2_PARALLELISM)
        self._t_hash = _benchmark_argon2id(self._kdf[0], self._kdf[1], self._kdf[2])
        self._fill_master_text()
        self._fill_entropy_table()

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

    def _refresh_entry_cards(self) -> None:
        for w in self._cred_container.winfo_children():
            w.destroy()
        for w in self._wifi_container.winfo_children():
            w.destroy()

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
            self._add_password_card(self._cred_container, "Credential", entry.site_note, entry.username, entry.password)
            cred_shown += 1
        if cred_shown == 0:
            ttk.Label(self._cred_container, text="No credential entries.").pack(anchor=tk.W)

        try:
            wifis = self.vault_manager.list_entries(entry_type="wifi")
        except Exception:
            wifis = []
        wifi_shown = 0
        for entry in wifis:
            if not isinstance(entry, WifiEntry):
                continue
            self._add_password_card(
                self._wifi_container,
                "Wi-Fi",
                entry.network_name,
                entry.security_type or "",
                entry.password,
            )
            wifi_shown += 1
        if wifi_shown == 0:
            ttk.Label(self._wifi_container, text="No Wi-Fi entries.").pack(anchor=tk.W)

    def _add_password_card(self, parent, kind: str, title: str, subtitle: str, password: str) -> None:
        pw = password or ""
        _cs, bits = naive_charset_bits(pw)
        n = len(pw)
        title_disp = (title or "(no title)")[:60]
        sub_disp = (subtitle or "")[:80]
        card = ttk.LabelFrame(parent, text=f"{kind}: {title_disp}", padding=8)
        card.pack(fill=tk.X, pady=4)
        lines = [
            f"Note / meta: {sub_disp}",
            f"Password length: {n} characters",
            f"Naive max entropy if uniform (not real min-entropy): ~{bits:.2f} bits",
        ]
        if n > 0:
            for _name, mult, _n in SCENARIO_MULTIPLIERS[:3]:
                t_g = self._t_hash / mult if mult > 0 else self._t_hash
                lines.append(f"Illustrative TTC ({_name}): {time_to_exhaust_bits(bits, t_g)}")
        ttk.Label(card, text="\n".join(lines), wraplength=680, justify=tk.LEFT).pack(anchor=tk.W)
