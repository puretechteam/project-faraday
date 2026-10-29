"""
Placeholder for an entry this build cannot read: an unknown type (written by a
newer Faraday) or a known type with missing or malformed fields. The raw
dictionary is kept untouched and written back on every save, so nothing is
lost just because this version does not understand it.
"""

import uuid
from datetime import datetime
from typing import Optional

from .entry import BaseEntry


def _parse_time(value) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(value) if isinstance(value, str) else None
    except ValueError:
        return None


class OpaqueEntry(BaseEntry):
    read_only = True

    def __init__(self, raw: dict, problem: str = ""):
        self.raw = dict(raw)
        self.problem = problem
        entry_id = raw.get("entry_id") if isinstance(raw.get("entry_id"), str) else None
        site_note = raw.get("site_note") if isinstance(raw.get("site_note"), str) else None
        super().__init__(
            entry_id=entry_id or f"opaque-{uuid.uuid4()}",
            site_note=site_note,
            created=_parse_time(raw.get("created")),
            modified=_parse_time(raw.get("modified")),
        )

    def to_dict(self) -> dict:
        return dict(self.raw)

    @classmethod
    def from_dict(cls, data: dict) -> "OpaqueEntry":
        return cls(data)

    def get_entry_type(self) -> str:
        value = self.raw.get("type")
        return value if isinstance(value, str) else "unknown"
