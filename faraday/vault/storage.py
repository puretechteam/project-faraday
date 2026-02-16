"""
Vault storage serialization using CBOR or MessagePack.
No JSON, YAML, or pickle for secret storage.
"""

import cbor2
import os
from typing import Dict, Any
import sys


def get_resource_path(relative_path: str) -> str:
    """Get resource path, handling both normal execution and PyInstaller frozen context."""
    if getattr(sys, 'frozen', False):
        base_path = sys._MEIPASS
    else:
        base_path = __file__
        for _ in range(3):  # storage.py -> vault/ -> faraday/
            base_path = os.path.dirname(base_path)
    return os.path.join(base_path, relative_path)


def serialize_vault_data(data: Dict[str, Any]) -> bytes:
    """Serialize vault data to CBOR format."""
    return cbor2.dumps(data)


def deserialize_vault_data(data: bytes) -> Dict[str, Any]:
    """Deserialize vault data from CBOR format."""
    return cbor2.loads(data)


def create_vault_header(version: int, salt: bytes, kdf_params: Dict[str, Any]) -> Dict[str, Any]:
    """Create vault header with non-sensitive metadata."""
    return {
        "version": version,
        "salt": salt.hex(),
        "kdf": "argon2id",
        "kdf_params": kdf_params
    }


def parse_vault_header(header_data: bytes) -> Dict[str, Any]:
    """Parse vault header from bytes."""
    header = cbor2.loads(header_data)
    if "salt" in header and isinstance(header["salt"], str):
        header["salt"] = bytes.fromhex(header["salt"])
    return header
