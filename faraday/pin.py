"""
Optional local action PIN (toolkit-free; extracted from gui/action_guard.py).

The PIN's Argon2id hash and salt live in ``action_guard.json`` in the app data
folder, in the same format 3.0 used, so an existing PIN keeps working. A short
numeric PIN is weak against offline guessing if someone copies that file; it is
convenience friction, not strong authentication.
"""

import json
import os
import secrets
from typing import Any, Dict, Tuple

import argon2.low_level

from .paths import app_data_dir
from .vault.atomic import atomic_write_bytes

CONFIG_VERSION = 1
PIN_TIME_COST = 2
PIN_MEMORY_KIB = 65536
PIN_PARALLELISM = 2
PIN_HASH_LEN = 32
MAX_PIN_FAILURES = 5


def guard_config_path() -> str:
    return str(app_data_dir() / "action_guard.json")


def load_guard_config() -> Dict[str, Any]:
    path = guard_config_path()
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_guard_config(data: Dict[str, Any]) -> None:
    data = dict(data)
    data["version"] = CONFIG_VERSION
    atomic_write_bytes(guard_config_path(), json.dumps(data, indent=2).encode("utf-8"))


def validate_pin_format(pin: str) -> Tuple[bool, str]:
    if len(pin) < 4:
        return False, "PIN must be at least 4 digits."
    if not pin.isdigit():
        return False, "PIN must contain only digits (0-9)."
    return True, ""


def _hash_pin(pin: str, salt: bytes) -> bytes:
    return argon2.low_level.hash_secret_raw(
        secret=pin.encode("utf-8"),
        salt=salt,
        time_cost=PIN_TIME_COST,
        memory_cost=PIN_MEMORY_KIB,
        parallelism=PIN_PARALLELISM,
        hash_len=PIN_HASH_LEN,
        type=argon2.low_level.Type.ID,
    )


def pin_enabled() -> bool:
    cfg = load_guard_config()
    return bool(cfg.get("enabled") and cfg.get("salt_hex") and cfg.get("hash_hex"))


def verify_pin(pin: str) -> bool:
    cfg = load_guard_config()
    if not pin_enabled():
        return False
    try:
        salt = bytes.fromhex(cfg["salt_hex"])
        expected = bytes.fromhex(cfg["hash_hex"])
    except (ValueError, TypeError):
        return False
    if len(salt) != 16 or len(expected) != PIN_HASH_LEN:
        return False
    return secrets.compare_digest(_hash_pin(pin, salt), expected)


def set_pin(pin: str) -> None:
    ok, message = validate_pin_format(pin)
    if not ok:
        raise ValueError(message)
    salt = secrets.token_bytes(16)
    cfg = load_guard_config()
    cfg.update(enabled=True, salt_hex=salt.hex(), hash_hex=_hash_pin(pin, salt).hex(), offer_shown=True)
    save_guard_config(cfg)


def disable_pin() -> None:
    cfg = load_guard_config()
    cfg.update(enabled=False, offer_shown=True)
    cfg.pop("salt_hex", None)
    cfg.pop("hash_hex", None)
    save_guard_config(cfg)


def offer_shown() -> bool:
    return bool(load_guard_config().get("offer_shown"))


def mark_offer_shown() -> None:
    cfg = load_guard_config()
    cfg["offer_shown"] = True
    save_guard_config(cfg)
