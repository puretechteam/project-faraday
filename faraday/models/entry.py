"""
Base entry model for vault entries.
"""

import uuid
from datetime import datetime
from typing import Optional
from abc import ABC, abstractmethod


class BaseEntry(ABC):
    """Base class for all vault entries."""
    
    sensitivity_level: str = "normal"  # Class attribute: "normal" | "sensitive" | "critical"
    
    def __init__(self, entry_id: Optional[str] = None, site_note: Optional[str] = None, created: Optional[datetime] = None, modified: Optional[datetime] = None):
        """Initialize base entry."""
        self.entry_id = entry_id or str(uuid.uuid4())
        self.site_note = site_note or ""
        self.created = created or datetime.utcnow()
        self.modified = modified or datetime.utcnow()
    
    def update_modified(self):
        """Update the modified timestamp."""
        self.modified = datetime.utcnow()
    
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
