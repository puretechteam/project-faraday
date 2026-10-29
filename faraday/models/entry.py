"""
Base entry model for vault entries.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional
from abc import ABC, abstractmethod


def _utc_now() -> datetime:
    """Naive UTC timestamp, the same on-disk format the deprecated datetime.utcnow() produced."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class BaseEntry(ABC):
    """Base class for all vault entries."""
    
    sensitivity_level: str = "normal"  # Class attribute: "normal" | "sensitive" | "critical"
    
    def __init__(self, entry_id: Optional[str] = None, site_note: Optional[str] = None, created: Optional[datetime] = None, modified: Optional[datetime] = None):
        """Initialize base entry."""
        self.entry_id = entry_id or str(uuid.uuid4())
        self.site_note = site_note or ""
        self.created = created or _utc_now()
        self.modified = modified or _utc_now()
    
    def update_modified(self):
        """Update the modified timestamp."""
        self.modified = _utc_now()
    
    @abstractmethod
    def to_dict(self) -> dict:
        """Convert entry to dictionary for serialization."""
        pass
    
    @classmethod
    @abstractmethod
    def from_dict(cls, data: dict) -> 'BaseEntry':
        """Create entry from dictionary."""
        pass
    
    @abstractmethod
    def get_entry_type(self) -> str:
        """Get the type identifier for this entry."""
        pass
