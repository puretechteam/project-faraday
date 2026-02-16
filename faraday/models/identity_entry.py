"""
Identity profile entry model.
"""

from datetime import datetime
from typing import Optional
from .entry import BaseEntry


class IdentityEntry(BaseEntry):
    """Entry for storing identity profile information."""
    
    sensitivity_level = "normal"
    
    def __init__(self, full_name: str, address: str, phone: str, date_of_birth: str, email: str, entry_id: Optional[str] = None, site_note: Optional[str] = None, created: Optional[datetime] = None, modified: Optional[datetime] = None):
        """Initialize identity entry."""
        super().__init__(entry_id, site_note, created, modified)
        self.full_name = full_name
        self.address = address
        self.phone = phone
        self.date_of_birth = date_of_birth
        self.email = email
    
    def to_dict(self) -> dict:
        """Convert entry to dictionary for serialization."""
        return {
            "type": "identity",
            "entry_id": self.entry_id,
            "full_name": self.full_name,
            "address": self.address,
            "phone": self.phone,
            "date_of_birth": self.date_of_birth,
            "email": self.email,
            "site_note": self.site_note,
            "created": self.created.isoformat(),
            "modified": self.modified.isoformat()
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'IdentityEntry':
        """Create entry from dictionary."""
        return cls(
            full_name=data["full_name"],
            address=data["address"],
            phone=data["phone"],
            date_of_birth=data["date_of_birth"],
            email=data["email"],
            entry_id=data.get("entry_id"),
            site_note=data.get("site_note"),
            created=datetime.fromisoformat(data["created"]) if "created" in data else None,
            modified=datetime.fromisoformat(data["modified"]) if "modified" in data else None
        )
    
    def get_entry_type(self) -> str:
        """Get the type identifier for this entry."""
        return "identity"

