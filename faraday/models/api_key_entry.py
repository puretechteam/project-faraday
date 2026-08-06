"""
API/Developer keys entry model.
"""

from datetime import datetime
from typing import Optional
from .entry import BaseEntry


class ApiKeyEntry(BaseEntry):
    """Entry for storing API keys and developer credentials."""
    
    sensitivity_level = "sensitive"
    
    def __init__(self, service_name: str, api_key: str, api_secret: Optional[str] = None, environment: str = "prod", notes: Optional[str] = None, entry_id: Optional[str] = None, site_note: Optional[str] = None, created: Optional[datetime] = None, modified: Optional[datetime] = None):
        """Initialize API key entry."""
        super().__init__(entry_id, site_note, created, modified)
        self.service_name = service_name
        self.api_key = api_key
        self.api_secret = api_secret or ""
        self.environment = environment  # prod, dev, staging
        self.notes = notes or ""
    
    def to_dict(self) -> dict:
        """Convert entry to dictionary for serialization."""
        return {
            "type": "api_key",
            "entry_id": self.entry_id,
            "service_name": self.service_name,
            "api_key": self.api_key,
            "api_secret": self.api_secret,
            "environment": self.environment,
            "notes": self.notes,
            "site_note": self.site_note,
            "created": self.created.isoformat(),
            "modified": self.modified.isoformat()
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'ApiKeyEntry':
        """Create entry from dictionary."""
        return cls(
            service_name=data["service_name"],
            api_key=data["api_key"],
            api_secret=data.get("api_secret"),
            environment=data.get("environment", "prod"),
            notes=data.get("notes"),
            entry_id=data.get("entry_id"),
            site_note=data.get("site_note"),
            created=datetime.fromisoformat(data["created"]) if "created" in data else None,
            modified=datetime.fromisoformat(data["modified"]) if "modified" in data else None
        )
    
    def get_entry_type(self) -> str:
        """Get the type identifier for this entry."""
        return "api_key"

