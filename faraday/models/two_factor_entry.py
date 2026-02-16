"""
2FA/Recovery codes entry model.
"""

from datetime import datetime
from typing import Optional, List
from .entry import BaseEntry


class TwoFactorEntry(BaseEntry):
    """Entry for storing 2FA/recovery codes and TOTP secrets."""
    
    sensitivity_level = "critical"
    
    def __init__(self, service_name: str, backup_codes: List[str], totp_secret: Optional[str] = None, entry_id: Optional[str] = None, site_note: Optional[str] = None, created: Optional[datetime] = None, modified: Optional[datetime] = None):
        """Initialize 2FA entry."""
        super().__init__(entry_id, site_note, created, modified)
        self.service_name = service_name
        self.backup_codes = backup_codes if isinstance(backup_codes, list) else []
        self.totp_secret = totp_secret or ""
    
    def to_dict(self) -> dict:
        """Convert entry to dictionary for serialization."""
        return {
            "type": "two_factor",
            "entry_id": self.entry_id,
            "service_name": self.service_name,
            "backup_codes": self.backup_codes,
            "totp_secret": self.totp_secret,
            "site_note": self.site_note,
            "created": self.created.isoformat(),
            "modified": self.modified.isoformat()
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'TwoFactorEntry':
        """Create entry from dictionary."""
        return cls(
            service_name=data["service_name"],
            backup_codes=data.get("backup_codes", []),
            totp_secret=data.get("totp_secret"),
            entry_id=data.get("entry_id"),
            site_note=data.get("site_note"),
            created=datetime.fromisoformat(data["created"]) if "created" in data else None,
            modified=datetime.fromisoformat(data["modified"]) if "modified" in data else None
        )
    
    def get_entry_type(self) -> str:
        """Get the type identifier for this entry."""
        return "two_factor"

