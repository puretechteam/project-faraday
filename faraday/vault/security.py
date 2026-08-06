"""
Security utilities for file operations and permissions.
"""

import os
import sys
from typing import Optional


def secure_delete_file(filepath: str, passes: int = 3) -> bool:
    """Securely delete file with multiple overwrite passes.
    
    Args:
        filepath: Path to file to securely delete
        passes: Number of overwrite passes (default 3)
        
    Returns:
        True if file was deleted, False if file didn't exist
    """
    if not os.path.exists(filepath):
        return False
    try:
        file_size = os.path.getsize(filepath)
        with open(filepath, 'r+b') as f:
            for _ in range(passes):
                f.seek(0)
                f.write(os.urandom(file_size))
                f.flush()
                os.fsync(f.fileno())
        os.remove(filepath)
        return True
    except (OSError, IOError):
        return False


def set_vault_permissions(vault_path: str) -> bool:
    """Set restrictive file permissions on vault file.
    
    Unix: Sets mode to 0o600 (owner read/write only)
    Windows: Attempts to restrict to current user (requires win32security)
    
    Args:
        vault_path: Path to vault file
        
    Returns:
        True if permissions were set successfully
    """
    if not os.path.exists(vault_path):
        return False
    try:
        if sys.platform != 'win32':
            os.chmod(vault_path, 0o600)
            return True
        else:
            try:
                import win32security
                import win32api
                import ntsecuritycon as con
                user, domain, _ = win32security.LookupAccountName("", win32api.GetUserName())
                sd = win32security.GetFileSecurity(vault_path, win32security.DACL_SECURITY_INFORMATION)
                dacl = win32security.ACL()
                dacl.AddAccessAllowedAce(win32security.ACL_REVISION, con.FILE_ALL_ACCESS, user)
                sd.SetSecurityDescriptorDacl(1, dacl, 0)
                win32security.SetFileSecurity(vault_path, win32security.DACL_SECURITY_INFORMATION, sd)
                return True
            except ImportError:
                return False
    except (OSError, IOError):
        return False


def verify_vault_permissions(vault_path: str) -> tuple[bool, Optional[str]]:
    """Verify vault file has restrictive permissions.
    
    Args:
        vault_path: Path to vault file
        
    Returns:
        Tuple of (is_secure, warning_message)
        is_secure: True if permissions are restrictive
        warning_message: Warning message if permissions are too permissive
    """
    if not os.path.exists(vault_path):
        return False, "Vault file does not exist"
    try:
        if sys.platform != 'win32':
            stat_info = os.stat(vault_path)
            mode = stat_info.st_mode
            if (mode & 0o077) != 0:  # Check if group or other have permissions
                return False, f"Vault file has permissive permissions (mode: {oct(mode)}). Should be 0o600."
            return True, None
        else:
            return True, None
    except (OSError, IOError):
        return False, "Could not verify file permissions"


def secure_delete_temp_file(temp_path: str, passes: int = 3) -> bool:
    """Securely delete temporary vault file.
    
    Args:
        temp_path: Path to temporary file
        passes: Number of overwrite passes
        
    Returns:
        True if file was deleted successfully
    """
    return secure_delete_file(temp_path, passes)

