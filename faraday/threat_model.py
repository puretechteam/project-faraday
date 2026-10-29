"""
Pure threat-model math shared by the GUIs (no toolkit imports).

Extracted from faraday/gui/threat_panel.py. Every figure is illustrative: it
assumes uniformly random secrets and says nothing about real-world attacks.
"""

import math
import re
import time
from typing import List, Tuple

import argon2
import argon2.low_level

from .vault.crypto import ARGON2_HASH_LENGTH, ARGON2_MEMORY_COST, ARGON2_PARALLELISM, ARGON2_TIME_COST
from .vault.storage import parse_vault_header

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
    ("1 million PCs", 1_000_000.0, "Illustrative fiction only, not a real facility claim."),
]

# Fixed entropy rows for the illustrative offline-time table (uniform-random model).
ENTROPY_TABLE_BIT_ROWS: List[int] = [28, 40, 56, 80, 100, 200, 300]


DISCLAIMER = (
    "These numbers are educational only. They assume random secrets and simple math; real attacks use "
    "wordlists, leaks, phishing, and malware. Argon2 slows each guess but cannot fix a weak password. "
    "Quantum computers do not mean 'instant crack' for password-based vaults in any honest, simple model."
)
