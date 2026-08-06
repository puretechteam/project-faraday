# Project Faraday

![version](https://img.shields.io/badge/version-3.0.0-blue)
![license](https://img.shields.io/badge/license-MIT-blue)
![python](https://img.shields.io/badge/python-3.7%20%7C%203.8–3.13-blue)
![platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey)
![encryption](https://img.shields.io/badge/encryption-AES--256--GCM-orange)
![kdf](https://img.shields.io/badge/KDF-Argon2id-informational)
![telemetry](https://img.shields.io/badge/telemetry-none-blueviolet)

Copyright © 2026 Pure Tech

Project Faraday is a secure, offline-first credential and digital-asset vault developed and maintained by Pure Tech. It provides both a command-line interface and a native graphical application for storing passwords, cryptographic keys, and sensitive records with provably strong, locally executed cryptography.

## Overview

Project Faraday is an enterprise-grade secrets-management solution engineered around a single principle: **your data never leaves your machine**. All key derivation and encryption operations are performed locally. There are no cloud services, no network calls, and no telemetry. Vaults are stored as encrypted files that remain entirely under the owner's control and can be backed up or transferred at will.

The product targets individuals and teams who require verifiable data sovereignty without the lock-in, recurring cost, or trust assumptions of hosted password managers.

## Why Project Faraday?

Most mainstream password managers are cloud-centric and subscription-based, which introduces connectivity requirements, third-party trust, and ongoing cost for what is fundamentally a security-critical tool. Project Faraday addresses this gap with a self-contained vault that runs completely offline.

**Problems we solve:**

- Eliminates dependence on cloud infrastructure and third-party trust for credential storage
- Removes recurring subscription cost from essential security tooling
- Avoids privacy exposure inherent in remotely stored encrypted data
- Operates reliably in air-gapped or connectivity-constrained environments
- Returns full ownership and portability of encrypted data to the user

**Our approach:**

Project Faraday delivers a professionally engineered secrets-management system that runs entirely on the local device. Whether storing cryptocurrency wallets, banking credentials, API keys, or personal identity records, data is encrypted at rest and never transmitted. The resulting vault file is portable, backup-friendly, and free of accounts, subscriptions, or external dependencies.

**Ideal for:**

- **Privacy-conscious users** who require complete data sovereignty
- **Offline-first and regulated workflows** where connectivity cannot be assumed
- **Cryptocurrency holders** who need secure storage for wallets and recovery phrases
- **Engineering and security teams** standardizing on vendor-neutral tooling

## About Pure Tech

Pure Tech is a software company focused on privacy-respecting, security-first tooling. Project Faraday is built and supported as a maintained product: it follows a documented cryptographic specification, a versioned vault format, and an established threat model. Development prioritizes cryptographic correctness, secure file handling, and a clean, accessible user experience over convenience-driven shortcuts.

## Table of Contents

- [Why Project Faraday?](#why-project-faraday)
- [Features](#features)
- [Security Architecture](#security-architecture)
  - [Threat Model](#threat-model)
- [Installation](#installation)
  - [Prerequisites](#prerequisites)
  - [Installation Steps](#installation-steps)
- [Usage](#usage)
  - [Command Line Interface (CLI)](#command-line-interface-cli)
  - [Graphical User Interface (GUI)](#graphical-user-interface-gui)
- [Detailed Examples](#detailed-examples)
- [Vault Format](#vault-format)
- [File Locations](#file-locations)
- [Security Best Practices](#security-best-practices)
- [Troubleshooting](#troubleshooting)
- [Development](#development)
- [License](#license)
- [Contributing](#contributing)
- [Version](#version)
- [Disclaimer](#disclaimer)
- [Additional Documentation](#additional-documentation)
- [Support](#support)

## Features

- **Offline-First Architecture**: Complete local operation with zero network dependencies
- **Multi-Vault Support**: Create and manage multiple independent vaults with separate encryption keys
- **Broad Record Support**: Store credentials, notes, cards, identities, 2FA data, Wi-Fi records, documents, API keys, emergency contacts, and crypto addresses
- **Dual Entry Types**: Store cryptocurrency addresses and username/password credentials
- **Action PIN Guard (Optional)**: Add an extra unlock step for sensitive actions
- **Threat Model Panel**: In-app educational tab with local Argon2 timing and metadata-only analysis
- **Advanced Password Generator**: Cryptographically secure generation with customizable character sets and exclusion rules
- **Dual Interface**: Full-featured CLI for automation and GUI for interactive use
- **Recent Vaults Management**: GUI maintains history of recently accessed vaults
- **System Tray Integration**: Optional system tray icon for quick access (configurable)
- **Automatic Locking**: Configurable auto-lock after inactivity period
- **Enterprise-Grade Cryptography**: Argon2id key derivation with configurable security levels and AES-256-GCM authenticated encryption
- **Secure File Operations**: Restrictive file permissions and secure deletion capabilities

## Security Architecture

Project Faraday implements industry-standard cryptographic primitives:

- **Argon2id Key Derivation**: Configurable security levels (standard, high, maximum) with memory-hard parameters
- **AES-256-GCM Encryption**: Authenticated encryption with unique nonces per operation
- **CBOR Serialization**: Binary format prevents accidental plaintext exposure
- **Secure File Permissions**: Restrictive access controls (0o600 on Unix, user-only on Windows)
- **Secure Deletion**: Multi-pass overwrite for temporary files and optional secure vault deletion

### Threat Model

**Protected Against:**

- Physical disk theft and offline attacks
- Brute-force password attacks (computationally infeasible with standard+ security levels)
- Unauthorized file access through restrictive permissions
- Temporary file recovery through secure deletion

**Not Protected Against:**

- Compromised operating systems or malware
- Keyloggers and screen capture software
- Live memory analysis attacks
- Social engineering attacks

**Important**: See [SECURITY.md](SECURITY.md) for comprehensive security documentation, threat model analysis, and best practices.

## Installation

### Prerequisites

- Windows 10/11 (or Linux/macOS — cross-platform)
- Python 3.7 or later
- pip

### Installation Steps

1. **Clone or download this repository**

2. **Install the package** (creates the `faraday` command):

   ```bash
   pip install -e .
   ```

   This installs Project Faraday and exposes a `faraday` command available from any working directory.

3. **Verify installation**:

   ```bash
   faraday --help
   ```

### Optional: Check Dependencies

Run `dependencies.bat` (Windows) to check what is installed (informational only).

## Usage

### Command Line Interface (CLI)

#### Basic Commands

**Create a new vault:**

```bash
faraday init
```

This creates `vaults/faraday.vault` by default.

**Create a vault with a custom name:**

```bash
faraday --vault vaults/my_vault.vault init
```

Or use a relative path from the vaults directory:

```bash
faraday --vault my_vault.vault init
```

**Unlock a vault:**

```bash
faraday unlock
```

**Add a crypto address:**

```bash
faraday add-crypto "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa" --note "Bitcoin main wallet"
```

**Add credentials:**

```bash
faraday add-credential "username" "password" --note "My bank account"
```

**List all entries:**

```bash
faraday list
```

**List only crypto entries:**

```bash
faraday list --type crypto
```

**List only credential entries:**

```bash
faraday list --type credential
```

**Get entry details by ID:**

```bash
faraday get <entry-id>
```

**Generate a password:**

```bash
faraday generate --length 20
```

**Generate a password with custom rules:**

```bash
faraday generate --length 24 --no-symbols --exclude "0O1l"
```

#### List Available Vaults

**List all vault files in the vaults directory:**

```bash
faraday --vaultlist
```

This shows all `.vault` files in the `vaults/` folder with their paths and sizes, making it easy to see what vaults are available.

#### Multiple Vaults

You can create and use multiple vaults by specifying different paths:

```bash
# List available vaults
faraday --vaultlist

# Create work vault (in vaults/ folder)
faraday --vault vaults/work.vault init

# Create personal vault (in vaults/ folder)
faraday --vault vaults/personal.vault init

# Use work vault
faraday --vault vaults/work.vault add-credential user pass --note "Work account"

# Use personal vault
faraday --vault vaults/personal.vault list
```

Each vault is completely independent with its own password and encryption.

### Graphical User Interface (GUI)

**Launch the GUI:**

```bash
faraday gui
```

#### GUI Features

- **Themed in-window menu strip**: `File`, `Security`, `Theme`, and `Help`
- **File actions**: New vault, open vault, backup vault, recent vaults, lock vault, and exit
- **Security actions**: Optional Action PIN setup/change/disable for protected operations
- **Theme controls**: Theme settings and quick presets with local save/load behavior

- **File Menu:**
   - **New Vault...**: Create a new vault file
   - **Open Vault...**: Open an existing vault (automatically locks current vault if one is open)
   - **Recent Vaults**: Quick access to recently opened vaults
   - **Lock Vault**: Lock the current vault
   - **Exit**: Close the application

- **Sections**: Credentials, secure notes, cards, identities, 2FA, Wi-Fi, documents, API keys, emergency contacts, crypto, and Threat Model

- **Features:**
   - Add, view, and delete entries
   - Password generator button in credentials section
   - Status bar shows current vault name
   - Auto-locks after 5 minutes of inactivity
   - System tray icon (optional) for quick access

## Detailed Examples

### Creating and Using Multiple Vaults

```bash
# Create a vault for work (in vaults/ folder)
faraday --vault vaults/work.vault init
# Enter password when prompted

# Create a vault for personal use (in vaults/ folder)
faraday --vault vaults/personal.vault init
# Enter different password when prompted

# Add entries to work vault
faraday --vault vaults/work.vault add-credential workuser workpass --note "Work email"
faraday --vault vaults/work.vault add-crypto "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb" --note "Work crypto wallet"

# Add entries to personal vault
faraday --vault vaults/personal.vault add-credential personaluser personalpass --note "Personal email"
faraday --vault vaults/personal.vault list
```

### Password Generation

```bash
# Generate a 16-character password (default)
faraday generate

# Generate a 32-character password
faraday generate --length 32

# Generate password without symbols
faraday generate --length 20 --no-symbols

# Generate password with only letters and numbers
faraday generate --length 16 --no-symbols

# Generate password excluding confusing characters
faraday generate --length 20 --exclude "0O1lI|"
```

### Working with Entries

```bash
# List all entries
faraday list

# List only crypto addresses
faraday list --type crypto

# List only credentials
faraday list --type credential

# Get full details of a specific entry
faraday get <entry-id-from-list>

# Add entry with note
faraday add-credential "john@example.com" "mypassword123" --note "Email account"
faraday add-crypto "bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh" --note "Bitcoin wallet"
```

## Vault Format

Vault files are encrypted and stored locally. The format is versioned — see [vault_format.md](vault_format.md) for technical details. New versions will not silently modify existing vaults.

**Important**: Always back up your vault file. Loss of the vault file results in total loss of the stored data. Because the file is encrypted, it is safe to back up to external storage.

## File Locations

- **Vault files**: Created in the `vaults/` folder in the project root (or specified path)
- **Recent vaults history**: `.faraday_vault_history.json` (in current directory)
- **Default vault**: `vaults/faraday.vault` (if no `--vault` flag is used)
- **Vaults directory**: Automatically created if it doesn't exist

## Security Best Practices

1. **Use strong master passwords**: Your vault is only as secure as your master password
2. **Back up your vault file**: Store encrypted vault files in multiple safe locations
3. **Lock when not in use**: The GUI auto-locks after 5 minutes, but you can lock manually
4. **Use different vaults**: Separate work and personal data into different vaults
5. **Keep your system secure**: Project Faraday cannot protect against compromised systems
6. **Read SECURITY.md**: Understand the threat model and limitations

## Troubleshooting

### "Vault file already exists" error

If you try to create a vault that already exists:

- Use a different name: `faraday --vault new_name.vault init`
- Or use the existing vault: `faraday unlock`

### "ModuleNotFoundError: No module named 'faraday'"

Make sure you installed the package:

```bash
pip install -e .
```

### GUI won't start

- Make sure tkinter is installed (usually comes with Python)
- On Linux, you may need: `sudo apt-get install python3-tk`

### Can't unlock vault

- Make sure you're using the correct password
- Make sure you're pointing to the correct vault file with `--vault` if needed
- Check that the vault file exists and isn't corrupted

## Development

### Project Structure

```
faraday/
├── __init__.py          # Package initialization
├── __main__.py          # Entry point
├── cli.py               # Command-line interface
├── generator/           # Password generator
│   └── password.py
├── gui/                 # Graphical interface
│   ├── main_window.py
│   ├── crypto_section.py
│   ├── credential_section.py
│   ├── password_generator.py
│   ├── vault_history.py
│   └── ...
├── models/              # Data models
│   ├── entry.py
│   ├── crypto_entry.py
│   └── credential_entry.py
└── vault/               # Vault management
    ├── manager.py
    ├── crypto.py
    └── storage.py
```

### Running from Source

```bash
# Install in development mode
pip install -e .

# Run CLI
python -m faraday list

# Run GUI
python -m faraday gui
```

## License

Copyright © 2026 Pure Tech

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for the full text.

## Contributing

Contributions are welcome. This project adheres to strict security and design principles:

- **Offline-First**: No network features, telemetry, or external dependencies
- **Security-First Design**: Cryptographic correctness takes precedence over convenience
- **Development Guidelines**: See `docs/` for project documentation
- **Comprehensive Testing**: All changes, especially security-related, must be thoroughly tested

## Disclaimer

This software is provided "as-is" without warranty of any kind. Users are responsible for maintaining backups of their vault files and protecting their master passwords. The developers assume no liability for data loss or security incidents.

## Additional Documentation

- [SECURITY.md](SECURITY.md) - Detailed security information and threat model
- [vault_format.md](vault_format.md) - Technical vault file format specification

## Support

For bug reports, feature requests, security issues, or contributions, please use the project's issue tracker or submit a pull request. Security vulnerabilities should be reported privately.

---

**Note**: Your vault is encrypted with AES-256-GCM and Argon2id. If you lose your master password, the data is cryptographically unrecoverable — there is no backdoor by design. Maintain secure backups and safeguard your master password.
