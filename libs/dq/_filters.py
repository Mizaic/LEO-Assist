"""Shared filter dataclass used across all DQ service functions."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class DQFilters:
    """Common filter parameters accepted by DQ service functions."""

    patient_id: Optional[str] = None
    site: Optional[str] = None
    status: Optional[str] = None
    since: Optional[str] = None       # ISO date string YYYY-MM-DD
    until: Optional[str] = None       # ISO date string YYYY-MM-DD
    domain_id: Optional[str] = None
    limit: int = 500
    offset: int = 0

    def to_cypher_params(self) -> dict:
        """Return a dict suitable for use as Cypher query parameters."""
        return {k: v for k, v in {
            "patient_id": self.patient_id,
            "site": self.site,
            "status": self.status,
            "since": self.since,
            "until": self.until,
            "domain_id": self.domain_id,
            "limit": self.limit,
            "offset": self.offset,
        }.items() if v is not None}
