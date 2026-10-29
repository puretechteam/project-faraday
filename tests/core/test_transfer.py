"""TOTP, importers, encrypted archives and bulk import."""

import base64
import json
import os

import pytest
from cryptography.exceptions import InvalidTag

from faraday import totp
from faraday.models.credential_entry import CredentialEntry
from faraday.transfer import archive, importers
from tests.conftest import FAST_KDF, PASSWORD

# ---------------------------------------------------------------- TOTP (RFC 6238 appendix B)

RFC_SECRET_SHA1 = base64.b32encode(b"12345678901234567890").decode()


@pytest.mark.parametrize("at,expected", [(59, "94287082"), (1111111109, "07081804"),
                                         (1234567890, "89005924"), (2000000000, "69279037")])
def test_totp_rfc_vectors(at, expected):
    params = totp.parse(f"otpauth://totp/Test?secret={RFC_SECRET_SHA1}&digits=8")
    assert totp.code(params, at) == expected


def test_totp_sha256_vector():
    secret = base64.b32encode(b"12345678901234567890123456789012").decode()
    params = totp.parse(f"otpauth://totp/x?secret={secret}&digits=8&algorithm=SHA256")
    assert totp.code(params, 59) == "46119246"


def test_totp_plain_secret_and_errors():
    params = totp.parse("jbsw y3dp ehpk 3pxp")  # spaces and lowercase are fine
    assert len(totp.code(params)) == 6 and 1 <= totp.seconds_left(params) <= 30
    assert totp.parse("otpauth://totp/GitHub:alice?secret=JBSWY3DPEHPK3PXP&issuer=GitHub").issuer == "GitHub"
    for bad in ("", "not base32!!", "otpauth://hotp/x?secret=JBSWY3DPEHPK3PXP"):
        assert totp.validation_error(bad)


# ---------------------------------------------------------------- importers

def _write(tmp_path, name, text):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return str(p)


BITWARDEN_JSON = {
    "encrypted": False,
    "items": [
        {"type": 1, "name": "GitHub", "notes": "work", "fields": [{"name": "PIN", "value": "1234"}],
         "login": {"username": "alice", "password": "pw1", "uris": [{"uri": "https://github.com"}],
                   "totp": "JBSWY3DPEHPK3PXP"}},
        {"type": 2, "name": "Wifi note", "notes": "router is in the attic"},
        {"type": 3, "name": "Visa", "card": {"cardholderName": "Alice", "number": "4111111111111111",
                                             "expMonth": "7", "expYear": "29", "code": "321"}},
        {"type": 4, "name": "Me", "identity": {"firstName": "Alice", "lastName": "Example",
                                                "email": "a@example.com", "city": "Springfield", "ssn": "123"}},
        {"type": 5, "name": "Passkey thing"},
    ],
}


def test_bitwarden_json(tmp_path):
    r = importers.load(_write(tmp_path, "bw.json", json.dumps(BITWARDEN_JSON)))
    assert r.counts() == {"credential": 1, "two_factor": 1, "secure_note": 1, "card": 1, "identity": 1}
    cred = next(e for e in r.entries if e.get_entry_type() == "credential")
    assert (cred.site_note, cred.username, cred.url) == ("GitHub", "alice", "https://github.com")
    assert "PIN: 1234" in cred.notes
    card = next(e for e in r.entries if e.get_entry_type() == "card")
    assert card.expiration_year == 2029 and card.cvv == "321"
    assert len(r.skipped) == 1


def test_bitwarden_encrypted_export_is_refused(tmp_path):
    with pytest.raises(ValueError, match="unencrypted"):
        importers.load(_write(tmp_path, "bw.json", json.dumps({"encrypted": True, "items": []})))


def test_bitwarden_csv(tmp_path):
    text = ("folder,favorite,type,name,notes,fields,reprompt,login_uri,login_username,login_password,login_totp\n"
            ",,login,Mail,,,0,https://mail.example.com,alice,pw2,\n"
            ",,note,Secret plan,step one,,0,,,,\n")
    r = importers.load(_write(tmp_path, "bw.csv", text))
    assert r.format == "bitwarden_csv" and r.counts() == {"credential": 1, "secure_note": 1}


def test_keepassxc_csv(tmp_path):
    text = ('"Group","Title","Username","Password","URL","Notes","TOTP"\n'
            '"Root","Bank","bob","pw3","https://bank.example","","otpauth://totp/Bank?secret=JBSWY3DPEHPK3PXP"\n'
            '"Root/Recycle Bin","Old","x","y","","",""\n'
            '"Root","","","","https://www.shop.example","just a note",""\n')
    r = importers.load(_write(tmp_path, "kp.csv", text))
    assert r.counts() == {"credential": 1, "two_factor": 1, "secure_note": 1}
    note = next(e for e in r.entries if e.get_entry_type() == "secure_note")
    assert note.title == "shop.example"


def test_keepass2_csv_headers(tmp_path):
    text = '"Account","Login Name","Password","Web Site","Comments"\n"Forum","al","pw","forum.example","hi"\n'
    r = importers.load(_write(tmp_path, "kp2.csv", text))
    [cred] = r.entries
    assert (cred.site_note, cred.username, cred.notes) == ("Forum", "al", "hi")


def test_keepass_xml(tmp_path):
    def entry(title, user, pw, history=""):
        return (f"<Entry><String><Key>Title</Key><Value>{title}</Value></String>"
                f"<String><Key>UserName</Key><Value>{user}</Value></String>"
                f"<String><Key>Password</Key><Value>{pw}</Value></String>{history}</Entry>")
    xml = ("<KeePassFile><Root><Group><Name>Root</Name>"
           + entry("Mail", "alice", "new", "<History>" + entry("Mail", "alice", "old") + "</History>")
           + "<Group><Name>Recycle Bin</Name>" + entry("Gone", "x", "y") + "</Group>"
           + "<Group><Name>Work</Name>" + entry("VPN", "bob", "vpnpw") + "</Group>"
           + "</Group></Root></KeePassFile>")
    r = importers.load(_write(tmp_path, "kp.xml", xml))
    assert sorted((e.site_note, e.password) for e in r.entries) == [("Mail", "new"), ("VPN", "vpnpw")]


def test_unrecognised_csv(tmp_path):
    with pytest.raises(ValueError):
        importers.load(_write(tmp_path, "x.csv", "a,b\n1,2\n"))


def test_duplicates_are_split(tmp_path, make_vault):
    vm = make_vault()
    r = importers.load(_write(tmp_path, "bw.json", json.dumps(BITWARDEN_JSON)))
    vm.import_entries(r.entries)
    again = importers.load(_write(tmp_path, "bw2.json", json.dumps(BITWARDEN_JSON)))
    importers.split_duplicates(again, vm.list_entries())
    assert again.entries == [] and len(again.duplicates) == 5


# ---------------------------------------------------------------- archives and bulk import

def test_archive_roundtrip_with_documents(make_vault, tmp_path, fast_kdf):
    src = make_vault("src.vault")
    src.add_entry(CredentialEntry("alice", "pw", url="https://x.example", notes="n", entry_id="c1"))
    doc_file = tmp_path / "id.pdf"
    doc_file.write_bytes(b"%PDF scan")
    src.add_document(str(doc_file), category="Legal")
    records, files = src.export_records()
    out = str(tmp_path / "all.faraday")
    archive.write_archive(out, records, files, b"export pw", kdf_params=fast_kdf)
    with pytest.raises(FileExistsError):
        archive.write_archive(out, records, files, b"export pw", kdf_params=fast_kdf)
    with pytest.raises(importers.NeedsPassword):
        importers.load(out)
    with pytest.raises(InvalidTag):
        importers.load(out, b"wrong")

    dest = make_vault("dest.vault")
    dest.add_entry(CredentialEntry("someone", "else", entry_id="c1"))  # id clash gets a new id
    result = importers.load(out, b"export pw")
    assert dest.import_entries(result.entries, result.attachments) == 2
    docs = dest.list_entries("document")
    assert len(docs) == 1 and dest.read_document(docs[0].entry_id) == b"%PDF scan"
    assert len(dest.list_entries("credential")) == 2
    assert any(e.url == "https://x.example" for e in dest.list_entries("credential"))


def test_import_from_plain_vault_includes_attachments(make_vault, tmp_path):
    other = make_vault("other.vault", password=b"other pw")
    f = tmp_path / "a.txt"
    f.write_text("hello")
    other.add_document(str(f))
    other_path = other.vault_path
    other.lock_vault()
    result = importers.load(other_path, b"other pw")
    dest = make_vault("dest.vault")
    dest.import_entries(result.entries, result.attachments)
    [doc] = dest.list_entries("document")
    assert dest.read_document(doc.entry_id) == b"hello"


def test_import_rollback_removes_stored_files(make_vault, tmp_path, monkeypatch):
    src = make_vault("src.vault")
    f = tmp_path / "a.txt"
    f.write_text("hello")
    src.add_document(str(f))
    records, files = src.export_records()
    result_entries = [src._entry_from_dict(r) for r in records]
    dest = make_vault("dest.vault")
    monkeypatch.setattr("faraday.vault.manager.atomic_write_bytes",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("disk full")))
    with pytest.raises(OSError):
        dest.import_entries(result_entries, files)
    assert dest.list_entries() == []
    assert os.listdir(dest.vault_path + ".attachments") == []


def test_credential_without_url_serializes_like_3_0():
    d = CredentialEntry("a", "b", entry_id="x").to_dict()
    assert "url" not in d and "notes" not in d
