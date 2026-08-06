"""
Secure note entry model.
"""

from datetime import datetime
from typing import Optional
from .entry import BaseEntry


class SecureNoteEntry(BaseEntry):
    """Entry for storing secure notes (multiline text)."""
    
    sensitivity_level = "normal"
    
    def __init__(self, content: str, title: Optional[str] = None, entry_id: Optional[str] = None, site_note: Optional[str] = None, created: Optional[datetime] = None, modified: Optional[datetime] = None):
        """Initialize secure note entry."""
        super().__init__(entry_id, site_note, created, modified)
        self.title = title or ""
        self.content = content
    
    def to_dict(self) -> dict:
        """Convert entry to dictionary for serialization."""
        return {
            "type": "secure_note",
            "entry_id": self.entry_id,
            "title": self.title,
            "content": self.content,
            "site_note": self.site_note,
            "created": self.created.isoformat(),
            "modified": self.modified.isoformat()
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'SecureNoteEntry':
        """Create entry from dictionary."""
        return cls(
            content=data["content"],
            title=data.get("title"),
            entry_id=data.get("entry_id"),
            site_note=data.get("site_note"),
            created=datetime.fromisoformat(data["created"]) if "created" in data else None,
            modified=datetime.fromisoformat(data["modified"]) if "modified" in data else None
        )
    
    def get_entry_type(self) -> str:
        """Get the type identifier for this entry."""
        return "secure_note"

