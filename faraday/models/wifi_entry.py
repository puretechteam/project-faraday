"""
Wi-Fi credentials entry model.
"""

from datetime import datetime
from typing import Optional
from .entry import BaseEntry


class WifiEntry(BaseEntry):
    """Entry for storing Wi-Fi network credentials."""
    
    sensitivity_level = "normal"
    
    def __init__(self, network_name: str, password: str, security_type: str, entry_id: Optional[str] = None, site_note: Optional[str] = None, created: Optional[datetime] = None, modified: Optional[datetime] = None):
        """Initialize Wi-Fi entry."""
        super().__init__(entry_id, site_note, created, modified)
        self.network_name = network_name
        self.password = password
        self.security_type = security_type  # WPA2, WPA3, WEP, None
    
    def to_dict(self) -> dict:
        """Convert entry to dictionary for serialization."""
        return {
            "type": "wifi",
            "entry_id": self.entry_id,
            "network_name": self.network_name,
            "password": self.password,
            "security_type": self.security_type,
            "site_note": self.site_note,
            "created": self.created.isoformat(),
            "modified": self.modified.isoformat()
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'WifiEntry':
        """Create entry from dictionary."""
        return cls(
            network_name=data["network_name"],
            password=data["password"],
            security_type=data.get("security_type", "WPA2"),
            entry_id=data.get("entry_id"),
            site_note=data.get("site_note"),
            created=datetime.fromisoformat(data["created"]) if "created" in data else None,
            modified=datetime.fromisoformat(data["modified"]) if "modified" in data else None
        )
    
    def get_entry_type(self) -> str:
        """Get the type identifier for this entry."""
        return "wifi"

