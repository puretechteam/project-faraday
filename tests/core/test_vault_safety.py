"""The data-safety guarantees of the vault core."""

import os
import shutil
import threading
import time

import pytest
from cryptography.exceptions import InvalidTag

from faraday.models.credential_entry import CredentialEntry
from faraday.models.opaque_entry import OpaqueEntry
from faraday.models.wifi_entry import WifiEntry
from faraday.vault import atomic, fileformat
from faraday.vault.errors import (
    AttachmentsPresentError,
    VaultChangedOnDiskError,
    VaultInUseError,
    VaultLockedError,
    VaultReadOnlyError,
)
from faraday.vault.manager import VaultManager
from faraday.vault.storage import deserialize_vault_data, serialize_vault_data
from tests.conftest import FIXTURES, PASSWORD


def cred(**kw):
    kw.setdefault("username", "alice")
    kw.setdefault("password", "pw")
    return CredentialEntry(**kw)


# ---------------------------------------------------------------- guard

def test_real_vault_guard_blocks_access():
    from tests.conftest import REPO
    with pytest.raises(AssertionError):
        open(REPO / "vaults" / "Main.vault", "rb")


# ---------------------------------------------------------------- basics

def test_create_unlock_roundtrip(make_vault, reopen):
    vm = make_vault()
    vm.add_entry(cred(site_note="example.com"))
    path = vm.vault_path
    vm.lock_vault()
    vm2 = reopen(path)
    [entry] = vm2.list_entries()
    assert entry.username == "alice" and entry.site_note == "example.com"


def test_wrong_password_raises(make_vault, reopen):
    vm = make_vault()
    path = vm.vault_path
    vm.lock_vault()
    with pytest.raises(InvalidTag):
        reopen(path, password=b"wrong")


def test_create_refuses_existing_file(make_vault, fast_kdf):
    vm = make_vault()
    original = open(vm.vault_path, "rb").read()
    vm.lock_vault()
    other = VaultManager(vm.vault_path, b"another password", auto_lock_seconds=None)
    with pytest.raises(FileExistsError):
        other.create_vault(kdf_params=fast_kdf)
    assert open(vm.vault_path, "rb").read() == original


def test_locked_vault_refuses_access(make_vault):
    vm = make_vault()
    vm.lock_vault()
    with pytest.raises(VaultLockedError):
        vm.list_entries()
    with pytest.raises(RuntimeError):  # older callers catch RuntimeError
        vm.add_entry(cred())


# ---------------------------------------------------------------- salt from memory

def test_save_uses_in_memory_salt_not_disk(make_vault, reopen, tmp_path):
    vm = make_vault()
    vm.add_entry(cred())
    # Simulate another program rewriting the header with a different salt while
    # we are open. The old code re-read that salt and wrote an unopenable vault.
    data = open(vm.vault_path, "rb").read()
    vf = fileformat.parse_vault_bytes(data)
    tampered = fileformat.build_vault_bytes(os.urandom(16), vf.kdf_params, vf.nonce, vf.ciphertext)
    atomic.atomic_write_bytes(vm.vault_path, tampered)
    with pytest.raises(VaultChangedOnDiskError):
        vm.add_entry(cred(username="bob"))
    # Nothing was written over the changed file.
    assert open(vm.vault_path, "rb").read() == tampered


def test_verify_password_ignores_disk(make_vault):
    vm = make_vault()
    os.remove(vm.vault_path)  # verification must not need the file
    assert vm.verify_password(PASSWORD)
    assert not vm.verify_password(b"nope")


# ---------------------------------------------------------------- atomic writes

def test_atomic_write_keeps_original_when_replace_fails(tmp_path, monkeypatch):
    tmp_path = tmp_path / "w"
    tmp_path.mkdir()
    target = tmp_path / "file.bin"
    target.write_bytes(b"original")

    def boom(*a, **k):
        raise OSError("disk full")
    monkeypatch.setattr(atomic.os, "replace", boom)
    with pytest.raises(OSError):
        atomic.atomic_write_bytes(str(target), b"new data")
    assert target.read_bytes() == b"original"
    assert [p.name for p in tmp_path.iterdir()] == ["file.bin"]  # no temp left behind


def test_atomic_write_fsyncs(tmp_path, monkeypatch):
    calls = []
    real = os.fsync
    monkeypatch.setattr(atomic.os, "fsync", lambda fd: (calls.append(fd), real(fd)))
    atomic.atomic_write_bytes(str(tmp_path / "f"), b"x")
    assert calls


def test_atomic_write_no_overwrite(tmp_path):
    target = tmp_path / "f"
    target.write_bytes(b"keep")
    with pytest.raises(FileExistsError):
        atomic.atomic_write_bytes(str(target), b"new", overwrite=False)
    assert target.read_bytes() == b"keep"


def test_atomic_write_retries_permission_error(tmp_path, monkeypatch):
    real = os.replace
    attempts = []

    def flaky(src, dst):
        attempts.append(1)
        if len(attempts) < 3:
            raise PermissionError("held by antivirus")
        return real(src, dst)
    monkeypatch.setattr(atomic.os, "replace", flaky)
    atomic.atomic_write_bytes(str(tmp_path / "f"), b"data")
    assert (tmp_path / "f").read_bytes() == b"data" and len(attempts) == 3


# ---------------------------------------------------------------- rollback

def test_failed_save_rolls_back_add(make_vault, monkeypatch):
    vm = make_vault()
    vm.add_entry(cred(entry_id="keep"))
    monkeypatch.setattr("faraday.vault.manager.atomic_write_bytes",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("disk full")))
    with pytest.raises(OSError):
        vm.add_entry(cred(entry_id="new"))
    assert [e.entry_id for e in vm.list_entries()] == ["keep"]


def test_failed_save_rolls_back_delete(make_vault, monkeypatch):
    vm = make_vault()
    vm.add_entry(cred(entry_id="keep"))
    monkeypatch.setattr("faraday.vault.manager.atomic_write_bytes",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("disk full")))
    with pytest.raises(OSError):
        vm.delete_entry("keep")
    assert vm.get_entry("keep") is not None


def test_failed_save_rolls_back_update(make_vault, monkeypatch):
    vm = make_vault()
    vm.add_entry(cred(entry_id="e", password="old"))
    monkeypatch.setattr("faraday.vault.manager.atomic_write_bytes",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("disk full")))
    with pytest.raises(OSError):
        vm.update_entry(cred(entry_id="e", password="new"))
    assert vm.get_entry("e").password == "old"


# ---------------------------------------------------------------- update semantics

def test_update_keeps_id_created_and_unknown_fields(make_vault, reopen):
    vm = make_vault()
    original = cred(entry_id="e1")
    vm.add_entry(original)
    created = vm.get_entry("e1").created
    vm.get_entry("e1")._extra = {"future_field": "keep me"}
    vm.save_vault()
    time.sleep(0.01)
    vm.update_entry(cred(entry_id="e1", password="changed"))
    path = vm.vault_path
    vm.lock_vault()
    vm2 = reopen(path)
    e = vm2.get_entry("e1")
    assert e.password == "changed" and e.created == created and e.modified > created
    assert e._extra == {"future_field": "keep me"}


def test_update_missing_entry_raises(make_vault):
    with pytest.raises(KeyError):
        make_vault().update_entry(cred(entry_id="missing"))


def test_update_cannot_change_type(make_vault):
    vm = make_vault()
    vm.add_entry(cred(entry_id="x"))
    with pytest.raises(ValueError):
        vm.update_entry(WifiEntry("net", "pw", "WPA2", entry_id="x"))


def test_add_with_same_id_keeps_created(make_vault):
    vm = make_vault()
    vm.add_entry(cred(entry_id="x"))
    created = vm.get_entry("x").created
    vm.add_entry(cred(entry_id="x", password="2"))  # legacy edit path
    assert vm.get_entry("x").created == created and len(vm.list_entries()) == 1


# ---------------------------------------------------------------- forward compatibility

def _rewrite_payload(vm, mutate):
    """Write a payload directly (as a newer Faraday would), keeping salt and key."""
    data = open(vm.vault_path, "rb").read()
    vf = fileformat.parse_vault_bytes(data)
    payload = deserialize_vault_data(vm.crypto.decrypt_aes_gcm(vf.nonce, vf.ciphertext, vm.master_key))
    mutate(payload)
    nonce, ct = vm.crypto.encrypt_aes_gcm(serialize_vault_data(payload), vm.master_key)
    atomic.atomic_write_bytes(vm.vault_path, fileformat.build_vault_bytes(vf.salt, vf.kdf_params, nonce, ct))


def test_unknown_types_and_fields_survive_a_save(make_vault, reopen):
    vm = make_vault()
    vm.add_entry(cred(entry_id="c"))
    path = vm.vault_path

    def mutate(payload):
        payload["entries"][0]["passkey"] = {"alg": "ES256"}
        payload["entries"].append({"type": "passkey", "entry_id": "p", "rp": "example.com"})
        payload["entries"].append({"type": "credential", "entry_id": "broken"})  # missing fields
    _rewrite_payload(vm, mutate)
    vm.lock_vault()

    vm2 = reopen(path)
    assert [e.entry_id for e in vm2.list_entries()] == ["c"]  # opaque hidden by default
    opaque = {e.entry_id for e in vm2.list_entries(include_opaque=True) if isinstance(e, OpaqueEntry)}
    assert opaque == {"p", "broken"}
    vm2.update_entry(cred(entry_id="c", password="new"))
    with pytest.raises(ValueError):
        vm2.update_entry(cred(entry_id="p"))

    def check(payload):
        by_id = {e["entry_id"]: e for e in payload["entries"]}
        assert by_id["c"]["passkey"] == {"alg": "ES256"} and by_id["c"]["password"] == "new"
        assert by_id["p"] == {"type": "passkey", "entry_id": "p", "rp": "example.com"}
        assert by_id["broken"] == {"type": "credential", "entry_id": "broken"}
    _rewrite_payload(vm2, check)


# ---------------------------------------------------------------- file lock

def test_second_writer_is_refused(make_vault, fast_kdf):
    vm = make_vault()
    other = VaultManager(vm.vault_path, PASSWORD, auto_lock_seconds=None)
    with pytest.raises(VaultInUseError):
        other.unlock_vault()
    vm.lock_vault()
    other.unlock_vault()  # free once the first one locks
    other.lock_vault()


def test_read_only_can_open_while_locked_by_writer(make_vault):
    vm = make_vault()
    vm.add_entry(cred())
    ro = VaultManager(vm.vault_path, PASSWORD, auto_lock_seconds=None, read_only=True)
    ro.unlock_vault()
    assert len(ro.list_entries()) == 1
    with pytest.raises(VaultReadOnlyError):
        ro.save_vault()
    ro.lock_vault()


def test_failed_unlock_releases_lock(make_vault, fast_kdf):
    vm = make_vault()
    path = vm.vault_path
    vm.lock_vault()
    bad = VaultManager(path, b"wrong", auto_lock_seconds=None)
    with pytest.raises(InvalidTag):
        bad.unlock_vault()
    good = VaultManager(path, PASSWORD, auto_lock_seconds=None)
    good.unlock_vault()
    good.lock_vault()


# ---------------------------------------------------------------- backups

def test_every_save_snapshots_previous_version(make_vault, reopen):
    vm = make_vault()
    vm.add_entry(cred(entry_id="a"))
    vm.add_entry(cred(entry_id="b"))
    backups = vm.backups.list()
    assert len(backups) == 2
    # The newest snapshot is the vault as it was before "b" was added.
    newest = backups[0].path
    restored_count = vm.restore_backup(newest, PASSWORD)
    assert restored_count == 1 and vm.is_locked
    vm2 = reopen(vm.vault_path)
    assert [e.entry_id for e in vm2.list_entries()] == ["a"]
    # The pre-restore state was itself snapshotted.
    assert len(vm2.backups.list()) == 3


def test_restore_with_wrong_password_changes_nothing(make_vault):
    vm = make_vault()
    vm.add_entry(cred())
    before = open(vm.vault_path, "rb").read()
    with pytest.raises(InvalidTag):
        vm.restore_backup(vm.backups.list()[0].path, b"wrong")
    assert open(vm.vault_path, "rb").read() == before and not vm.is_locked


def test_backup_retention(tmp_path):
    from datetime import datetime, timedelta, timezone
    from faraday.vault.backups import BackupStore
    store = BackupStore(str(tmp_path / "v.vault"), keep_recent=3, keep_daily=5)
    now = datetime(2026, 10, 29, 12, tzinfo=timezone.utc)
    for day in reversed(range(10)):  # oldest first, as saves really happen
        for hour in reversed(range(3)):
            store.snapshot_bytes(b"x", now=now - timedelta(days=day, hours=hour))
    kept = store.list()
    days = sorted({b.created.date() for b in kept})
    # 3 newest (all today) + newest per day for the last 5 days
    assert len(kept) == 3 + 4
    assert len(days) == 5


def test_export_full_backup_includes_attachments(make_vault, tmp_path):
    vm = make_vault()
    src = tmp_path / "passport.pdf"
    src.write_bytes(b"%PDF fake")
    vm.add_document(str(src), category="Legal")
    dest = tmp_path / "exports"
    dest.mkdir()
    folder = vm.export_full_backup(str(dest))
    names = sorted(os.listdir(folder))
    assert names == ["test.vault", "test.vault.attachments"]
    assert len(os.listdir(os.path.join(folder, "test.vault.attachments"))) == 1


# ---------------------------------------------------------------- documents

def test_document_add_read_export(make_vault, tmp_path):
    vm = make_vault()
    src = tmp_path / "scan.png"
    src.write_bytes(b"\x89PNG data")
    doc = vm.add_document(str(src), site_note="ID scan")
    assert doc.filename == "scan.png" and doc.mime_type == "image/png"
    assert vm.read_document(doc.entry_id) == b"\x89PNG data"
    out = tmp_path / "out.png"
    vm.export_document(doc.entry_id, str(out))
    assert out.read_bytes() == b"\x89PNG data"


def test_document_add_failure_leaves_no_orphan(make_vault, tmp_path, monkeypatch):
    vm = make_vault()
    src = tmp_path / "a.txt"
    src.write_text("hello")
    monkeypatch.setattr("faraday.vault.manager.atomic_write_bytes",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("disk full")))
    with pytest.raises(OSError):
        vm.add_document(str(src))
    assert os.listdir(vm.vault_path + ".attachments") == []
    assert vm.list_entries() == []


def test_delete_document_keeps_attachment_if_save_fails(make_vault, tmp_path, monkeypatch):
    vm = make_vault()
    src = tmp_path / "a.txt"
    src.write_text("hello")
    doc = vm.add_document(str(src))
    monkeypatch.setattr("faraday.vault.manager.atomic_write_bytes",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("disk full")))
    with pytest.raises(OSError):
        vm.delete_entry(doc.entry_id)
    assert vm.read_document(doc.entry_id) == b"hello"


def test_delete_document_wipes_attachment(make_vault, tmp_path):
    vm = make_vault()
    src = tmp_path / "a.txt"
    src.write_text("hello")
    doc = vm.add_document(str(src))
    assert vm.delete_entry(doc.entry_id)
    assert os.listdir(vm.vault_path + ".attachments") == []


def test_tampered_attachment_is_detected(make_vault, tmp_path):
    from faraday.vault.errors import AttachmentIntegrityError
    vm = make_vault()
    src = tmp_path / "a.txt"
    src.write_text("hello")
    doc = vm.add_document(str(src))
    vm.get_entry(doc.entry_id).file_hash = "0" * 64
    with pytest.raises(AttachmentIntegrityError):
        vm.read_document(doc.entry_id)


# ---------------------------------------------------------------- rekey

def test_rekey_refuses_with_attachments(make_vault, tmp_path):
    vm = make_vault()
    src = tmp_path / "a.txt"
    src.write_text("hello")
    vm.add_document(str(src))
    before = open(vm.vault_path, "rb").read()
    with pytest.raises(AttachmentsPresentError):
        vm.rekey()
    assert open(vm.vault_path, "rb").read() == before


def test_rekey_new_password(make_vault, reopen):
    vm = make_vault()
    vm.add_entry(cred(entry_id="a"))
    vm.rekey(new_password=b"new password")
    vm.add_entry(cred(entry_id="b"))  # saving after rekey still works
    path = vm.vault_path
    vm.lock_vault()
    with pytest.raises(InvalidTag):
        reopen(path)
    assert len(reopen(path, password=b"new password").list_entries()) == 2


# ---------------------------------------------------------------- auto-lock

def test_auto_lock_fires_listener(make_vault):
    vm = make_vault(auto_lock_seconds=0.2)
    fired = threading.Event()
    reasons = []
    vm.add_lock_listener(lambda reason: (reasons.append(reason), fired.set()))
    assert fired.wait(3)
    assert vm.is_locked and reasons == ["auto_timeout"] and vm.master_key is None


def test_auto_lock_off(make_vault):
    vm = make_vault(auto_lock_seconds=None)
    assert vm._auto_lock_thread is None


def test_lock_waits_for_inflight_save(make_vault, monkeypatch):
    """Locking during a save must not let the save write an empty or half-cleared vault."""
    vm = make_vault()
    vm.add_entry(cred(entry_id="a"))
    import faraday.vault.manager as manager_mod
    real = manager_mod.atomic_write_bytes
    started = threading.Event()

    def slow_write(*a, **k):
        started.set()
        time.sleep(0.3)
        return real(*a, **k)
    monkeypatch.setattr(manager_mod, "atomic_write_bytes", slow_write)
    t = threading.Thread(target=lambda: vm.add_entry(cred(entry_id="b")))
    t.start()
    started.wait(2)
    vm.lock_vault()
    t.join(3)
    monkeypatch.setattr(manager_mod, "atomic_write_bytes", real)
    vm2 = VaultManager(vm.vault_path, PASSWORD, auto_lock_seconds=None)
    vm2.unlock_vault()
    assert {e.entry_id for e in vm2.list_entries()} == {"a", "b"}
    vm2.lock_vault()


# ---------------------------------------------------------------- 3.0 compatibility

@pytest.mark.slow
def test_opens_vault_created_by_3_0(tmp_path):
    path = tmp_path / "v1.vault"
    shutil.copyfile(FIXTURES / "v1_sample.vault", path)
    vm = VaultManager(str(path), PASSWORD, auto_lock_seconds=None)
    vm.unlock_vault()
    types = sorted(e.get_entry_type() for e in vm.list_entries())
    assert types == sorted(["credential", "card", "identity", "secure_note", "crypto", "api_key",
                            "wifi", "two_factor", "emergency_contact"])
    assert vm.get_entry("cred-1").password == "s3cret-PW!"
    assert vm.get_entry("2fa-1").backup_codes == ["aaaa-1111", "bbbb-2222"]
    # Saving with the new core keeps the original header parameters.
    before = fileformat.parse_vault_bytes(path.read_bytes())
    vm.update_entry(vm.get_entry("cred-1"))
    after = fileformat.parse_vault_bytes(path.read_bytes())
    assert after.salt == before.salt and after.kdf_params == before.kdf_params
    vm.lock_vault()
