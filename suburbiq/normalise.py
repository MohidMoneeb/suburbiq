"""Raw records -> Business objects.

Handles the three messes the brief identified: inconsistent phone formats,
suburb missing on ~87% of records, and duplicates across/within sources.
"""
import math
import re
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Tuple

from .models import Business, RawRecord


def normalise_phone(raw: str) -> str:
    """Australian numbers to a canonical local format."""
    if not raw:
        return ""
    digits = re.sub(r"[^\d+]", "", raw.split(";")[0].split(",")[0])
    digits = re.sub(r"^\+61", "0", digits)
    if not digits.startswith("0") and len(digits) in (8, 9):
        digits = "0" + digits  # area code dropped by the source
    if len(digits) == 10 and digits.startswith("04"):        # mobile
        return f"{digits[:4]} {digits[4:7]} {digits[7:]}"
    if len(digits) == 10:                                    # landline
        return f"{digits[:2]} {digits[2:6]} {digits[6:]}"
    return digits


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km."""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


class SuburbResolver:
    """Nearest-centroid suburb assignment (architecture §5.1).

    A source-provided suburb always wins; the centroid is only a fallback.
    """

    def __init__(self, centroids: List[Tuple[str, float, float]]):
        self.centroids = centroids

    def resolve(self, given: str, lat, lon) -> str:
        if given:
            return given.strip()
        if lat is None or lon is None or not self.centroids:
            return ""
        best, best_d = "", 1e9
        for name, clat, clon in self.centroids:
            d = haversine(lat, lon, clat, clon)
            if d < best_d:
                best, best_d = name, d
        # Beyond ~15km the nearest centroid is not a meaningful suburb claim.
        return best if best_d <= 15 else ""


DIGITAL_GAP_WEIGHTS = {"website": 40, "phone": 25, "opening_hours": 20, "street": 15}


def digital_gap_score(b: Business) -> int:
    """0 = complete online presence, 100 = absent. Higher = better prospect."""
    return sum(w for field, w in DIGITAL_GAP_WEIGHTS.items()
               if not getattr(b, field, ""))


def _dedupe_key(b: Business) -> str:
    name = re.sub(r"[^a-z0-9]", "", b.name.lower())
    if b.phone:
        return f"p:{re.sub(r'[^0-9]', '', b.phone)}"
    if b.lat is not None and b.lon is not None:
        # ~100m grid: same name at the same corner is the same business
        return f"n:{name}:{round(b.lat, 3)}:{round(b.lon, 3)}"
    return f"n:{name}:{b.suburb.lower()}"


def normalise(records: Iterable[RawRecord], category: str,
              resolver: SuburbResolver) -> Tuple[List[Business], Dict[str, int]]:
    """Returns (businesses, drop-reason counts)."""
    out: Dict[str, Business] = {}
    dropped = {"no_name": 0, "no_suburb": 0, "duplicate": 0}
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    for rec in records:
        f = rec.fields
        name = (f.get("name") or "").strip()
        if not name:
            dropped["no_name"] += 1
            continue

        lat, lon = f.get("lat"), f.get("lon")
        suburb = resolver.resolve(f.get("suburb", ""), lat, lon)
        if not suburb:
            dropped["no_suburb"] += 1
            continue

        b = Business(
            id=Business.make_id(rec.source, rec.native_id),
            source=rec.source,
            name=name,
            category=category,
            raw_category=f.get("raw_category", ""),
            suburb=suburb,
            state=f.get("state", ""),
            postcode=f.get("postcode", ""),
            street=(f.get("street") or "").strip(),
            lat=lat,
            lon=lon,
            phone=normalise_phone(f.get("phone", "")),
            website=(f.get("website") or "").strip(),
            opening_hours=(f.get("opening_hours") or "").strip(),
            ingested_at=now,
        )
        b.digital_gap_score = digital_gap_score(b)

        key = _dedupe_key(b)
        if key in out:
            dropped["duplicate"] += 1
            continue
        out[key] = b

    return list(out.values()), dropped
