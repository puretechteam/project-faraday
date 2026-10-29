"""
Command-line interface for Project Faraday.
"""

import argparse
import sys
import getpass
import os
import glob
from typing import Optional, List

from .vault.manager import VaultManager, ENTRY_TYPE_REGISTRY
from .vault.backups import BackupStore
from .vault.security import secure_delete_file
from .models.crypto_entry import CryptoEntry
from .models.credential_entry import CredentialEntry
from .generator.password import PasswordGenerator, PassphraseGenerator
from .paths import default_vaults_dir


def get_vaults_directory() -> str:
    """Get the vaults directory path, creating it if it doesn't exist."""
    return str(default_vaults_dir())


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
    """Get vault path from args or default. A bare file name means a vault in the default folder."""
    if not args.vault_path:
        return get_default_vault_path()
    if not os.path.dirname(args.vault_path) and not os.path.exists(args.vault_path):
        return os.path.join(get_vaults_directory(), args.vault_path)
    return args.vault_path


def _with_vault(args, func, read_only=False, password=None):
    """Execute function with unlocked vault, handling errors. The vault is always locked afterwards."""
    vault_path = _get_vault_path(args)
    if password is None:
        password = get_password()
    manager = None
    try:
        manager = VaultManager(vault_path, password, auto_lock_seconds=None, read_only=read_only)
        manager.unlock_vault()
        return func(manager, vault_path)
    except Exception as e:
        print(f"Operation failed: {e}")
        return 1
    finally:
        if manager is not None and not manager.is_locked:
            manager.lock_vault(reason="manual")


def cmd_init(args):
    """Initialize a new vault."""
    vault_path = _get_vault_path(args)
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
        manager = VaultManager(vault_path, password, auto_lock_seconds=None, read_only=True)
        if manager.unlock_vault():
            manager.lock_vault(reason="manual")
            print(f"Password verified; vault opens: {os.path.abspath(vault_path)}")
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
    return _with_vault(args, _list, read_only=True)


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
    return _with_vault(args, _get, read_only=True)


def cmd_generate(args):
    """Generate password."""
    try:
        if args.words:
            generator = PassphraseGenerator(words=args.words)
        else:
            generator = PasswordGenerator(
                length=args.length or 16,
                use_lowercase=not args.no_lowercase,
                use_uppercase=not args.no_uppercase,
                use_digits=not args.no_digits,
                use_symbols=not args.no_symbols,
                exclude_chars=args.exclude or ""
            )
    except ValueError as e:
        print(f"Cannot generate: {e}")
        return 1
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
        name = os.path.basename(vault_path)
        print(f"Secure deletion overwrites '{vault_path}' and cannot be undone.")
        print("Its attachments and backups folders are left in place.")
        if input(f"Type the vault file name ({name}) to confirm: ").strip() != name:
            print("Deletion cancelled by user")
            return 0
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
    """Re-encrypt the vault with a fresh salt and the chosen Argon2 parameters."""
    from .vault.crypto import get_argon2_params
    level = args.security_level or "standard"

    def _upgrade(manager, vault_path):
        manager.rekey(kdf_params=get_argon2_params(level))
        print(f"Vault upgraded successfully with security level: {level}")
        print(f"The previous version was kept in: {manager.backups.directory}")
        return 0
    return _with_vault(args, _upgrade)


def cmd_backup(args):
    """Copy the vault and its attachments into a new, verified folder."""
    def _backup(manager, vault_path):
        folder = manager.export_full_backup(args.dest)
        print(f"Backup written and verified: {folder}")
        return 0
    return _with_vault(args, _backup)


def cmd_list_backups(args):
    """List the automatic snapshots kept for a vault."""
    store = BackupStore(_get_vault_path(args))
    backups = store.list()
    if not backups:
        print(f"No automatic backups found in {store.directory}")
        return 0
    for i, b in enumerate(backups, 1):
        print(f"  {i}. {b.created.astimezone():%Y-%m-%d %H:%M:%S}  {b.size / 1024:.1f} KB  {b.path}")
    return 0


def cmd_restore(args):
    """Replace the vault with one of its automatic snapshots (the current file is snapshotted first)."""
    store = BackupStore(_get_vault_path(args))
    backups = store.list()
    if not 1 <= args.number <= len(backups):
        print("No such backup. Run 'faraday list-backups' to see the numbers.")
        return 1
    chosen = backups[args.number - 1]
    password = get_password()

    def _restore(manager, vault_path):
        count = manager.restore_backup(chosen.path, password)
        print(f"Restored backup from {chosen.created.astimezone():%Y-%m-%d %H:%M:%S} ({count} entries).")
        return 0
    return _with_vault(args, _restore, password=password)


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(description="Project Faraday - Offline Password Vault", prog="faraday")
    parser.add_argument("--vault", dest="vault_path", help="Vault file. A bare name such as work.vault means Documents\\Faraday\\work.vault (default: faraday.vault).")
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
    list_parser.add_argument("--type", choices=sorted(ENTRY_TYPE_REGISTRY), help="Filter by entry type")
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
    gen_parser.add_argument("--words", type=int, help="Generate a passphrase with this many words instead")
    lock_parser = subparsers.add_parser("lock", help="Lock vault")
    lock_parser.set_defaults(func=cmd_lock)
    delete_parser = subparsers.add_parser("delete-vault", help="Delete vault file")
    delete_parser.set_defaults(func=cmd_delete_vault)
    delete_parser.add_argument("--secure", action="store_true", help="Use secure deletion (multiple overwrite passes)")
    upgrade_parser = subparsers.add_parser("upgrade-vault", help="Upgrade vault to use enhanced Argon2 parameters")
    upgrade_parser.set_defaults(func=cmd_upgrade_vault)
    upgrade_parser.add_argument("--security-level", choices=["low", "standard", "high", "maximum"], help="Security level for upgrade (default: standard)")
    backup_parser = subparsers.add_parser("backup", help="Copy the vault and attachments into a new verified folder")
    backup_parser.set_defaults(func=cmd_backup)
    backup_parser.add_argument("dest", help="Folder to create the backup in")
    list_backups_parser = subparsers.add_parser("list-backups", help="List automatic vault snapshots")
    list_backups_parser.set_defaults(func=cmd_list_backups)
    restore_parser = subparsers.add_parser("restore", help="Restore an automatic snapshot (see list-backups)")
    restore_parser.set_defaults(func=cmd_restore)
    restore_parser.add_argument("number", type=int, help="Backup number from list-backups")
    
    args = parser.parse_args()
    if args.vaultlist:
        return cmd_list_vaults(args)
    if not args.command:
        parser.print_help()
        return 1
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
