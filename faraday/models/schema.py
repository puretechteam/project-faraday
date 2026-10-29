"""
Field schema for every entry type.

The GUI builds its list rows, detail panes and edit forms from these specs
instead of hand-writing one screen per type. Nothing here imports Qt or Tk.

``TypeSpec.build`` turns form values into a model instance. When editing it
keeps the existing entry's id, created time, read-only fields and any fields
this build does not know about, so an edit can never drop data.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

from ..vault import validation
from .api_key_entry import ApiKeyEntry
from .card_entry import CardEntry
from .credential_entry import CredentialEntry
from .crypto_entry import CryptoEntry
from .document_entry import DocumentEntry
from .emergency_contact_entry import EmergencyContactEntry
from .entry import BaseEntry
from .identity_entry import IdentityEntry
from .opaque_entry import OpaqueEntry
from .secure_note_entry import SecureNoteEntry
from .two_factor_entry import TwoFactorEntry
from .wifi_entry import WifiEntry

# Field kinds understood by the editors.
TEXT = "text"
SECRET = "secret"
MULTILINE = "multiline"
SECRET_MULTILINE = "secret_multiline"
EMAIL = "email"
PHONE = "phone"
CHOICE = "choice"
INT = "int"
LINES = "lines"
READONLY = "readonly"

DOCUMENT_CATEGORIES = ("General", "ID / Driver License", "Legal", "Financial", "Medical", "Tax", "Other")
WIFI_SECURITY_TYPES = ("WPA2", "WPA3", "WEP", "None")
API_ENVIRONMENTS = ("prod", "dev", "staging")
MAX_DOCUMENT_BYTES = 100 * 1024 * 1024


def _check(result: Tuple[bool, Optional[str]]) -> Optional[str]:
    ok, message = result
    return None if ok else message


def _int_range(low: int, high: int, label: str) -> Callable[[Any], Optional[str]]:
    def check(value):
        try:
            number = int(str(value).strip())
        except (TypeError, ValueError):
            return f"{label} must be a number"
        if not low <= number <= high:
            return f"{label} must be between {low} and {high}"
        return None
    return check


@dataclass(frozen=True)
class FieldSpec:
    key: str
    label: str
    kind: str = TEXT
    required: bool = False
    searchable: bool = False
    copyable: bool = True
    generator: bool = False
    hidden: bool = False          # stored, never shown (e.g. attachment reference)
    choices: Tuple[str, ...] = ()
    placeholder: str = ""
    validate: Optional[Callable[[Any], Optional[str]]] = None  # blocking error
    warn: Optional[Callable[[Any], Optional[str]]] = None      # non-blocking warning
    display: Optional[Callable[[Any], str]] = None             # masked/compact display

    @property
    def secret(self) -> bool:
        return self.kind in (SECRET, SECRET_MULTILINE)

    @property
    def editable(self) -> bool:
        return self.kind != READONLY and not self.hidden


NOTE = FieldSpec("site_note", "Note", MULTILINE, searchable=True)


@dataclass(frozen=True)
class TypeSpec:
    type_id: str
    label: str
    plural: str
    icon: str
    model: type
    fields: Tuple[FieldSpec, ...]
    title: Callable[[BaseEntry], str]
    subtitle: Callable[[BaseEntry], str]
    primary_secret: Optional[str] = None
    primary_copy: Optional[str] = None   # non-secret quick copy (e.g. username)
    creatable: bool = True               # documents use their own add flow
    description: str = ""

    def field(self, key: str) -> FieldSpec:
        for f in self.fields:
            if f.key == key:
                return f
        raise KeyError(key)

    @property
    def visible_fields(self) -> Tuple[FieldSpec, ...]:
        return tuple(f for f in self.fields if not f.hidden)

    @property
    def editable_fields(self) -> Tuple[FieldSpec, ...]:
        return tuple(f for f in self.fields if f.editable)

    def values(self, entry: BaseEntry) -> Dict[str, Any]:
        """Current field values of ``entry`` in editor form (lists, ints and dates as text)."""
        out = {}
        for f in self.fields:
            out[f.key] = to_text(f, getattr(entry, f.key, None))
        return out

    def validate(self, values: Dict[str, Any]) -> Tuple[Dict[str, str], Dict[str, str]]:
        """Return (errors, warnings) keyed by field."""
        errors, warnings = {}, {}
        for f in self.editable_fields:
            raw = values.get(f.key, "")
            text = raw if isinstance(raw, str) else to_text(f, raw)
            if f.required and not text.strip():
                errors[f.key] = f"{f.label} is required"
                continue
            if not text.strip():
                continue
            if f.validate:
                message = f.validate(text)
                if message:
                    errors[f.key] = message
                    continue
            if f.warn:
                message = f.warn(text)
                if message:
                    warnings[f.key] = message
        return errors, warnings

    def build(self, values: Dict[str, Any], existing: Optional[BaseEntry] = None) -> BaseEntry:
        """Create a model instance from editor values. Raises ValueError on invalid input."""
        errors, _ = self.validate(values)
        if errors:
            raise ValueError("; ".join(errors.values()))
        kwargs: Dict[str, Any] = {}
        for f in self.fields:
            if f.editable:
                kwargs[f.key] = from_text(f, values.get(f.key, ""))
            elif existing is not None:
                kwargs[f.key] = getattr(existing, f.key)
            else:
                raise ValueError(f"{self.label} entries cannot be created from a form")
        if existing is not None:
            if existing.get_entry_type() != self.type_id:
                raise ValueError("An entry cannot change its type")
            kwargs["entry_id"] = existing.entry_id
            kwargs["created"] = existing.created
            kwargs["modified"] = existing.modified
        entry = self.model(**kwargs)
        entry._extra = dict(getattr(existing, "_extra", None) or {})
        return entry


def to_text(f: FieldSpec, value: Any) -> str:
    if value is None:
        return ""
    if f.kind == LINES:
        return "\n".join(str(v) for v in value) if isinstance(value, (list, tuple)) else str(value)
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M")
    return str(value)


def from_text(f: FieldSpec, value: Any) -> Any:
    if f.kind == LINES:
        if isinstance(value, (list, tuple)):
            return [str(v).strip() for v in value if str(v).strip()]
        return [line.strip() for line in str(value or "").splitlines() if line.strip()]
    if f.kind == INT:
        return int(str(value).strip())
    text = "" if value is None else str(value)
    if f.kind in (MULTILINE, SECRET_MULTILINE):
        return text.rstrip()
    return text.strip()


def _last4(value: Any) -> str:
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    return f"ending {digits[-4:]}" if digits else ""


def _shorten(value: str, keep: int = 8) -> str:
    value = value or ""
    return value if len(value) <= keep * 2 + 3 else f"{value[:keep]}...{value[-keep:]}"


def _first_line(value: str) -> str:
    return (value or "").strip().splitlines()[0] if (value or "").strip() else ""


def _size(value: Any) -> str:
    try:
        n = float(value)
    except (TypeError, ValueError):
        return ""
    for unit in ("bytes", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "bytes" else f"{n:.1f} {unit}"
        n /= 1024
    return ""


_email_warn = lambda v: _check(validation.validate_email(v))  # noqa: E731


def _totp_warning(value: str) -> Optional[str]:
    from ..totp import validation_error
    problem = validation_error(value)
    return f"{problem}; live codes will not be shown" if problem else None

TYPES: Tuple[TypeSpec, ...] = (
    TypeSpec(
        "credential", "Login", "Logins", "key-round", CredentialEntry,
        (
            FieldSpec("site_note", "Site or service", searchable=True, placeholder="e.g. github.com"),
            FieldSpec("username", "Username", required=True, searchable=True),
            FieldSpec("password", "Password", SECRET, required=True, generator=True),
            FieldSpec("url", "Website", searchable=True, placeholder="https://"),
            FieldSpec("notes", "Notes", MULTILINE, searchable=True),
        ),
        title=lambda e: e.site_note or e.username,
        subtitle=lambda e: e.username if e.site_note else "",
        primary_secret="password", primary_copy="username",
        description="Usernames and passwords for sites and apps.",
    ),
    TypeSpec(
        "card", "Card", "Cards", "credit-card", CardEntry,
        (
            FieldSpec("cardholder_name", "Cardholder name", required=True, searchable=True),
            FieldSpec("card_number", "Card number", SECRET, required=True, display=_last4,
                      warn=lambda v: _check(validation.validate_card_number(v))),
            FieldSpec("expiration_month", "Expiry month", INT, required=True, placeholder="MM",
                      validate=_int_range(1, 12, "Expiry month")),
            FieldSpec("expiration_year", "Expiry year", INT, required=True, placeholder="YYYY",
                      validate=_int_range(2000, 2100, "Expiry year")),
            FieldSpec("cvv", "CVV", SECRET, required=True, warn=lambda v: _check(validation.validate_cvv(v))),
            FieldSpec("billing_zip", "Billing ZIP", searchable=False),
            NOTE,
        ),
        title=lambda e: e.site_note.splitlines()[0] if e.site_note else f"Card {_last4(e.card_number)}".strip(),
        subtitle=lambda e: f"{e.cardholder_name}  {_last4(e.card_number)}".strip(),
        primary_secret="card_number",
        description="Payment cards with expiry dates and security codes.",
    ),
    TypeSpec(
        "identity", "Identity", "Identities", "id-card", IdentityEntry,
        (
            FieldSpec("full_name", "Full name", required=True, searchable=True),
            FieldSpec("email", "Email", EMAIL, searchable=True, warn=_email_warn),
            FieldSpec("phone", "Phone", PHONE),
            FieldSpec("date_of_birth", "Date of birth", placeholder="YYYY-MM-DD"),
            FieldSpec("address", "Address", MULTILINE),
            FieldSpec("social_security_number", "Social Security number", SECRET),
            NOTE,
        ),
        title=lambda e: e.full_name,
        subtitle=lambda e: e.email,
        primary_secret="social_security_number", primary_copy="email",
        description="Personal details for forms and records.",
    ),
    TypeSpec(
        "secure_note", "Secure note", "Secure notes", "notebook-pen", SecureNoteEntry,
        (
            FieldSpec("title", "Title", searchable=True),
            FieldSpec("content", "Content", SECRET_MULTILINE, required=True),
            NOTE,
        ),
        title=lambda e: e.title or _first_line(e.site_note) or "Untitled note",
        subtitle=lambda e: f"{len(e.content or '')} characters",
        primary_secret="content",
        description="Private text: recovery phrases, PINs, anything else.",
    ),
    TypeSpec(
        "crypto", "Crypto address", "Crypto addresses", "bitcoin", CryptoEntry,
        (
            FieldSpec("address", "Address", required=True, searchable=True),
            NOTE,
        ),
        title=lambda e: _first_line(e.site_note) or _shorten(e.address),
        subtitle=lambda e: _shorten(e.address) if e.site_note else "",
        primary_copy="address",
        description="Wallet addresses you send to or receive from.",
    ),
    TypeSpec(
        "api_key", "API key", "API keys", "code-xml", ApiKeyEntry,
        (
            FieldSpec("service_name", "Service", required=True, searchable=True),
            FieldSpec("environment", "Environment", CHOICE, choices=API_ENVIRONMENTS, searchable=True),
            FieldSpec("api_key", "API key", SECRET, required=True),
            FieldSpec("api_secret", "API secret", SECRET),
            FieldSpec("notes", "Notes", MULTILINE, searchable=True),
            NOTE,
        ),
        title=lambda e: e.service_name,
        subtitle=lambda e: e.environment or "",
        primary_secret="api_key",
        description="Developer keys and secrets.",
    ),
    TypeSpec(
        "document", "Document", "Documents", "file-lock", DocumentEntry,
        (
            FieldSpec("filename", "File name", READONLY, searchable=True),
            FieldSpec("category", "Category", CHOICE, choices=DOCUMENT_CATEGORIES, searchable=True),
            FieldSpec("file_size", "Size", READONLY, copyable=False, display=_size),
            FieldSpec("mime_type", "Type", READONLY, copyable=False),
            FieldSpec("upload_timestamp", "Added", READONLY, copyable=False),
            FieldSpec("file_hash", "SHA-256", READONLY),
            FieldSpec("file_reference", "Attachment", READONLY, hidden=True),
            NOTE,
        ),
        title=lambda e: e.filename,
        subtitle=lambda e: f"{e.category}  {_size(e.file_size)}",
        creatable=False,
        description="Encrypted files: IDs, contracts, scans.",
    ),
    TypeSpec(
        "wifi", "Wi-Fi network", "Wi-Fi", "wifi", WifiEntry,
        (
            FieldSpec("network_name", "Network name (SSID)", required=True, searchable=True),
            FieldSpec("password", "Password", SECRET, generator=True),
            FieldSpec("security_type", "Security", CHOICE, choices=WIFI_SECURITY_TYPES),
            NOTE,
        ),
        title=lambda e: e.network_name,
        subtitle=lambda e: e.security_type or "",
        primary_secret="password", primary_copy="network_name",
        description="Network names and passwords.",
    ),
    TypeSpec(
        "two_factor", "Two-factor", "Two-factor", "shield-check", TwoFactorEntry,
        (
            FieldSpec("service_name", "Service", required=True, searchable=True),
            FieldSpec("totp_secret", "Authenticator secret", SECRET, placeholder="Base32 secret or otpauth:// link",
                      warn=lambda v: _totp_warning(v)),
            FieldSpec("backup_codes", "Backup codes", LINES, placeholder="One code per line"),
            NOTE,
        ),
        title=lambda e: e.service_name,
        subtitle=lambda e: f"{len(e.backup_codes or [])} backup codes",
        primary_secret="totp_secret",
        description="Authenticator secrets and recovery codes.",
    ),
    TypeSpec(
        "emergency_contact", "Emergency contact", "Emergency contacts", "siren", EmergencyContactEntry,
        (
            FieldSpec("contact_name", "Name", required=True, searchable=True),
            FieldSpec("relationship", "Relationship", searchable=True),
            FieldSpec("phone", "Phone", PHONE),
            FieldSpec("email", "Email", EMAIL, warn=_email_warn),
            FieldSpec("address", "Address", MULTILINE),
            FieldSpec("medical_notes", "Medical notes", MULTILINE),
            FieldSpec("instructions", "Instructions", MULTILINE),
            NOTE,
        ),
        title=lambda e: e.contact_name,
        subtitle=lambda e: e.relationship,
        primary_copy="phone",
        description="Who to call, and what they need to know.",
    ),
)

# Backup codes are recovery secrets: hide them like one even though they are a list.
REGISTRY: Dict[str, TypeSpec] = {t.type_id: t for t in TYPES}
SECRET_LIST_FIELDS = {("two_factor", "backup_codes")}


def is_secret(type_id: str, f: FieldSpec) -> bool:
    return f.secret or (type_id, f.key) in SECRET_LIST_FIELDS


def spec_for(entry: BaseEntry) -> Optional[TypeSpec]:
    if isinstance(entry, OpaqueEntry):
        return None
    return REGISTRY.get(entry.get_entry_type())


def entry_title(entry: BaseEntry) -> str:
    spec = spec_for(entry)
    if spec is None:
        return f"Unreadable item ({entry.get_entry_type()})"
    try:
        return spec.title(entry) or spec.label
    except Exception:
        return spec.label


def entry_subtitle(entry: BaseEntry) -> str:
    spec = spec_for(entry)
    if spec is None:
        return getattr(entry, "problem", "") or "Kept unchanged; this version cannot display it"
    try:
        return spec.subtitle(entry) or ""
    except Exception:
        return ""


def entry_matches(entry: BaseEntry, query: str) -> bool:
    """Case-insensitive match of ``query`` against an entry's title and searchable (never secret) fields."""
    needle = (query or "").strip().lower()
    if not needle:
        return True
    haystack: List[str] = [entry_title(entry), entry_subtitle(entry)]
    spec = spec_for(entry)
    if spec is None:
        haystack.append(entry.get_entry_type())
    else:
        haystack.append(spec.label)
        for f in spec.fields:
            if f.searchable and not is_secret(spec.type_id, f):
                haystack.append(to_text(f, getattr(entry, f.key, None)))
    return any(needle in (h or "").lower() for h in haystack)
