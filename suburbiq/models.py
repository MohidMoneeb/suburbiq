"""Core domain types shared by every layer.

The Business schema is deliberately source-agnostic: adapters translate into it,
and nothing downstream of normalisation knows where a record came from.
"""
from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, Any
import hashlib


class SourceBlocked(Exception):
    """A source refused automated access (bot protection, 403, challenge page).

    Raised instead of returning empty results so the CLI can report the block
    explicitly rather than silently producing a zero-row dataset (PRD FR4).
    """

    def __init__(self, source: str, status: int, detail: str, remediation: str = ""):
        self.source = source
        self.status = status
        self.detail = detail
        self.remediation = remediation
        super().__init__(f"{source} blocked (HTTP {status}): {detail}")


@dataclass(frozen=True)
class Area:
    """A named metro area addressed as a bounding box."""
    slug: str
    label: str
    south: float
    west: float
    north: float
    east: float

    @property
    def bbox(self) -> str:
        return f"{self.south},{self.west},{self.north},{self.east}"


# Metro bounding boxes. Kept small and explicit rather than geocoded at runtime,
# so a PoC run never depends on a geocoding service being up.
AREAS: Dict[str, Area] = {
    "sydney":    Area("sydney", "Greater Sydney", -34.10, 150.80, -33.65, 151.35),
    "melbourne": Area("melbourne", "Greater Melbourne", -38.05, 144.55, -37.995, 145.85),
    "brisbane":  Area("brisbane", "Greater Brisbane", -27.75, 152.85, -27.30, 153.25),
    "perth":     Area("perth", "Greater Perth", -32.20, 115.65, -31.70, 116.10),
    "adelaide":  Area("adelaide", "Greater Adelaide", -35.15, 138.45, -34.70, 138.80),
}


@dataclass
class RawRecord:
    """Whatever an adapter pulled, before normalisation."""
    source: str
    native_id: str
    fields: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Business:
    """The unified schema. One row per business, per source."""
    id: str
    source: str
    name: str
    category: str
    raw_category: str = ""
    suburb: str = ""
    state: str = ""
    postcode: str = ""
    street: str = ""
    lat: Optional[float] = None
    lon: Optional[float] = None
    phone: str = ""
    website: str = ""
    opening_hours: str = ""
    digital_gap_score: int = 0
    ingested_at: str = ""

    @staticmethod
    def make_id(source: str, native_id: str) -> str:
        """Stable PK so re-ingesting updates rather than duplicates (FR12)."""
        return hashlib.sha1(f"{source}:{native_id}".encode()).hexdigest()[:16]

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


# Category slug -> OSM tag filters. Mirrors the way a directory groups trades,
# which is what makes OSM a usable stand-in for a Yellow Pages taxonomy.
CATEGORIES: Dict[str, list] = {
    "cafe":       [("amenity", "cafe")],
    "restaurant": [("amenity", "restaurant")],
    "plumber":    [("craft", "plumber"), ("shop", "plumber")],
    "electrician":[("craft", "electrician")],
    "hairdresser":[("shop", "hairdresser")],
    "gym":        [("leisure", "fitness_centre")],
    "dentist":    [("amenity", "dentist"), ("healthcare", "dentist")],
    "bakery":     [("shop", "bakery")],
    "childcare":  [("amenity", "childcare"), ("amenity", "kindergarten")],
    "veterinary": [("amenity", "veterinary")],
}
