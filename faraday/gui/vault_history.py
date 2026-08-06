"""
Recent vaults history manager.
Stores list of recently opened vault files (paths only, no passwords).
"""

import os
import json
from typing import List
from pathlib import Path


def get_config_dir() -> Path:
    """Get the directory for storing application configuration."""
    return Path.cwd()


def get_history_file() -> Path:
    """Get path to vault history file."""
    return get_config_dir() / ".faraday_vault_history.json"


def load_recent_vaults(max_items: int = 10) -> List[str]:
    """Load list of recently opened vault files."""
    history_file = get_history_file()
    if not history_file.exists():
        return []
    try:
        with open(history_file, 'r', encoding='utf-8') as f:
            vaults = json.load(f).get('recent_vaults', [])
            return [v for v in vaults if os.path.exists(v)][:max_items]
    except (json.JSONDecodeError, IOError, KeyError):
        return []


def save_recent_vault(vault_path: str, max_items: int = 10):
    """Add a vault to recent vaults list."""
    if not vault_path or not os.path.exists(vault_path):
        return
    vault_path = os.path.abspath(vault_path)
    recent_vaults = load_recent_vaults(max_items=max_items * 2)
    if vault_path in recent_vaults:
        recent_vaults.remove(vault_path)
    recent_vaults.insert(0, vault_path)
    try:
        with open(get_history_file(), 'w', encoding='utf-8') as f:
            json.dump({'recent_vaults': recent_vaults[:max_items]}, f, indent=2)
    except IOError:
        pass


def remove_recent_vault(vault_path: str):
    """Remove a vault from recent vaults list."""
    vault_path = os.path.abspath(vault_path)
    recent_vaults = load_recent_vaults(max_items=100)
    if vault_path in recent_vaults:
        recent_vaults.remove(vault_path)
        try:
            with open(get_history_file(), 'w', encoding='utf-8') as f:
                json.dump({'recent_vaults': recent_vaults}, f, indent=2)
        except IOError:
            pass
