"""
Encrypted Faraday archives (``.faraday``): a single file holding every entry
and every document, protected by its own password.

The container is the same version 1 layout as a vault file (Argon2id +
AES-256-GCM, see vault_format.md). The encrypted payload is::

    {"kind": "faraday-export", "exported": <ISO time>, "entries": [...],
     "attachments": {<file_reference>: <plaintext file bytes>}}

so documents travel inside the one file instead of a side folder.
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from ..vault.atomic import atomic_write_bytes
from ..vault.crypto import VaultCrypto, get_argon2_params
from ..vault.fileformat import build_vault_bytes, parse_vault_bytes
from ..vault.storage import deserialize_vault_data, serialize_vault_data

KIND = "faraday-export"
EXTENSION = ".faraday"


def write_archive(path: str, records: List[dict], files: Dict[str, bytes], password: bytes,
                  kdf_params: Optional[dict] = None) -> None:
    """Encrypt ``records`` and ``files`` into a new archive. Never overwrites an existing file."""
    crypto = VaultCrypto(password)
    try:
        params = dict(kdf_params or get_argon2_params("standard"))
        salt = crypto.generate_salt()
        key = crypto.derive_master_key(salt, **params)
        payload = serialize_vault_data({
            "kind": KIND,
            "exported": datetime.now(timezone.utc).isoformat(),
            "entries": records,
            "attachments": files,
        })
        nonce, ciphertext = crypto.encrypt_aes_gcm(payload, key)
        atomic_write_bytes(path, build_vault_bytes(salt, params, nonce, ciphertext), overwrite=False)
    finally:
        crypto.clear_memory()


def read_archive(path: str, password: bytes) -> Tuple[List[dict], Dict[str, bytes]]:
    """Decrypt an archive (or a plain vault file). Raises InvalidTag on a wrong password."""
    with open(path, "rb") as fh:
        vf = parse_vault_bytes(fh.read())
    crypto = VaultCrypto(password)
    try:
        key = crypto.derive_master_key(vf.salt, **vf.kdf_params)
        payload = deserialize_vault_data(crypto.decrypt_aes_gcm(vf.nonce, vf.ciphertext, key))
    finally:
        crypto.clear_memory()
    records = payload.get("entries") or []
    files = payload.get("attachments") or {}
    if not isinstance(records, list) or not isinstance(files, dict):
        raise ValueError("This archive is damaged")
    files = {str(k): bytes(v) for k, v in files.items()}
    if payload.get("kind") != KIND:
        files.update(_vault_side_files(path, key, records))
    return records, files


def _vault_side_files(path: str, key: bytes, records: List[dict]) -> Dict[str, bytes]:
    """For a plain vault file, decrypt the documents kept in its ``.attachments`` folder."""
    import os
    from ..vault.attachments import AttachmentStorage
    directory = path + ".attachments"
    if not os.path.isdir(directory):
        return {}
    storage = AttachmentStorage.__new__(AttachmentStorage)  # read-only: do not create folders
    storage.attachments_dir, storage.master_key = directory, key
    files = {}
    for record in records:
        ref = record.get("file_reference") if isinstance(record, dict) and record.get("type") == "document" else None
        if ref and os.path.exists(os.path.join(directory, f"{ref}.enc")):
            files[ref] = storage.retrieve_file(ref)
    return files
