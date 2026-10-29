"""Schema, generator, PIN, settings, recents, CLI."""

import inspect
import json
import os

import pytest

from faraday.generator.password import (
    MAX_LENGTH,
    PassphraseGenerator,
    PasswordGenerator,
    estimate_entropy,
    load_wordlist,
    strength_label,
)
from faraday.models.schema import REGISTRY, READONLY, entry_matches, entry_title, is_secret
from faraday.vault.manager import ENTRY_TYPE_REGISTRY

SAMPLE_VALUES = {
    "credential": {"site_note": "example.com", "username": "alice", "password": "pw"},
    "card": {"cardholder_name": "Alice", "card_number": "4111 1111 1111 1111", "expiration_month": "12",
             "expiration_year": "2030", "cvv": "123", "billing_zip": "90210", "site_note": ""},
    "identity": {"full_name": "Alice", "email": "a@example.com", "phone": "1", "date_of_birth": "",
                 "address": "1 Main", "social_security_number": "", "site_note": ""},
    "secure_note": {"title": "T", "content": "body", "site_note": ""},
    "crypto": {"address": "bc1q", "site_note": "wallet"},
    "api_key": {"service_name": "Stripe", "environment": "dev", "api_key": "k", "api_secret": "",
                "notes": "", "site_note": ""},
    "wifi": {"network_name": "Home", "password": "p", "security_type": "WPA2", "site_note": ""},
    "two_factor": {"service_name": "GitHub", "totp_secret": "", "backup_codes": "a\n\nb\n", "site_note": ""},
    "emergency_contact": {"contact_name": "Bob", "relationship": "Brother", "phone": "", "email": "",
                          "address": "", "medical_notes": "", "instructions": "", "site_note": ""},
}


# ---------------------------------------------------------------- schema

def test_schema_covers_every_type_and_constructor_argument():
    assert set(REGISTRY) == set(ENTRY_TYPE_REGISTRY)
    for type_id, spec in REGISTRY.items():
        params = set(inspect.signature(spec.model.__init__).parameters) - {"self", "entry_id", "created", "modified"}
        assert params == {f.key for f in spec.fields}, type_id


@pytest.mark.parametrize("type_id", sorted(SAMPLE_VALUES))
def test_build_roundtrip(type_id, make_vault, reopen):
    spec = REGISTRY[type_id]
    vm = make_vault()
    entry = spec.build(SAMPLE_VALUES[type_id])
    vm.add_entry(entry)
    path = vm.vault_path
    vm.lock_vault()
    loaded = reopen(path).get_entry(entry.entry_id)
    assert loaded.to_dict() == entry.to_dict()
    # values() -> build() is lossless for an edit
    rebuilt = spec.build(spec.values(loaded), existing=loaded)
    assert rebuilt.to_dict() == loaded.to_dict()


def test_lines_and_ints_convert():
    e = REGISTRY["two_factor"].build(SAMPLE_VALUES["two_factor"])
    assert e.backup_codes == ["a", "b"]
    c = REGISTRY["card"].build(SAMPLE_VALUES["card"])
    assert c.expiration_month == 12 and c.expiration_year == 2030


def test_validation_errors_and_warnings():
    spec = REGISTRY["card"]
    bad = dict(SAMPLE_VALUES["card"], expiration_month="13", card_number="1234")
    errors, warnings = spec.validate(bad)
    assert "expiration_month" in errors and "card_number" in warnings
    with pytest.raises(ValueError):
        spec.build(bad)
    errors, _ = REGISTRY["credential"].validate({"username": "", "password": ""})
    assert set(errors) == {"username", "password"}


def test_documents_cannot_be_created_from_a_form():
    with pytest.raises(ValueError):
        REGISTRY["document"].build({"category": "Legal", "site_note": ""})


def test_edit_document_keeps_readonly_fields(make_vault, tmp_path):
    vm = make_vault()
    src = tmp_path / "f.txt"
    src.write_text("x")
    doc = vm.add_document(str(src))
    spec = REGISTRY["document"]
    edited = spec.build(dict(spec.values(doc), category="Tax"), existing=doc)
    vm.update_entry(edited)
    got = vm.get_entry(doc.entry_id)
    assert got.category == "Tax" and got.file_reference == doc.file_reference and got.file_hash == doc.file_hash
    assert all(f.kind == READONLY for f in spec.fields if f.key in ("filename", "file_hash"))


def test_search_never_matches_secrets():
    e = REGISTRY["credential"].build({"site_note": "github.com", "username": "alice", "password": "hunter2"})
    assert entry_matches(e, "GITHUB") and entry_matches(e, "alice")
    assert not entry_matches(e, "hunter2")
    assert entry_title(e) == "github.com"
    assert is_secret("two_factor", REGISTRY["two_factor"].field("backup_codes"))


# ---------------------------------------------------------------- generator

def test_password_contains_every_class_and_length_bounds():
    gen = PasswordGenerator(length=8)
    for _ in range(200):
        pw = gen.generate()
        assert len(pw) == 8
        assert any(c.islower() for c in pw) and any(c.isupper() for c in pw)
        assert any(c.isdigit() for c in pw) and any(not c.isalnum() for c in pw)
    assert len(PasswordGenerator(length=MAX_LENGTH).generate()) == MAX_LENGTH
    for bad in (7, MAX_LENGTH + 1):
        with pytest.raises(ValueError):
            PasswordGenerator(length=bad)


def test_exclusions_and_ambiguous():
    pw = PasswordGenerator(length=64, exclude_ambiguous=True, exclude_chars="!@").generate()
    assert not set(pw) & set("Il1O0o!@")


def test_deterministic_mode_unchanged():
    gen = PasswordGenerator(length=16)
    assert gen.generate(b"seed") == gen.generate(b"seed")


def test_passphrase():
    assert len(load_wordlist()) == 7776
    phrase = PassphraseGenerator(words=4, separator=" ").generate()
    assert len(phrase.split(" ")) == 4 and any(c.isdigit() for c in phrase)
    assert PassphraseGenerator(words=6).entropy_bits > 77
    with pytest.raises(ValueError):
        PassphraseGenerator(words=2)


def test_strength_estimate_orders_sensibly():
    assert estimate_entropy("") == 0
    assert estimate_entropy("aaaaaaaa") < estimate_entropy("Xk7$pQ2!") < estimate_entropy("Xk7$pQ2!Lm9#vR4&")
    assert strength_label(estimate_entropy("password")) == "Weak"
    assert strength_label(PasswordGenerator(length=20).entropy_bits) == "Very strong"


# ---------------------------------------------------------------- pin

def test_pin_set_verify_disable():
    from faraday import pin
    assert not pin.pin_enabled()
    with pytest.raises(ValueError):
        pin.set_pin("12a4")
    pin.set_pin("4821")
    assert pin.pin_enabled() and pin.verify_pin("4821") and not pin.verify_pin("0000")
    pin.disable_pin()
    assert not pin.pin_enabled() and not pin.verify_pin("4821")


def test_pin_reads_3_0_config_format():
    from faraday import pin
    import secrets
    salt = secrets.token_bytes(16)
    legacy = {"enabled": True, "salt_hex": salt.hex(), "hash_hex": pin._hash_pin("1234", salt).hex(),
              "offer_shown": True, "version": 1}
    with open(pin.guard_config_path(), "w", encoding="utf-8") as fh:
        json.dump(legacy, fh)
    assert pin.verify_pin("1234")


# ---------------------------------------------------------------- settings and recents

def test_settings_roundtrip_clamps_and_keeps_unknown():
    from faraday.settings import load_settings, save_settings, settings_path
    s = load_settings()
    assert s.auto_lock_minutes == 5
    s.auto_lock_minutes = 9999
    s.theme_mode = "neon"
    save_settings(s)
    raw = json.loads(settings_path().read_text())
    raw["future_option"] = 1
    settings_path().write_text(json.dumps(raw))
    s2 = load_settings()
    assert s2.auto_lock_minutes == 240 and s2.theme_mode == "system"
    save_settings(s2)
    assert json.loads(settings_path().read_text())["future_option"] == 1


def test_settings_import_legacy_theme():
    from faraday.paths import app_data_dir
    from faraday.settings import load_settings
    (app_data_dir() / "gui_theme.json").write_text(json.dumps({"preset": "forest", "font_scale": 110}))
    s = load_settings()
    assert s.theme_mode == "forest" and s.accent == "" and abs(s.font_scale - 1.1) < 1e-9
    assert (app_data_dir() / "gui_theme.json").exists()  # the 3.0 file is left alone


def test_legacy_theme_restored_over_existing_settings_once():
    """The real upgrade path: settings.json already written with defaults, 3.0 theme file present."""
    from faraday.paths import app_data_dir
    from faraday.settings import load_settings, save_settings, settings_path
    settings_path().write_text(json.dumps({"theme_mode": "dark", "accent": "#4F7CFF", "font_scale": 1.0}))
    spiral = {"bg": "#000000", "bg_elev": "#0a150a", "border": "#1e4a24", "text": "#e6ffe6",
              "muted": "#6b9c73", "accent": "#9fd12a", "danger": "#ff5c4a"}
    (app_data_dir() / "gui_theme.json").write_text(json.dumps({"preset": "spiral", "colors": spiral, "font_scale": 90}))
    s = load_settings()
    assert (s.theme_mode, s.accent, s.theme_colors, s.font_scale) == ("spiral", "", {}, 0.9)
    assert json.loads(settings_path().read_text())["themes_restored"] is True
    s.theme_mode = "paper"  # a later choice is never overwritten by the migration again
    save_settings(s)
    assert load_settings().theme_mode == "paper"


def test_legacy_custom_colours_kept_as_overrides():
    from faraday import themes
    theme_id, overrides = themes.from_legacy("dark", {"bg": "#101010", "accent": "#3b82f6"})
    assert theme_id == "classic-dark" and overrides == {"bg": "#101010"}


def test_every_theme_is_complete():
    from faraday import themes
    assert len(themes.THEMES) == 13 and themes.THEME_IDS[0] == "system"
    for theme_id, (name, colors) in themes.THEMES.items():
        assert name and set(themes.COLOR_KEYS) <= set(colors), theme_id


def test_recent_imports_legacy_file_and_dedupes(tmp_path):
    from faraday import recent
    a = tmp_path / "a.vault"
    b = tmp_path / "b.vault"
    a.write_bytes(b"x")
    b.write_bytes(b"x")
    (tmp_path / ".faraday_vault_history.json").write_text(json.dumps({"recent_vaults": [str(a), str(tmp_path / "gone.vault")]}))
    assert recent.load_recent() == [str(a)]
    recent.add_recent(str(b))
    recent.add_recent(str(a))
    assert recent.load_recent() == [str(a), str(b)]
    recent.remove_recent(str(a))
    assert recent.load_recent() == [str(b)]


# ---------------------------------------------------------------- CLI

def _cli(monkeypatch, argv, password=b"correct horse battery staple", inputs=()):
    import sys
    from faraday import cli
    monkeypatch.setattr(sys, "argv", ["faraday"] + argv)
    monkeypatch.setattr(cli, "get_password", lambda prompt="": password)
    answers = iter(inputs)
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    return cli.main()


def test_cli_flow(make_vault, monkeypatch, capsys, tmp_path):
    vm = make_vault("cli.vault")
    path = vm.vault_path
    vm.lock_vault()
    assert _cli(monkeypatch, ["--vault", path, "add-credential", "bob", "pw", "--note", "site"]) == 0
    assert _cli(monkeypatch, ["--vault", path, "list", "--type", "credential"]) == 0
    assert "bob" in capsys.readouterr().out
    assert _cli(monkeypatch, ["--vault", path, "list-backups"]) == 0
    assert "1." in capsys.readouterr().out
    dest = tmp_path / "bk"
    dest.mkdir()
    assert _cli(monkeypatch, ["--vault", path, "backup", str(dest)]) == 0
    assert len(os.listdir(dest)) == 1
    assert _cli(monkeypatch, ["--vault", path, "restore", "1"]) == 0
    assert _cli(monkeypatch, ["generate", "--words", "5"]) == 0
    assert _cli(monkeypatch, ["generate", "--length", "4"]) == 1


def test_cli_secure_delete_needs_typed_name(make_vault, monkeypatch):
    vm = make_vault("del.vault")
    path = vm.vault_path
    vm.lock_vault()
    assert _cli(monkeypatch, ["--vault", path, "delete-vault", "--secure"], inputs=["yes"]) == 0
    assert os.path.exists(path)
    assert _cli(monkeypatch, ["--vault", path, "delete-vault", "--secure"], inputs=["del.vault"]) == 0
    assert not os.path.exists(path)


def test_cli_refused_while_vault_open(make_vault, monkeypatch, capsys):
    vm = make_vault("busy.vault")
    assert _cli(monkeypatch, ["--vault", vm.vault_path, "add-credential", "x", "y"]) == 1
    assert "another Faraday" in capsys.readouterr().out


def test_cli_bare_vault_name_lives_in_default_folder(fast_kdf, monkeypatch, tmp_path):
    import faraday.vault.crypto as crypto
    monkeypatch.setattr("faraday.vault.manager.DEFAULT_KDF_PARAMS", dict(fast_kdf))
    assert _cli(monkeypatch, ["--vault", "work.vault", "init"]) == 0
    assert (tmp_path / "vaults" / "work.vault").is_file()
    assert crypto  # tiny KDF allowed by fast_kdf
