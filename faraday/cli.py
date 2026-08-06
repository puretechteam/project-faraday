"""
Command-line interface for Project Faraday.
"""

import argparse
import sys
import getpass
import os
import glob
from typing import Optional, List

from .vault.manager import VaultManager
from .vault.security import secure_delete_file
from .vault.crypto import VAULT_FORMAT_VERSION
from .models.crypto_entry import CryptoEntry
from .models.credential_entry import CredentialEntry
from .generator.password import PasswordGenerator


def get_vaults_directory() -> str:
    """Get the vaults directory path, creating it if it doesn't exist."""
    vaults_dir = os.path.join(os.getcwd(), "vaults")
    os.makedirs(vaults_dir, exist_ok=True)
    return vaults_dir


def get_default_vault_path() -> str:
    """Get the default vault path in the vaults directory."""
    return os.path.join(get_vaults_directory(), "faraday.vault")


def get_password(prompt: str = "Master password: ") -> bytes:
    """Get password from user (hidden input)."""
    return getpass.getpass(prompt).encode('utf-8')


def list_vault_files(directory: str = None) -> List[str]:
    """List all vault files in the specified directory."""
    if directory is None:
        directory = get_vaults_directory()
    vault_files = [os.path.abspath(f) for f in glob.glob(os.path.join(directory, "*.vault")) if not f.endswith(".tmp")]
    vault_files.sort()
    return vault_files


def cmd_list_vaults(args):
    """List all vault files in the vaults directory."""
    vaults_dir = get_vaults_directory()
    vault_files = list_vault_files()
    if not vault_files:
        print(f"No vault files found in vaults directory: {os.path.abspath(vaults_dir)}")
        return 0
    print(f"Found {len(vault_files)} vault file(s) in vaults directory:\n")
    for i, vault_path in enumerate(vault_files, 1):
        filename = os.path.basename(vault_path)
        size = os.path.getsize(vault_path) / 1024
        size_str = f"{size:.1f} KB" if size < 1024 else f"{size / 1024:.1f} MB"
        print(f"  {i}. {filename}\n     Path: {vault_path}\n     Size: {size_str}\n")
    return 0


def _get_vault_path(args) -> str:
    """Get vault path from args or default."""
    return args.vault_path or get_default_vault_path()


def _with_vault(args, func):
    """Execute function with unlocked vault, handling errors."""
    vault_path = _get_vault_path(args)
    password = get_password()
    try:
        manager = VaultManager(vault_path, password)
        manager.unlock_vault()
        result = func(manager, vault_path)
        manager.lock_vault()
        return result
    except Exception as e:
        print(f"Operation failed: {e}")
        return 1


def cmd_init(args):
    """Initialize a new vault."""
    vault_path = args.vault_path or get_default_vault_path()
    if os.path.exists(vault_path):
        print(f"Vault file already exists: {vault_path}")
        print("Use a different path or unlock the existing vault.")
        return 1
    password = get_password("Enter master password for new vault: ")
    if password != get_password("Confirm master password: "):
        print("Password mismatch. Vault creation cancelled.")
        return 1
    try:
        VaultManager(vault_path, password).create_vault()
        print(f"Vault created successfully: {os.path.abspath(vault_path)}")
        return 0
    except Exception as e:
        print(f"Vault creation failed: {e}")
        return 1


def cmd_unlock(args):
    """Unlock vault (interactive)."""
    vault_path = _get_vault_path(args)
    password = get_password()
    try:
        manager = VaultManager(vault_path, password)
        if manager.unlock_vault():
            print(f"Vault unlocked: {os.path.abspath(vault_path)}")
            return 0
        print("Unlock operation failed. Please verify your password and vault file.")
        return 1
    except Exception as e:
        print(f"Unlock failed: {e}")
        return 1


def cmd_add_crypto(args):
    """Add crypto address entry."""
    def _add(manager, vault_path):
        entry = CryptoEntry(address=args.address, site_note=args.note or "")
        manager.add_entry(entry)
        print(f"Crypto entry added to vault '{os.path.basename(vault_path)}': {entry.entry_id}")
        return 0
    return _with_vault(args, _add)


def cmd_add_credential(args):
    """Add username/password entry."""
    def _add(manager, vault_path):
        entry = CredentialEntry(username=args.username, password=args.password, site_note=args.note or "")
        manager.add_entry(entry)
        print(f"Credential entry added to vault '{os.path.basename(vault_path)}': {entry.entry_id}")
        return 0
    return _with_vault(args, _add)


def cmd_list(args):
    """List entries."""
    def _list(manager, vault_path):
        entries = manager.list_entries(entry_type=args.type)
        if not entries:
            print(f"No entries found in vault '{os.path.basename(vault_path)}'")
        else:
            print(f"\nFound {len(entries)} entries in vault '{os.path.basename(vault_path)}':\n")
            for entry in entries:
                print(f"ID: {entry.entry_id}\nType: {entry.get_entry_type()}\nNote: {entry.site_note}")
                if isinstance(entry, CryptoEntry):
                    print(f"Address: {entry.address}")
                elif isinstance(entry, CredentialEntry):
                    print(f"Username: {entry.username}")
                print(f"Created: {entry.created}\nModified: {entry.modified}\n" + "-" * 40)
        return 0
    return _with_vault(args, _list)


def cmd_get(args):
    """Get entry by ID."""
    def _get(manager, vault_path):
        entry = manager.get_entry(args.entry_id)
        if not entry:
            print(f"Entry not found: {args.entry_id}")
            return 1
        print(f"\nEntry ID: {entry.entry_id}\nType: {entry.get_entry_type()}\nNote: {entry.site_note}")
        if isinstance(entry, CryptoEntry):
            print(f"Address: {entry.address}")
        elif isinstance(entry, CredentialEntry):
            print(f"Username: {entry.username}\nPassword: {entry.password}")
        print(f"Created: {entry.created}\nModified: {entry.modified}")
        return 0
    return _with_vault(args, _get)


def cmd_generate(args):
    """Generate password."""
    generator = PasswordGenerator(
        length=args.length or 16,
        use_lowercase=not args.no_lowercase,
        use_uppercase=not args.no_uppercase,
        use_digits=not args.no_digits,
        use_symbols=not args.no_symbols,
        exclude_chars=args.exclude or ""
    )
    print(generator.generate())
    return 0


def cmd_lock(args):
    """Lock vault (explicit lock command)."""
    print("Vault is locked (locked after each CLI operation)")
    return 0


def cmd_delete_vault(args):
    """Delete vault file with optional secure deletion."""
    vault_path = _get_vault_path(args)
    if not os.path.exists(vault_path):
        print(f"Vault file not found: {vault_path}")
        return 1
    if args.secure:
        print(f"Securely deleting vault: {vault_path}")
        if secure_delete_file(vault_path, passes=3):
            print("Vault securely deleted (multiple overwrite passes completed)")
            return 0
        else:
            print("Secure deletion failed. File may have been removed or access denied.")
            return 1
    else:
        confirm = input(f"Delete vault file '{vault_path}'? (yes/no): ")
        if confirm.lower() == 'yes':
            try:
                os.remove(vault_path)
                print("Vault file deleted")
                return 0
            except Exception as e:
                print(f"Deletion failed: {e}")
                return 1
        else:
            print("Deletion cancelled by user")
            return 0


def cmd_upgrade_vault(args):
    """Upgrade vault to use enhanced Argon2 parameters."""
    from .vault.crypto import get_argon2_params
    from .vault.storage import create_vault_header, serialize_vault_data
    from .vault.security import set_vault_permissions
    vault_path = _get_vault_path(args)
    password = get_password()
    try:
        manager = VaultManager(vault_path, password)
        manager.unlock_vault()
        entries = manager.list_entries()
        print(f"Upgrading vault with {len(entries)} entries...")
        salt = manager.crypto.generate_salt()
        params = get_argon2_params(args.security_level or "standard")
        manager.master_key = manager.crypto.derive_master_key(salt, time_cost=params["time_cost"], memory_cost=params["memory_cost"], parallelism=params["parallelism"])
        plaintext = serialize_vault_data({"entries": [entry.to_dict() for entry in entries]})
        nonce, ciphertext = manager.crypto.encrypt_aes_gcm(plaintext, manager.master_key)
        header = create_vault_header(VAULT_FORMAT_VERSION, salt, {"time_cost": params["time_cost"], "memory_cost": params["memory_cost"], "parallelism": params["parallelism"]})
        header_bytes = serialize_vault_data(header)
        temp_path = vault_path + ".tmp"
        try:
            with open(temp_path, 'wb') as f:
                f.write(len(header_bytes).to_bytes(4, 'big'))
                f.write(header_bytes)
                f.write(nonce)
                f.write(ciphertext)
            os.replace(temp_path, vault_path)
            set_vault_permissions(vault_path)
            print(f"Vault upgraded successfully with security level: {args.security_level or 'standard'}")
            manager.lock_vault()
            return 0
        except Exception as e:
            if os.path.exists(temp_path):
                secure_delete_file(temp_path)
            raise
    except Exception as e:
        print(f"Vault upgrade failed: {e}")
        return 1


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(description="Project Faraday - Offline Password Vault", prog="faraday")
    parser.add_argument("--vault", dest="vault_path", help="Path to vault file (default: vaults/faraday.vault). You can use multiple vaults by specifying different paths.")
    parser.add_argument("--vaultlist", action="store_true", help="List all vault files in the current directory")
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")
    
    init_parser = subparsers.add_parser("init", help="Create a new vault")
    init_parser.set_defaults(func=cmd_init)
    unlock_parser = subparsers.add_parser("unlock", help="Unlock vault")
    unlock_parser.set_defaults(func=cmd_unlock)
    add_crypto_parser = subparsers.add_parser("add-crypto", help="Add crypto address entry")
    add_crypto_parser.set_defaults(func=cmd_add_crypto)
    add_crypto_parser.add_argument("address", help="Cryptocurrency address")
    add_crypto_parser.add_argument("--note", help="Site/service note")
    add_cred_parser = subparsers.add_parser("add-credential", help="Add username/password entry")
    add_cred_parser.set_defaults(func=cmd_add_credential)
    add_cred_parser.add_argument("username", help="Username")
    add_cred_parser.add_argument("password", help="Password")
    add_cred_parser.add_argument("--note", help="Site/service note")
    list_parser = subparsers.add_parser("list", help="List entries")
    list_parser.set_defaults(func=cmd_list)
    list_parser.add_argument("--type", choices=["crypto", "credential"], help="Filter by entry type")
    get_parser = subparsers.add_parser("get", help="Get entry by ID")
    get_parser.set_defaults(func=cmd_get)
    get_parser.add_argument("entry_id", help="Entry ID")
    gen_parser = subparsers.add_parser("generate", help="Generate password")
    gen_parser.set_defaults(func=cmd_generate)
    gen_parser.add_argument("--length", type=int, help="Password length (default: 16)")
    gen_parser.add_argument("--no-lowercase", action="store_true", help="Exclude lowercase letters")
    gen_parser.add_argument("--no-uppercase", action="store_true", help="Exclude uppercase letters")
    gen_parser.add_argument("--no-digits", action="store_true", help="Exclude digits")
    gen_parser.add_argument("--no-symbols", action="store_true", help="Exclude symbols")
    gen_parser.add_argument("--exclude", help="Characters to exclude")
    lock_parser = subparsers.add_parser("lock", help="Lock vault")
    lock_parser.set_defaults(func=cmd_lock)
    delete_parser = subparsers.add_parser("delete-vault", help="Delete vault file")
    delete_parser.set_defaults(func=cmd_delete_vault)
    delete_parser.add_argument("--secure", action="store_true", help="Use secure deletion (multiple overwrite passes)")
    upgrade_parser = subparsers.add_parser("upgrade-vault", help="Upgrade vault to use enhanced Argon2 parameters")
    upgrade_parser.set_defaults(func=cmd_upgrade_vault)
    upgrade_parser.add_argument("--security-level", choices=["low", "standard", "high", "maximum"], help="Security level for upgrade (default: standard)")
    
    args = parser.parse_args()
    if args.vaultlist:
        return cmd_list_vaults(args)
    if not args.command:
        parser.print_help()
        return 1
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
