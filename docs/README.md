# Faraday

Faraday - Copyright (C) 2026 Tanner Lucier

A secure, offline-first password vault for storing credentials and sensitive records. Built with Python, featuring both command-line and graphical interfaces.

## Overview

Faraday is an offline-first password management solution that prioritizes security and privacy. All encryption and key derivation operations are performed locally with no cloud services, network calls, or telemetry. Your data remains under your control in encrypted vault files that can be backed up and transferred securely.

## Why Faraday?

In an era where password managers are increasingly cloud-based and subscription-driven, Faraday fills a critical gap: **a truly offline, self-contained password vault that you can trust with your most sensitive credentials**.

**The Problem:**
- Cloud-based password managers require internet connectivity and trust in third-party services
- Subscription fees create ongoing costs for essential security tools
- Privacy concerns with cloud storage of encrypted credentials
- Need for a solution that works completely offline
- Desire for full control over your encrypted data

**The Solution:**
Faraday provides a local-first password management system that runs entirely on your machine. Whether you're storing cryptocurrency wallet addresses, banking credentials, or any sensitive information, your data never leaves your device. The encrypted vault file is yours to back up, transfer, and secure as you see fit.

Perfect for:
- **Privacy-conscious users** who want complete data sovereignty
- **Offline-first workflows** where internet connectivity isn't guaranteed
- **Cryptocurrency users** who need secure storage for wallet addresses and recovery phrases
- **Anyone** who wants enterprise-grade security without vendor lock-in

**About This Project:**

This project represents my first experience building a complete application with [Cursor](https://cursor.sh), an AI-powered code editor. After extensive research into modern password vault architecture, cryptographic implementations, and security best practices, I recognized the complexity involved in building a production-ready password management system from scratch. Rather than attempting to implement this solo with my limited experience in cryptographic systems, I chose to leverage Cursor's AI-assisted development capabilities to build a secure, well-architected solution that I could learn from and be proud of.

The result is a fully functional, security-focused password vault that demonstrates proper cryptographic practices, secure file handling, and professional software architecture—all while serving as a valuable learning experience in both security engineering and AI-assisted development. This is a tool I genuinely need, and I believe others need it too: a truly offline password manager that puts you in complete control of your encrypted data.

## Table of Contents

- [Why Faraday?](#why-faraday)
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
- **Advanced Password Generator**: Cryptographically secure generation with customizable character sets and exclusion rules
- **Dual Interface**: Full-featured CLI for automation and GUI for interactive use
- **Recent Vaults Management**: GUI keeps local history of recently opened vaults
- **Action PIN Guard (Optional)**: Add an extra unlock step for sensitive actions
- **Threat Model Panel**: In-app educational tab with local Argon2 timing and metadata-only analysis
- **System Tray Integration**: Optional system tray icon for quick access (configurable)
- **Automatic Locking**: Configurable auto-lock after inactivity period
- **Enterprise-Grade Cryptography**: Argon2id key derivation with configurable security levels and AES-256-GCM authenticated encryption
- **Secure File Operations**: Restrictive file permissions and secure deletion capabilities

## Security Architecture

Faraday implements industry-standard cryptographic primitives:

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

- Windows 10/11 (or Linux/Mac - cross-platform)
- Python 3.7 or later
- pip

### Installation Steps

1. **Clone or download this repository**

2. **Install the package** (creates `faraday` command):
   ```bash
   pip install -e .
   ```

   This installs Faraday and creates a `faraday` command that works from anywhere.

3. **Verify installation**:
   ```bash
   faraday --help
   ```

### Optional: Check Dependencies

Run `dependencies.bat` (Windows) to check what's installed (informational only).

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

**Generate password with custom rules:**
```bash
faraday generate --length 24 --no-symbols --exclude "0O1l"
```

#### List Available Vaults

**List all vault files in the vaults directory:**
```bash
faraday --vaultlist
```

This shows all `.vault` files in the `vaults/` folder with their paths and sizes, making it easy to see what vaults you have available.

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
- **Sections**: Credentials, secure notes, cards, identities, 2FA, Wi-Fi, documents, API keys, emergency contacts, crypto, and threat model
- **Core behavior**: Add/view/delete entries, password generation tools, status bar vault context, auto-lock after inactivity, optional tray access

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

Vault files are encrypted and stored locally. The format is versioned - see [vault_format.md](vault_format.md) for technical details. New versions will not silently modify existing vaults.

**Important**: Always back up your vault file! If you lose it, you lose all your data. The vault file is encrypted, so you can safely back it up to external storage.

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
5. **Keep your system secure**: Faraday cannot protect against compromised systems
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

Copyright (C) 2026 Tanner Lucier

This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the [LICENSE](LICENSE) file for more details.

You should have received a copy of the GNU General Public License along with this program. If not, see <https://www.gnu.org/licenses/>.

## Contributing

Contributions are welcome! This project adheres to strict security and design principles:

- **Offline-First**: No network features, telemetry, or external dependencies
- **Security-First Design**: Cryptographic correctness takes precedence over convenience
- **Development Guidelines**: See `.cursor/rules/` for detailed development standards
- **Comprehensive Testing**: All changes, especially security-related, must be thoroughly tested

## Disclaimer

This software is provided "as-is" without warranty of any kind. Users are responsible for maintaining backups of their vault files and protecting their master passwords. The developers assume no liability for data loss or security incidents.

## Additional Documentation

- [SECURITY.md](SECURITY.md) - Detailed security information and threat model
- [vault_format.md](vault_format.md) - Technical vault file format specification

## Support

For bug reports, feature requests, security issues, or contributions, please use the project's issue tracker or submit a pull request. Security vulnerabilities should be reported privately.

---

**Remember**: Your vault file is encrypted, but if you lose your master password, you cannot recover your data, not even I could. Keep backups and remember your passwords!

