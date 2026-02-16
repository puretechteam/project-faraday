# Vault File Format Specification

###### Project Faraday - Copyright (C) 2026 Tanner Lucier


Project Faraday stores all encrypted data in a single vault file. The vault file format is versioned to allow for future format changes while maintaining compatibility.

## File Structure

The vault file consists of:

1. **Header Length** (4 bytes, big-endian): Length of the header section
2. **Header** (CBOR-encoded): Non-sensitive metadata
3. **Nonce** (12 bytes for AES-GCM): Unique nonce for this encryption
4. **Ciphertext** (variable length): Encrypted vault data with authentication tag

## Header Format

The header is CBOR-encoded and contains only non-sensitive metadata:

```python
{
    "version": int,           # Vault format version (currently 1)
    "salt": str,              # Hex-encoded salt for key derivation (16 bytes)
    "kdf": "argon2id",        # Key derivation function identifier
    "kdf_params": {
        "time_cost": int,     # Argon2 time cost parameter
        "memory_cost": int,   # Argon2 memory cost parameter (in KB)
        "parallelism": int    # Argon2 parallelism parameter
    }
}
```

**Important**: The header contains NO sensitive data. It is stored in plaintext (CBOR format) and can be read without the master password.

## Encrypted Payload Format

The encrypted payload (after decryption) is CBOR-encoded and contains:

```python
{
    "entries": [
        {
            "type": str,              # Entry type: "crypto", "credential", "secure_note", "card", "identity", "two_factor", "wifi", "document", "api_key", "emergency_contact"
            "entry_id": str,          # UUID string
            "site_note": str,         # User note
            "created": str,           # ISO format timestamp
            "modified": str,          # ISO format timestamp
            # ... type-specific fields (see below)
        },
        ...
    ]
}
```

### Crypto Entry Format

```python
{
    "type": "crypto",
    "entry_id": str,
    "address": str,           # Cryptocurrency address
    "site_note": str,
    "created": str,
    "modified": str
}
```

### Credential Entry Format

```python
{
    "type": "credential",
    "entry_id": str,
    "username": str,          # Username/login identifier
    "password": str,          # Password
    "site_note": str,
    "created": str,
    "modified": str
}
```

### Secure Note Entry Format

```python
{
    "type": "secure_note",
    "entry_id": str,
    "title": str,             # Optional title
    "content": str,           # Multiline text content
    "site_note": str,
    "created": str,
    "modified": str
}
```

### Card Entry Format

```python
{
    "type": "card",
    "entry_id": str,
    "cardholder_name": str,
    "card_number": str,       # Full card number (encrypted)
    "expiration_month": int,  # 1-12
    "expiration_year": int,
    "cvv": str,               # Card verification value (encrypted)
    "billing_zip": str,
    "site_note": str,
    "created": str,
    "modified": str
}
```

### Identity Entry Format

```python
{
    "type": "identity",
    "entry_id": str,
    "full_name": str,
    "address": str,
    "phone": str,
    "date_of_birth": str,
    "email": str,
    "site_note": str,
    "created": str,
    "modified": str
}
```

### Two Factor Entry Format

```python
{
    "type": "two_factor",
    "entry_id": str,
    "service_name": str,
    "backup_codes": [str],    # List of backup/recovery codes
    "totp_secret": str,       # Optional TOTP secret (encrypted)
    "site_note": str,
    "created": str,
    "modified": str
}
```

### Wi-Fi Entry Format

```python
{
    "type": "wifi",
    "entry_id": str,
    "network_name": str,      # SSID
    "password": str,          # Network password (encrypted)
    "security_type": str,     # "WPA2", "WPA3", "WEP", or "None"
    "site_note": str,
    "created": str,
    "modified": str
}
```

### Document Entry Format

```python
{
    "type": "document",
    "entry_id": str,
    "filename": str,          # Original filename
    "mime_type": str,         # MIME type (e.g., "application/pdf")
    "file_reference": str,    # UUID reference to encrypted file
    "file_size": int,         # File size in bytes
    "file_hash": str,         # SHA-256 hash (hex-encoded)
    "upload_timestamp": str,  # ISO format timestamp
    "site_note": str,
    "created": str,
    "modified": str
}
```

**Note**: The actual encrypted file is stored separately in `{vault_path}.attachments/{file_reference}.enc`. Files are encrypted individually using HKDF-derived keys (master key + file UUID as info parameter).

### API Key Entry Format

```python
{
    "type": "api_key",
    "entry_id": str,
    "service_name": str,
    "api_key": str,           # API key (encrypted)
    "api_secret": str,        # Optional API secret (encrypted)
    "environment": str,       # "prod", "dev", or "staging"
    "notes": str,
    "site_note": str,
    "created": str,
    "modified": str
}
```

### Emergency Contact Entry Format

```python
{
    "type": "emergency_contact",
    "entry_id": str,
    "contact_name": str,
    "relationship": str,
    "phone": str,
    "email": str,
    "address": str,
    "medical_notes": str,     # Optional medical notes
    "instructions": str,      # Optional instructions
    "site_note": str,
    "created": str,
    "modified": str
}
```

## Attachment Storage Format

Document attachments are stored separately from the vault file in a directory named `{vault_path}.attachments/`. Each encrypted file is named `{uuid}.enc`.

### File Encryption

Each attachment file is encrypted using:
- **Key Derivation**: HKDF-SHA-256
  - Input: Vault master key
  - Info parameter: `faraday_attachment_{uuid}` (where uuid is the file reference UUID)
  - Output: 32-byte derived key
- **Encryption**: AES-256-GCM
- **Nonce**: 12-byte random nonce per file (stored at the beginning of the encrypted file)
- **File format**: `[nonce (12 bytes)][ciphertext (variable length)]`

### File Metadata

Metadata for document entries is stored in the vault entry itself:
- `file_hash`: SHA-256 hash of the original plaintext file (for integrity verification)
- `filename`: Original filename (preserved for user reference)
- `mime_type`: MIME type of the file
- `file_size`: Size of the original file in bytes
- `upload_timestamp`: When the file was uploaded

This design allows:
- File integrity verification (hash comparison)
- Separate file storage (avoids vault bloat)
- Individual file encryption (key isolation)
- Backup-friendly structure (attachments directory can be backed up separately)

## Version Compatibility

- **Future versions**: Will maintain backward compatibility through explicit migration logic
- **No silent modifications**: New versions will not silently modify existing vaults. Migration must be explicit and user-confirmed.

## Encryption Details

- **Algorithm**: AES-256-GCM (default) or XChaCha20-Poly1305
- **Key Derivation**: Argon2id with parameters from header
- **Nonce**: Unique random nonce per encryption (never reused)
- **Authentication**: GCM/Poly1305 authentication tag included in ciphertext

## Serialization

- **Header**: CBOR-encoded
- **Payload**: CBOR-encoded (after decryption)
- **No JSON, YAML, or pickle**: These formats are not used for secret storage

## Safe Failure Rules

If decryption or authentication fails:
- Abort immediately
- Do not attempt partial reads
- Do not attempt "repair" operations
- Report error to user

This ensures that corrupted or tampered vaults are not partially decrypted, which could lead to data loss or security issues.

