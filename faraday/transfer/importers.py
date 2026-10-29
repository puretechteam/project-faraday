"""
Read exports from other password managers into Faraday entries.

Supported:
* Bitwarden: unencrypted ``.json`` and ``.csv`` exports
* KeePass 2: ``.xml`` export and ``.csv`` export
* KeePassXC: ``.csv`` export
* Faraday: ``.faraday`` encrypted archives and other ``.vault`` files (need their password)

Nothing here writes anywhere; ``load`` returns a preview the caller confirms
before anything is added to the vault.
"""

import csv
import io
import json
import os
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional
from urllib.parse import urlparse

from ..models.card_entry import CardEntry
from ..models.credential_entry import CredentialEntry
from ..models.entry import BaseEntry
from ..models.identity_entry import IdentityEntry
from ..models.secure_note_entry import SecureNoteEntry
from ..models.two_factor_entry import TwoFactorEntry

FORMATS = {
    "bitwarden_json": "Bitwarden (.json)",
    "bitwarden_csv": "Bitwarden (.csv)",
    "keepass_xml": "KeePass 2 (.xml)",
    "keepass_csv": "KeePass or KeePassXC (.csv)",
    "faraday": "Faraday archive or vault",
}
FILE_FILTER = ("Supported exports (*.json *.csv *.xml *.faraday *.vault);;"
               "Bitwarden (*.json *.csv);;KeePass (*.xml *.csv);;Faraday (*.faraday *.vault);;All files (*)")


class NeedsPassword(Exception):
    """The file is a Faraday archive or vault; call load() again with its password."""


@dataclass
class ImportResult:
    format: str
    entries: List[BaseEntry] = field(default_factory=list)
    attachments: Dict[str, bytes] = field(default_factory=dict)
    skipped: List[str] = field(default_factory=list)
    duplicates: List[BaseEntry] = field(default_factory=list)

    def counts(self) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for e in self.entries:
            out[e.get_entry_type()] = out.get(e.get_entry_type(), 0) + 1
        return out


# ---------------------------------------------------------------- helpers

def _s(value) -> str:
    return "" if value is None else str(value).strip()


def _host(url: str) -> str:
    try:
        host = urlparse(url if "://" in url else f"https://{url}").hostname or ""
    except ValueError:
        return ""
    return host[4:] if host.startswith("www.") else host


def _login(name: str, username: str, password: str, url: str, notes: str, totp: str,
           result: ImportResult) -> None:
    title = name or _host(url) or username
    if not (username or password):
        if notes or title:
            result.entries.append(SecureNoteEntry(content=notes or "(empty)", title=title or "Imported note"))
        else:
            result.skipped.append("An empty login")
        return
    result.entries.append(CredentialEntry(username=username, password=password, url=url, notes=notes,
                                          site_note=title))
    if totp:
        result.entries.append(TwoFactorEntry(service_name=title or "Imported", backup_codes=[], totp_secret=totp))


def _detect(path: str, head: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    if ext in (".faraday", ".vault"):
        return "faraday"
    if ext == ".json" or head.lstrip().startswith("{"):
        return "bitwarden_json"
    if ext == ".xml" or head.lstrip().startswith("<"):
        return "keepass_xml"
    first_line = head.splitlines()[0].lower() if head else ""
    if "login_username" in first_line or "login_password" in first_line:
        return "bitwarden_csv"
    return "keepass_csv"


# ---------------------------------------------------------------- Bitwarden

def _bitwarden_json(text: str, result: ImportResult) -> None:
    data = json.loads(text)
    if data.get("encrypted"):
        raise ValueError("This is an encrypted Bitwarden export. Export again as unencrypted JSON, "
                         "import it, then delete the export file.")
    for item in data.get("items") or []:
        name, notes, kind = _s(item.get("name")), _s(item.get("notes")), item.get("type")
        extra = [f"{_s(f.get('name'))}: {_s(f.get('value'))}" for f in item.get("fields") or [] if f.get("name")]
        if extra:
            notes = "\n".join(filter(None, [notes, *extra]))
        if kind == 1:
            login = item.get("login") or {}
            uris = login.get("uris") or []
            url = _s(uris[0].get("uri")) if uris else ""
            _login(name, _s(login.get("username")), _s(login.get("password")), url, notes,
                   _s(login.get("totp")), result)
        elif kind == 2:
            result.entries.append(SecureNoteEntry(content=notes or "(empty)", title=name))
        elif kind == 3:
            card = item.get("card") or {}
            number = _s(card.get("number"))
            if not number:
                result.skipped.append(f"Card '{name}' has no number")
                continue
            try:
                month, year = int(_s(card.get("expMonth")) or 1), int(_s(card.get("expYear")) or 2000)
            except ValueError:
                month, year = 1, 2000
            if year < 100:
                year += 2000
            result.entries.append(CardEntry(cardholder_name=_s(card.get("cardholderName")), card_number=number,
                                            expiration_month=month, expiration_year=year, cvv=_s(card.get("code")),
                                            billing_zip="", site_note="\n".join(filter(None, [name, notes]))))
        elif kind == 4:
            ident = item.get("identity") or {}
            full = " ".join(filter(None, (_s(ident.get(k)) for k in ("title", "firstName", "middleName", "lastName"))))
            address = "\n".join(filter(None, [
                _s(ident.get("address1")), _s(ident.get("address2")), _s(ident.get("address3")),
                " ".join(filter(None, (_s(ident.get("city")), _s(ident.get("state")), _s(ident.get("postalCode"))))),
                _s(ident.get("country"))]))
            others = [f"{label}: {_s(ident.get(k))}" for k, label in
                      (("company", "Company"), ("username", "Username"), ("passportNumber", "Passport"),
                       ("licenseNumber", "Licence")) if _s(ident.get(k))]
            result.entries.append(IdentityEntry(
                full_name=full or name, address=address, phone=_s(ident.get("phone")), date_of_birth="",
                email=_s(ident.get("email")), social_security_number=_s(ident.get("ssn")),
                site_note="\n".join(filter(None, [name if full else "", notes, *others]))))
        else:
            result.skipped.append(f"'{name}' has an item type Faraday does not import")


def _bitwarden_csv(text: str, result: ImportResult) -> None:
    for row in csv.DictReader(io.StringIO(text)):
        row = {(_s(k)).lower(): _s(v) for k, v in row.items() if k}
        if row.get("type", "login") == "note":
            result.entries.append(SecureNoteEntry(content=row.get("notes") or "(empty)", title=row.get("name", "")))
            continue
        notes = "\n".join(filter(None, [row.get("notes", ""), row.get("fields", "")]))
        _login(row.get("name", ""), row.get("login_username", ""), row.get("login_password", ""),
               row.get("login_uri", "").split(",")[0], notes, row.get("login_totp", ""), result)


# ---------------------------------------------------------------- KeePass

_KEEPASS_COLUMNS = {
    "title": ("title", "account"),
    "username": ("username", "user name", "login name"),
    "password": ("password",),
    "url": ("url", "web site"),
    "notes": ("notes", "comments"),
    "totp": ("totp", "otp"),
    "group": ("group",),
}


def _keepass_csv(text: str, result: ImportResult) -> None:
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        return
    header = [h.strip().lower() for h in rows[0]]
    index = {}
    for key, names in _KEEPASS_COLUMNS.items():
        for name in names:
            if name in header:
                index[key] = header.index(name)
                break
    if "password" not in index:
        raise ValueError("This CSV file does not look like a KeePass, KeePassXC or Bitwarden export")
    for row in rows[1:]:
        get = lambda k: _s(row[index[k]]) if k in index and index[k] < len(row) else ""  # noqa: E731
        if "recycle bin" in get("group").lower():
            continue
        _login(get("title"), get("username"), get("password"), get("url"), get("notes"), get("totp"), result)


def _keepass_xml(text: str, result: ImportResult) -> None:
    root = ET.fromstring(text)
    top = root.find("Root")
    if top is None:
        raise ValueError("This XML file does not look like a KeePass 2 export")

    def walk(group, in_bin: bool):
        name = _s(group.findtext("Name"))
        in_bin = in_bin or name.lower() == "recycle bin"
        for entry in group.findall("Entry"):  # direct children only; <History> copies are skipped
            if in_bin:
                continue
            values = {}
            for string in entry.findall("String"):
                values[_s(string.findtext("Key")).lower()] = string.findtext("Value") or ""
            totp = values.get("otp") or values.get("totp seed") or ""
            _login(_s(values.get("title")), _s(values.get("username")), values.get("password", ""),
                   _s(values.get("url")), (values.get("notes") or "").strip(), _s(totp), result)
        for child in group.findall("Group"):
            walk(child, in_bin)

    for group in top.findall("Group"):
        walk(group, False)


# ---------------------------------------------------------------- entry point

def load(path: str, password: Optional[bytes] = None) -> ImportResult:
    """Parse ``path``. Raises NeedsPassword for Faraday files opened without one, ValueError for bad files."""
    with open(path, "rb") as fh:
        raw = fh.read()
    head = raw[:4096].decode("utf-8-sig", errors="ignore")
    fmt = _detect(path, head)
    result = ImportResult(format=fmt)
    if fmt == "faraday":
        if password is None:
            raise NeedsPassword()
        from ..vault.manager import VaultManager
        from .archive import read_archive
        records, files = read_archive(path, password)
        parser = VaultManager.__new__(VaultManager)
        for record in records:
            result.entries.append(parser._entry_from_dict(record))
        result.attachments = files
        return result
    text = raw.decode("utf-8-sig", errors="replace")
    {"bitwarden_json": _bitwarden_json, "bitwarden_csv": _bitwarden_csv,
     "keepass_xml": _keepass_xml, "keepass_csv": _keepass_csv}[fmt](text, result)
    return result


def _fingerprint(entry: BaseEntry) -> tuple:
    d = entry.to_dict()
    ignore = {"entry_id", "created", "modified", "upload_timestamp", "file_reference"}
    return tuple(sorted((k, repr(v)) for k, v in d.items() if k not in ignore))


def split_duplicates(result: ImportResult, existing: Iterable[BaseEntry]) -> None:
    """Move entries identical to one already in the vault (or earlier in the file) into ``duplicates``."""
    seen = {_fingerprint(e) for e in existing}
    fresh = []
    for entry in result.entries:
        fp = _fingerprint(entry)
        if fp in seen:
            result.duplicates.append(entry)
        else:
            seen.add(fp)
            fresh.append(entry)
    result.entries = fresh
