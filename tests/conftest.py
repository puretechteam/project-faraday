"""
Shared test setup.

Every test runs in its own temp folder with app data and the default vault
folder redirected there, and with a guard that fails the test outright if
anything tries to open, replace or delete a file under the repo's real
``vaults/`` folder.
"""

import builtins
import os
import shutil
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


def _real_vault_dirs():
    """The repo's old vaults/ folder and the real default folder (Documents/Faraday)."""
    from faraday.paths import documents_dir
    return [os.path.normcase(os.path.realpath(str(p))) for p in (REPO / "vaults", documents_dir() / "Faraday")]


REAL_VAULT_DIRS = _real_vault_dirs()
FIXTURES = Path(__file__).resolve().parent / "fixtures"
FAST_KDF = {"time_cost": 1, "memory_cost": 8, "parallelism": 1}
PASSWORD = b"correct horse battery staple"


def _is_real_vault_path(path) -> bool:
    try:
        resolved = os.path.normcase(os.path.realpath(os.fspath(path)))
    except (TypeError, ValueError):
        return False
    return any(resolved == d or resolved.startswith(d + os.sep) for d in REAL_VAULT_DIRS)


def _guarded(fn, name):
    def wrapper(*args, **kwargs):
        for arg in args[:2]:
            if isinstance(arg, (str, bytes, os.PathLike)) and _is_real_vault_path(arg):
                raise AssertionError(f"Test tried to {name} the real vault folder: {arg}")
        return fn(*args, **kwargs)
    return wrapper


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    appdata = tmp_path / "appdata"
    vaults = tmp_path / "vaults"
    appdata.mkdir()
    monkeypatch.setenv("FARADAY_APPDATA", str(appdata))
    monkeypatch.setenv("FARADAY_VAULTS_DIR", str(vaults))
    monkeypatch.setenv("LOCALAPPDATA", str(appdata))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(appdata))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(builtins, "open", _guarded(builtins.open, "open"))
    for name in ("open", "replace", "rename", "remove", "unlink", "link"):
        monkeypatch.setattr(os, name, _guarded(getattr(os, name), name))
    for name in ("copy", "copy2", "copyfile", "move", "rmtree"):
        monkeypatch.setattr(shutil, name, _guarded(getattr(shutil, name), name))
    yield tmp_path


@pytest.fixture
def fast_kdf(monkeypatch):
    """Allow tiny Argon2 parameters so tests run in milliseconds."""
    import faraday.vault.crypto as crypto
    monkeypatch.setattr(crypto, "validate_argon2_params", lambda *a, **k: True)
    return dict(FAST_KDF)


@pytest.fixture
def make_vault(tmp_path, fast_kdf):
    """Create an unlocked vault in the temp folder. Call with a name; returns the manager."""
    from faraday.vault.manager import VaultManager
    created = []

    def factory(name="test.vault", password=PASSWORD, **kwargs):
        kwargs.setdefault("auto_lock_seconds", None)
        vm = VaultManager(str(tmp_path / name), password, **kwargs)
        vm.create_vault(kdf_params=fast_kdf)
        created.append(vm)
        return vm

    yield factory
    for vm in created:
        if not vm.is_locked:
            vm.lock_vault()


@pytest.fixture
def reopen(fast_kdf):
    """Open an existing vault path with a fresh manager."""
    from faraday.vault.manager import VaultManager
    opened = []

    def opener(path, password=PASSWORD, **kwargs):
        kwargs.setdefault("auto_lock_seconds", None)
        vm = VaultManager(str(path), password, **kwargs)
        vm.unlock_vault()
        opened.append(vm)
        return vm

    yield opener
    for vm in opened:
        if not vm.is_locked:
            vm.lock_vault()
