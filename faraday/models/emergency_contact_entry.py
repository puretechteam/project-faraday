"""
Emergency/trusted contact entry model.
"""

from datetime import datetime
from typing import Optional
from .entry import BaseEntry


class EmergencyContactEntry(BaseEntry):
    """Entry for storing emergency contact and trusted contact information."""
    
    sensitivity_level = "normal"
    
    def __init__(self, contact_name: str, relationship: str, phone: str, email: str, address: str, medical_notes: Optional[str] = None, instructions: Optional[str] = None, entry_id: Optional[str] = None, site_note: Optional[str] = None, created: Optional[datetime] = None, modified: Optional[datetime] = None):
        """Initialize emergency contact entry."""
        super().__init__(entry_id, site_note, created, modified)
        self.contact_name = contact_name
        self.relationship = relationship
        self.phone = phone
        self.email = email
        self.address = address
        self.medical_notes = medical_notes or ""
        self.instructions = instructions or ""
    
    def to_dict(self) -> dict:
        """Convert entry to dictionary for serialization."""
        return {
            "type": "emergency_contact",
            "entry_id": self.entry_id,
            "contact_name": self.contact_name,
            "relationship": self.relationship,
            "phone": self.phone,
            "email": self.email,
            "address": self.address,
            "medical_notes": self.medical_notes,
            "instructions": self.instructions,
            "site_note": self.site_note,
            "created": self.created.isoformat(),
            "modified": self.modified.isoformat()
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'EmergencyContactEntry':
        """Create entry from dictionary."""
        return cls(
            contact_name=data["contact_name"],
            relationship=data["relationship"],
            phone=data["phone"],
            email=data["email"],
            address=data["address"],
            medical_notes=data.get("medical_notes"),
            instructions=data.get("instructions"),
            entry_id=data.get("entry_id"),
            site_note=data.get("site_note"),
            created=datetime.fromisoformat(data["created"]) if "created" in data else None,
            modified=datetime.fromisoformat(data["modified"]) if "modified" in data else None
        )
    
    def get_entry_type(self) -> str:
        """Get the type identifier for this entry."""
        return "emergency_contact"

