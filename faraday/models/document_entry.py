"""
Document storage entry model.
"""

from datetime import datetime
from typing import Optional
from .entry import BaseEntry


class DocumentEntry(BaseEntry):
    """Entry for storing encrypted document references."""
    
    sensitivity_level = "critical"
    
    def __init__(self, filename: str, mime_type: str, file_reference: str, file_size: int, file_hash: str, category: str = "General", upload_timestamp: Optional[datetime] = None, entry_id: Optional[str] = None, site_note: Optional[str] = None, created: Optional[datetime] = None, modified: Optional[datetime] = None):
        """Initialize document entry."""
        super().__init__(entry_id, site_note, created, modified)
        self.filename = filename
        self.mime_type = mime_type
        self.file_reference = file_reference  # UUID for encrypted file
        self.file_size = file_size
        self.file_hash = file_hash  # SHA-256 hash
        self.category = category or "General"
        self.upload_timestamp = upload_timestamp or datetime.utcnow()
    
    def to_dict(self) -> dict:
        """Convert entry to dictionary for serialization."""
        return {
            "type": "document",
            "entry_id": self.entry_id,
            "filename": self.filename,
            "mime_type": self.mime_type,
            "file_reference": self.file_reference,
            "file_size": self.file_size,
            "file_hash": self.file_hash,
            "category": self.category,
            "upload_timestamp": self.upload_timestamp.isoformat(),
            "site_note": self.site_note,
            "created": self.created.isoformat(),
            "modified": self.modified.isoformat()
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'DocumentEntry':
        """Create entry from dictionary."""
        return cls(
            filename=data["filename"],
            mime_type=data["mime_type"],
            file_reference=data["file_reference"],
            file_size=data["file_size"],
            file_hash=data["file_hash"],
            category=data.get("category") or "General",
            upload_timestamp=datetime.fromisoformat(data["upload_timestamp"]) if "upload_timestamp" in data else None,
            entry_id=data.get("entry_id"),
            site_note=data.get("site_note"),
            created=datetime.fromisoformat(data["created"]) if "created" in data else None,
            modified=datetime.fromisoformat(data["modified"]) if "modified" in data else None
        )
    
    def get_entry_type(self) -> str:
        """Get the type identifier for this entry."""
        return "document"

