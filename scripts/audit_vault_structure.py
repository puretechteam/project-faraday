"""Offline structural check of a .vault file (no password). Run from repo root: python scripts/audit_vault_structure.py [path]"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from faraday.vault.storage import parse_vault_header
from faraday.vault.crypto import VAULT_FORMAT_VERSION, ARGON2_SALT_LENGTH


def audit(path: str) -> None:
    size = os.path.getsize(path)
    issues = []
    ok = []

    with open(path, "rb") as f:
        raw = f.read()

    pos = 0
    hlb = raw[pos : pos + 4]
    if len(hlb) != 4:
        issues.append("File too small: cannot read 4-byte header length")
        hl = 0
    else:
        pos += 4
        hl = int.from_bytes(hlb, "big")
        ok.append(f"Header length field: {hl} bytes")
        hb = raw[pos : pos + hl]
        if len(hb) != hl:
            issues.append(f"TRUNCATED: expected {hl} header bytes, got {len(hb)}")
            header = None
        else:
            pos += hl
            try:
                header = parse_vault_header(hb)
            except Exception as e:
                issues.append(f"Header CBOR parse failed: {e}")
                header = None
            if header:
                ver = header.get("version")
                if ver != VAULT_FORMAT_VERSION:
                    issues.append(f"Wrong version: {ver}")
                else:
                    ok.append(f"Format version: {ver}")
                salt = header.get("salt")
                if not isinstance(salt, (bytes, bytearray)) or len(salt) != ARGON2_SALT_LENGTH:
                    slen = len(salt) if isinstance(salt, (bytes, bytearray)) else "n/a"
                    issues.append(f"Salt missing or wrong length (got {slen})")
                else:
                    ok.append(f"Salt: {len(salt)} bytes")
                kdf = header.get("kdf_params") or {}
                ok.append(f"KDF params: {kdf}")

            nonce = raw[pos : pos + 12]
            if len(nonce) != 12:
                issues.append(f"TRUNCATED or missing nonce: got {len(nonce)} bytes, need 12")
            else:
                pos += 12
                ok.append("Nonce: 12 bytes (AES-GCM)")
            ct = raw[pos:]
            ok.append(f"Ciphertext length: {len(ct)} bytes")
            if len(ct) < 17:
                issues.append("Ciphertext too short for AES-GCM (need payload + 16-byte tag)")
            expected_size = 4 + hl + 12 + len(ct)
            if expected_size != size:
                issues.append(f"Size mismatch: file on disk {size}, envelope sum {expected_size}")

    print("=== Vault structure audit:", os.path.abspath(path), "===")
    print("File size on disk:", size, "bytes")
    for line in ok:
        print("OK  ", line)
    if issues:
        print("PROBLEMS:")
        for line in issues:
            print(" !! ", line)
    else:
        print(
            "SUMMARY: Outer structure matches a complete Faraday v1 vault (header + nonce + ciphertext)."
        )
        print(
            "This does NOT prove your password works; wrong password and corrupted data both fail the same way at decrypt."
        )

    d = os.path.dirname(os.path.abspath(path))
    print("--- Other files in folder ---")
    for name in sorted(os.listdir(d)):
        p = os.path.join(d, name)
        if os.path.isfile(p) and (name.endswith(".vault") or "tmp" in name.lower()):
            print(f"  {name}  {os.path.getsize(p)} bytes")


if __name__ == "__main__":
    p = sys.argv[1] if len(sys.argv) > 1 else os.path.join("vaults", "Main.vault")
    if not os.path.isfile(p):
        print("Not found:", p)
        sys.exit(1)
    audit(p)
