"""
Username/password credential entry model.
"""

from datetime import datetime
from typing import Optional
from .entry import BaseEntry


class CredentialEntry(BaseEntry):
    """Entry for storing username/password credentials."""
    
    sensitivity_level = "sensitive"
    
    def __init__(self, username: str, password: str, entry_id: Optional[str] = None, site_note: Optional[str] = None, created: Optional[datetime] = None, modified: Optional[datetime] = None):
        """Initialize credential entry."""
        super().__init__(entry_id, site_note, created, modified)
        self.username = username
        self.password = password
    
    def to_dict(self) -> dict:
        """Convert entry to dictionary for serialization."""
        return {
            "type": "credential",
            "entry_id": self.entry_id,
            "username": self.username,
            "password": self.password,
            "site_note": self.site_note,
            "created": self.created.isoformat(),
            "modified": self.modified.isoformat()
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'CredentialEntry':
        """Create entry from dictionary."""
        return cls(
            username=data["username"],
            password=data["password"],
            entry_id=data.get("entry_id"),
            site_note=data.get("site_note"),
            created=datetime.fromisoformat(data["created"]) if "created" in data else None,
            modified=datetime.fromisoformat(data["modified"]) if "modified" in data else None
        )
    
    def get_entry_type(self) -> str:
        """Get the type identifier for this entry."""
        return "credential"
