"""
Time-based one-time passwords (RFC 6238), so two-factor entries can show
live codes like an authenticator app. Accepts a bare base32 secret or an
``otpauth://totp/...`` URI.
"""

import base64
import hashlib
import hmac
import struct
import time
from dataclasses import dataclass
from typing import Optional
from urllib.parse import parse_qs, unquote, urlparse

_ALGORITHMS = {"SHA1": hashlib.sha1, "SHA256": hashlib.sha256, "SHA512": hashlib.sha512}


@dataclass(frozen=True)
class TotpParams:
    secret: bytes
    digits: int = 6
    period: int = 30
    algorithm: str = "SHA1"
    issuer: str = ""
    account: str = ""


def _decode_base32(text: str) -> bytes:
    cleaned = "".join(text.split()).replace("-", "").upper().rstrip("=")
    if not cleaned:
        raise ValueError("The authenticator secret is empty")
    try:
        return base64.b32decode(cleaned + "=" * (-len(cleaned) % 8))
    except Exception:
        raise ValueError("The authenticator secret is not valid base32")


def parse(value: str) -> TotpParams:
    """Parse a base32 secret or an otpauth URI. Raises ValueError if unusable."""
    value = (value or "").strip()
    if value.lower().startswith("otpauth://"):
        uri = urlparse(value)
        if uri.netloc.lower() != "totp":
            raise ValueError("Only time-based (TOTP) codes are supported")
        query = {k.lower(): v[0] for k, v in parse_qs(uri.query).items()}
        label = unquote(uri.path.lstrip("/"))
        issuer, _, account = label.partition(":") if ":" in label else ("", "", label)
        digits = int(query.get("digits", 6))
        period = int(query.get("period", 30))
        algorithm = query.get("algorithm", "SHA1").upper()
        if algorithm not in _ALGORITHMS or digits not in (6, 7, 8) or not 1 <= period <= 300:
            raise ValueError("Unsupported authenticator settings")
        return TotpParams(_decode_base32(query.get("secret", "")), digits, period, algorithm,
                          query.get("issuer", issuer), account)
    return TotpParams(_decode_base32(value))


def code(params: TotpParams, at: Optional[float] = None) -> str:
    counter = int((time.time() if at is None else at) // params.period)
    digest = hmac.new(params.secret, struct.pack(">Q", counter), _ALGORITHMS[params.algorithm]).digest()
    offset = digest[-1] & 0x0F
    number = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(number % (10 ** params.digits)).zfill(params.digits)


def seconds_left(params: TotpParams, at: Optional[float] = None) -> int:
    now = time.time() if at is None else at
    return params.period - int(now % params.period)


def is_valid(value: str) -> bool:
    try:
        parse(value)
        return True
    except ValueError:
        return False


def validation_error(value: str) -> Optional[str]:
    try:
        parse(value)
        return None
    except ValueError as exc:
        return str(exc)
