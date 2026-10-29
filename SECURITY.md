# Security Documentation

Project Faraday - Copyright (C) 2024 Pure Tech

## Threat Model

Project Faraday is designed to protect against:

- **Disk theft**: If someone gains physical or remote access to your vault file, they cannot decrypt it without your master password
- **Offline brute-force attacks**: Enhanced Argon2id parameters make brute-force attacks computationally infeasible (years to decades on modern hardware)
- **Temporary file recovery**: Secure deletion prevents recovery of temporary files created during vault operations
- **Unauthorized file access**: Restrictive file permissions prevent other users from accessing your vault files

## What Project Faraday Does NOT Protect Against

Project Faraday **cannot** protect you from:

- **Compromised operating system**: If your OS is compromised (malware, rootkits, etc.), an attacker may be able to access your vault while it's unlocked
- **Keyloggers**: If keylogging software is installed, your master password may be captured
- **Live-memory attacks**: If an attacker has access to your system's RAM while the vault is unlocked, they may be able to extract decrypted data
- **Social engineering**: If someone tricks you into revealing your master password, the vault provides no protection

## Python Memory Limitations

**Important**: Python does not provide guarantees about secure memory wiping. While Project Faraday attempts to clear sensitive data from memory with multiple overwrite passes, Python's garbage collector and memory management may:

- Keep copies of data in memory longer than expected
- Not immediately overwrite memory when objects are deleted
- Cache strings and other objects in ways that prevent secure erasure
- Create temporary copies during string operations

**Enhanced protections**:
- Multiple overwrite passes (3 passes) for sensitive buffers
- Immediate clearing of encryption keys after use
- Minimized lifetime of secrets in memory

**For maximum security, consider**:
- Using a dedicated, isolated system for vault access
- Locking the vault when not in use
- Using full-disk encryption on your system
- Being cautious about running untrusted code on the same system
- Shutting down the application when not in use (reduces memory exposure window)

## Cryptographic Design

- **Key Derivation**: Argon2id via `argon2-cffi` with configurable security levels
  - **Default (Standard)**: time_cost=5, memory_cost=131072 KB (128 MB), parallelism=4
  - **Low**: time_cost=3, memory_cost=65536 KB (64 MB), parallelism=4
  - **High**: time_cost=10, memory_cost=262144 KB (256 MB), parallelism=4
  - **Maximum**: time_cost=15, memory_cost=524288 KB (512 MB), parallelism=4
- **Encryption**: AES-256-GCM or XChaCha20-Poly1305 via `cryptography` library
- **Authentication**: All encrypted data includes authentication tags to prevent tampering
- **Master Keys**: Master keys are never stored; they are derived from your password each time you unlock the vault

### Security Levels

Project Faraday supports multiple security levels that balance security and performance:

- **Low**: Faster unlock times, suitable for less sensitive data or older hardware
- **Standard** (default): Recommended for most users, provides strong protection against brute-force attacks
- **High**: Enhanced security for sensitive data, slower unlock times
- **Maximum**: Maximum security, significantly slower unlock times but strongest protection

New vaults use the "standard" level by default. Existing vaults with older parameters continue to work (backward compatible). You can upgrade a vault using the `upgrade-vault` command. It re-encrypts the vault with a fresh salt, keeps the previous version as a snapshot, and refuses to run on vaults with document attachments (their keys derive from the master key and are not re-encrypted yet).

## Offline-Only Design

Project Faraday has **no network features**:
- No cloud sync
- No update checks
- No telemetry or analytics
- No remote backup
- No online services

The application functions completely offline. This reduces attack surface but means you are responsible for backing up your vault file.

## Security Enhancements

### File Permissions

Vault files are automatically created with restrictive permissions:
- **Unix/Linux/macOS**: Mode `0o600` (owner read/write only, no group or other access)
- **Windows**: Restricted to current user only (when `pywin32` is available)

The application verifies permissions when unlocking vaults and warns if permissions are too permissive.

### Secure File Deletion

- **Temporary files**: Automatically securely deleted with multiple overwrite passes
- **Vault deletion**: Use `faraday delete-vault --secure` to securely delete vault files
- **Multiple passes**: Secure deletion uses 3 overwrite passes with random data

**Note**: Secure deletion effectiveness depends on storage medium:
- **HDD**: Multiple overwrite passes are effective
- **SSD**: May be less effective due to wear-leveling and TRIM operations
- **Full-disk encryption**: Recommended for maximum protection

### Data Safety

- **Crash-safe saves**: every save writes a temporary file, flushes it to disk, then atomically replaces the vault. A crash or power cut leaves either the old or the new vault, never a half-written one.
- **Automatic snapshots**: before every save, the previous encrypted vault is kept in `<vault>.backups/` (the 10 newest plus one per day for 14 days, configurable). Snapshots are the same ciphertext as the vault and need the master password to open.
- **One writer at a time**: a lock file (`<vault>.lock`) stops two Faraday windows, or a window and the CLI, from writing the same vault. The operating system releases it if Faraday crashes.
- **No silent overwrites**: if the vault file changes on disk after it was opened (for example by a sync tool), Faraday refuses to save over it.
- **Rollback**: if a save fails, the change is undone in memory as well, so what you see matches what is on disk.
- **Forward compatible**: fields and entry types written by a newer Faraday are preserved, never dropped.

### Clipboard and Screen

- Copied secrets are cleared after a configurable delay (default 30 seconds), only if the clipboard still holds them, and when the vault locks.
- On Windows, copied secrets are flagged so they stay out of clipboard history (Win+V), cloud clipboard sync and clipboard monitors.
- Secrets stay masked until revealed, and hide again after a configurable delay.
- Optional: hide the Faraday window from screenshots and screen sharing (Settings > Behaviour).

### Locking

- The GUI locks after a configurable idle time (default 5 minutes), when Windows locks or sleeps, and optionally when minimized.
- Locking closes every dialog, destroys every page holding secrets, and clears the clipboard if it still holds a copied secret.
- An optional action PIN guards revealing, copying, editing, deleting and exporting. After 5 wrong PINs only the master password is accepted until the next unlock. Restoring backups, clearing the access log, changing the PIN, turning auto-lock off and exporting everything always require the master password. The PIN is convenience friction, not strong authentication.

### Import and Export

- Exports from other password managers are plain text. After importing one, Faraday offers to securely delete the file.
- Faraday never writes secrets to an unencrypted file. Its only full export is a `.faraday` archive protected by a password you choose (Argon2id and AES-256-GCM, the same as the vault).

### Enhanced Memory Clearing

- **Multiple overwrite passes**: Sensitive data is overwritten 3 times before clearing
- **Immediate key clearing**: Encryption keys are cleared immediately after use
- **Python limitations**: Note that Python's garbage collector may still keep copies in memory

## Best Practices

1. **Use a strong master password**: Use a long, unique password (20+ characters recommended) that you can remember (or store in a separate secure location)
2. **Choose appropriate security level**: Use "standard" or "high" for sensitive data, "maximum" for highly sensitive data
3. **Back up your vault file**: Automatic snapshots protect against mistakes on this PC; also export a full backup (Backups page or `faraday backup <folder>`) to another drive
4. **Lock the vault when not in use**: The vault auto-locks after a configurable idle time (default 5 minutes) and when Windows locks; Ctrl+L locks immediately
5. **Use full-disk encryption**: Encrypt your entire disk (BitLocker, FileVault, LUKS, etc.) for additional protection
6. **Keep your system secure**: Use antivirus, keep your OS updated, and be cautious about what software you install
7. **Don't share your master password**: Anyone with your master password can decrypt your vault
8. **Upgrade existing vaults**: Use `faraday upgrade-vault` to upgrade older vaults to enhanced security parameters
9. **Secure deletion**: Use `--secure` flag when deleting vaults to prevent file recovery
10. **Physical security**: Keep your computer physically secure, especially when the vault is unlocked

## Security Checklist

Before using Project Faraday in production, ensure:

- [ ] You have a strong master password (20+ characters, unique)
- [ ] Your system has full-disk encryption enabled
- [ ] You've chosen an appropriate security level for your threat model
- [ ] You have secure backups of your vault file
- [ ] Your system is free of malware and keyloggers
- [ ] You understand Python's memory limitations
- [ ] You lock the vault when not in use
- [ ] You've upgraded existing vaults to enhanced parameters (if applicable)

## Physical Theft Protection

If your hard drive is stolen:

**With vault locked** (recommended):
- ✅ Vault file is encrypted with strong Argon2 parameters
- ✅ Master password required to decrypt
- ✅ Brute-force attacks are computationally infeasible (years to decades)
- ✅ Temporary files are securely deleted
- ✅ File permissions restrict access

**With vault unlocked** (not recommended):
- ⚠️ Memory dumps may contain decrypted data
- ⚠️ Python memory limitations mean secrets may persist
- ⚠️ Full-disk encryption provides additional protection

**Best practice**: Always lock your vault before leaving your computer unattended.

## Reporting Security Issues

If you discover a security vulnerability, please report it responsibly. Do not create public issues for security problems.

