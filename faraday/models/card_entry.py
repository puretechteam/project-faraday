"""
Credit/debit card entry model.
"""

from datetime import datetime
from typing import Optional
from .entry import BaseEntry


class CardEntry(BaseEntry):
    """Entry for storing credit/debit card information."""
    
    sensitivity_level = "sensitive"
    
    def __init__(self, cardholder_name: str, card_number: str, expiration_month: int, expiration_year: int, cvv: str, billing_zip: str, entry_id: Optional[str] = None, site_note: Optional[str] = None, created: Optional[datetime] = None, modified: Optional[datetime] = None):
        """Initialize card entry."""
        super().__init__(entry_id, site_note, created, modified)
        self.cardholder_name = cardholder_name
        self.card_number = card_number
        self.expiration_month = expiration_month
        self.expiration_year = expiration_year
        self.cvv = cvv
        self.billing_zip = billing_zip
    
    def to_dict(self) -> dict:
        """Convert entry to dictionary for serialization."""
        return {
            "type": "card",
            "entry_id": self.entry_id,
            "cardholder_name": self.cardholder_name,
            "card_number": self.card_number,
            "expiration_month": self.expiration_month,
            "expiration_year": self.expiration_year,
            "cvv": self.cvv,
            "billing_zip": self.billing_zip,
            "site_note": self.site_note,
            "created": self.created.isoformat(),
            "modified": self.modified.isoformat()
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'CardEntry':
        """Create entry from dictionary."""
        return cls(
            cardholder_name=data["cardholder_name"],
            card_number=data["card_number"],
            expiration_month=data["expiration_month"],
            expiration_year=data["expiration_year"],
            cvv=data["cvv"],
            billing_zip=data["billing_zip"],
            entry_id=data.get("entry_id"),
            site_note=data.get("site_note"),
            created=datetime.fromisoformat(data["created"]) if "created" in data else None,
            modified=datetime.fromisoformat(data["modified"]) if "modified" in data else None
        )
    
    def get_entry_type(self) -> str:
        """Get the type identifier for this entry."""
        return "card"

