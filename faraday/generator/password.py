"""
Password generator with customizable rules and deterministic mode support,
plus a diceware-style passphrase generator and a simple strength estimate.
"""

import math
import os
import secrets
from typing import List, Optional

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.backends import default_backend


GENERATOR_PROFILE_VERSION = 1
LOWERCASE = "abcdefghijklmnopqrstuvwxyz"
UPPERCASE = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
DIGITS = "0123456789"
SYMBOLS = "!@#$%^&*()_+-=[]{}|;:,.<>?"
AMBIGUOUS = "Il1O0o"
MIN_LENGTH = 8
MAX_LENGTH = 128


class PasswordGenerator:
    """Generates cryptographically secure passwords.

    Random (non-deterministic) passwords always contain at least one
    character from every enabled class.
    """

    def __init__(self, length: int = 16, use_lowercase: bool = True, use_uppercase: bool = True, use_digits: bool = True, use_symbols: bool = True, exclude_chars: Optional[str] = None, exclude_ambiguous: bool = False):
        """Initialize password generator."""
        if not MIN_LENGTH <= int(length) <= MAX_LENGTH:
            raise ValueError(f"Length must be between {MIN_LENGTH} and {MAX_LENGTH}")
        self.length = int(length)
        self.use_lowercase = use_lowercase
        self.use_uppercase = use_uppercase
        self.use_digits = use_digits
        self.use_symbols = use_symbols
        self.exclude_chars = set(exclude_chars) if exclude_chars else set()
        if exclude_ambiguous:
            self.exclude_chars |= set(AMBIGUOUS)
        self.classes: List[str] = []
        for enabled, chars in ((use_lowercase, LOWERCASE), (use_uppercase, UPPERCASE), (use_digits, DIGITS), (use_symbols, SYMBOLS)):
            if enabled:
                kept = "".join(c for c in chars if c not in self.exclude_chars)
                if kept:
                    self.classes.append(kept)
        self.charset = "".join(self.classes)
        if not self.charset:
            raise ValueError("Character set is empty after exclusions")

    def generate(self, deterministic_seed: Optional[bytes] = None) -> str:
        """Generate a password."""
        if deterministic_seed:
            hkdf = HKDF(algorithm=hashes.SHA256(), length=self.length, salt=None, info=b"faraday_password_generator", backend=default_backend())
            random_bytes = hkdf.derive(deterministic_seed)
            return "".join(self.charset[byte_val % len(self.charset)] for byte_val in random_bytes)
        chars = [secrets.choice(cls) for cls in self.classes]
        chars += [secrets.choice(self.charset) for _ in range(self.length - len(chars))]
        # Fisher-Yates with a CSPRNG so the guaranteed characters land anywhere.
        for i in range(len(chars) - 1, 0, -1):
            j = secrets.randbelow(i + 1)
            chars[i], chars[j] = chars[j], chars[i]
        return "".join(chars)

    @property
    def entropy_bits(self) -> float:
        return self.length * math.log2(len(self.charset))

    def to_dict(self) -> dict:
        """Convert generator config to dictionary."""
        return {
            "version": GENERATOR_PROFILE_VERSION,
            "length": self.length,
            "use_lowercase": self.use_lowercase,
            "use_uppercase": self.use_uppercase,
            "use_digits": self.use_digits,
            "use_symbols": self.use_symbols,
            "exclude_chars": list(self.exclude_chars) if self.exclude_chars else []
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'PasswordGenerator':
        """Create generator from dictionary."""
        return cls(
            length=data.get("length", 16),
            use_lowercase=data.get("use_lowercase", True),
            use_uppercase=data.get("use_uppercase", True),
            use_digits=data.get("use_digits", True),
            use_symbols=data.get("use_symbols", True),
            exclude_chars="".join(data.get("exclude_chars", []))
        )


_WORDS: Optional[List[str]] = None


def load_wordlist() -> List[str]:
    """The EFF large wordlist (7,776 words, CC BY 3.0 US; see WORDLIST_ATTRIBUTION.md)."""
    global _WORDS
    if _WORDS is None:
        path = os.path.join(os.path.dirname(__file__), "eff_large_wordlist.txt")
        with open(path, encoding="ascii") as fh:
            _WORDS = [w.strip() for w in fh if w.strip()]
    return _WORDS


class PassphraseGenerator:
    """Random words joined by a separator, e.g. ``Mango-River-Cactus-Lantern7``."""

    MIN_WORDS = 3
    MAX_WORDS = 12

    def __init__(self, words: int = 5, separator: str = "-", capitalize: bool = True, add_number: bool = True):
        if not self.MIN_WORDS <= int(words) <= self.MAX_WORDS:
            raise ValueError(f"Word count must be between {self.MIN_WORDS} and {self.MAX_WORDS}")
        self.words = int(words)
        self.separator = separator
        self.capitalize = capitalize
        self.add_number = add_number

    def generate(self) -> str:
        wordlist = load_wordlist()
        chosen = [secrets.choice(wordlist) for _ in range(self.words)]
        if self.capitalize:
            chosen = [w.capitalize() for w in chosen]
        if self.add_number:
            i = secrets.randbelow(len(chosen))
            chosen[i] = chosen[i] + str(secrets.randbelow(10))
        return self.separator.join(chosen)

    @property
    def entropy_bits(self) -> float:
        bits = self.words * math.log2(len(load_wordlist()))
        if self.add_number:
            bits += math.log2(10) + math.log2(self.words)
        return bits


def estimate_entropy(password: str) -> float:
    """Rough upper-bound entropy in bits from length and character classes used.

    Penalises the most common weaknesses (repeats, short length) a little; it
    is a guide for a strength meter, not a guarantee.
    """
    if not password:
        return 0.0
    pool = 0
    if any(c.islower() for c in password):
        pool += 26
    if any(c.isupper() for c in password):
        pool += 26
    if any(c.isdigit() for c in password):
        pool += 10
    if any(not c.isalnum() for c in password):
        pool += 33
    pool = max(pool, 10)
    unique_ratio = len(set(password)) / len(password)
    effective_length = len(password) * (0.5 + 0.5 * unique_ratio)
    return effective_length * math.log2(pool)


def strength_label(bits: float) -> str:
    if bits < 40:
        return "Weak"
    if bits < 60:
        return "Fair"
    if bits < 80:
        return "Strong"
    return "Very strong"
