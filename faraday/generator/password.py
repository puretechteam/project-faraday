"""
Password generator with customizable rules and deterministic mode support.
"""

import secrets
from typing import Optional
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.backends import default_backend


GENERATOR_PROFILE_VERSION = 1
LOWERCASE = "abcdefghijklmnopqrstuvwxyz"
UPPERCASE = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
DIGITS = "0123456789"
SYMBOLS = "!@#$%^&*()_+-=[]{}|;:,.<>?"


class PasswordGenerator:
    """Generates cryptographically secure passwords."""
    
    def __init__(self, length: int = 16, use_lowercase: bool = True, use_uppercase: bool = True, use_digits: bool = True, use_symbols: bool = True, exclude_chars: Optional[str] = None):
        """Initialize password generator."""
        self.length = length
        self.use_lowercase = use_lowercase
        self.use_uppercase = use_uppercase
        self.use_digits = use_digits
        self.use_symbols = use_symbols
        self.exclude_chars = set(exclude_chars) if exclude_chars else set()
        self.charset = ""
        if use_lowercase:
            self.charset += LOWERCASE
        if use_uppercase:
            self.charset += UPPERCASE
        if use_digits:
            self.charset += DIGITS
        if use_symbols:
            self.charset += SYMBOLS
        for char in self.exclude_chars:
            self.charset = self.charset.replace(char, "")
        if not self.charset:
            raise ValueError("Character set is empty after exclusions")
    
    def generate(self, deterministic_seed: Optional[bytes] = None) -> str:
        """Generate a password."""
        if deterministic_seed:
            hkdf = HKDF(algorithm=hashes.SHA256(), length=self.length, salt=None, info=b"faraday_password_generator", backend=default_backend())
            random_bytes = hkdf.derive(deterministic_seed)
            return "".join(self.charset[byte_val % len(self.charset)] for byte_val in random_bytes)
        return "".join(secrets.choice(self.charset) for _ in range(self.length))
    
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
