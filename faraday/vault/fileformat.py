"""
Pure helpers for the version 1 vault file layout (see docs/vault-format.md):

    [4-byte big-endian header length][CBOR header][12-byte nonce][AES-GCM ciphertext]
"""

from dataclasses import dataclass
from typing import Any, Dict

from .crypto import ARGON2_MEMORY_COST, ARGON2_PARALLELISM, ARGON2_TIME_COST, NONCE_LENGTH, VAULT_FORMAT_VERSION
from .storage import create_vault_header, parse_vault_header, serialize_vault_data


@dataclass
class VaultFile:
    header: Dict[str, Any]
    nonce: bytes
    ciphertext: bytes

    @property
    def salt(self) -> bytes:
        return self.header["salt"]

    @property
    def kdf_params(self) -> Dict[str, int]:
        params = self.header.get("kdf_params") or {}
        return {
            "time_cost": params.get("time_cost", ARGON2_TIME_COST),
            "memory_cost": params.get("memory_cost", ARGON2_MEMORY_COST),
            "parallelism": params.get("parallelism", ARGON2_PARALLELISM),
        }


def parse_vault_bytes(data: bytes) -> VaultFile:
    """Split raw vault bytes into header, nonce and ciphertext. Raises ValueError if damaged."""
    if len(data) < 4:
        raise ValueError("Invalid vault file: cannot read header length")
    header_len = int.from_bytes(data[:4], "big")
    header_end = 4 + header_len
    if len(data) < header_end:
        raise ValueError("Invalid vault file: cannot read header")
    try:
        header = parse_vault_header(data[4:header_end])
    except Exception as exc:
        raise ValueError(f"Invalid vault file: unreadable header ({exc})")
    if not isinstance(header, dict) or "salt" not in header:
        raise ValueError("Invalid vault file: header has no salt")
    if header.get("version") != VAULT_FORMAT_VERSION:
        raise ValueError(f"Unsupported vault version: {header.get('version')}")
    nonce = data[header_end:header_end + NONCE_LENGTH]
    if len(nonce) != NONCE_LENGTH:
        raise ValueError("Invalid vault file: cannot read nonce")
    ciphertext = data[header_end + NONCE_LENGTH:]
    if not ciphertext:
        raise ValueError("Invalid vault file: empty ciphertext")
    return VaultFile(header=header, nonce=nonce, ciphertext=ciphertext)


def build_vault_bytes(salt: bytes, kdf_params: Dict[str, int], nonce: bytes, ciphertext: bytes) -> bytes:
    header = create_vault_header(VAULT_FORMAT_VERSION, salt, dict(kdf_params))
    header_bytes = serialize_vault_data(header)
    return len(header_bytes).to_bytes(4, "big") + header_bytes + nonce + ciphertext
