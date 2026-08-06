"""
Crypto address entry model.
"""

from datetime import datetime
from typing import Optional
from .entry import BaseEntry


class CryptoEntry(BaseEntry):
    """Entry for storing cryptocurrency addresses."""
    
    sensitivity_level = "normal"
    
    def __init__(self, address: str, entry_id: Optional[str] = None, site_note: Optional[str] = None, created: Optional[datetime] = None, modified: Optional[datetime] = None):
        """Initialize crypto address entry."""
        super().__init__(entry_id, site_note, created, modified)
        self.address = address
    
    def to_dict(self) -> dict:
        """Convert entry to dictionary for serialization."""
        return {
            "type": "crypto",
            "entry_id": self.entry_id,
            "address": self.address,
            "site_note": self.site_note,
            "created": self.created.isoformat(),
            "modified": self.modified.isoformat()
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'CryptoEntry':
        """Create entry from dictionary."""
        return cls(
            address=data["address"],
            entry_id=data.get("entry_id"),
            site_note=data.get("site_note"),
            created=datetime.fromisoformat(data["created"]) if "created" in data else None,
            modified=datetime.fromisoformat(data["modified"]) if "modified" in data else None
        )
    
    def get_entry_type(self) -> str:
        """Get the type identifier for this entry."""
        return "crypto"
