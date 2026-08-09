"""OpenStreetMap adapter via the Overpass API.

Default production source. ODbL-licensed, no API key, commercially usable with
attribution — which is why it, not Yellow Pages, anchors the MVP.
"""
from typing import Iterator, List, Tuple, Dict

from ..models import Area, RawRecord, CATEGORIES
from ..http import post_cached, load_json
from .base import SourceAdapter

ENDPOINT = "https://overpass-api.de/api/interpreter"


class OSMAdapter(SourceAdapter):
    name = "osm"
    licence = "© OpenStreetMap contributors, ODbL"

    def _query(self, filters: List[Tuple[str, str]], area: Area) -> str:
        clauses = "\n".join(
            f'  nwr["{k}"="{v}"]({area.bbox});' for k, v in filters
        )
        return f"[out:json][timeout:180];\n(\n{clauses}\n);\nout center tags;"

    def fetch(self, category: str, area: Area) -> Iterator[RawRecord]:
        filters = CATEGORIES.get(category)
        if not filters:
            raise ValueError(
                f"unknown category '{category}'. known: {', '.join(sorted(CATEGORIES))}"
            )

        q = self._query(filters, area)
        print(f"  querying Overpass for '{category}' in {area.label}...")
        text = post_cached(ENDPOINT, {"data": q},
                           cache_key=f"osm:{category}:{area.slug}")
        payload = load_json(text)
        elements = payload.get("elements", [])
        print(f"  Overpass returned {len(elements)} elements")

        for el in elements:
            tags = el.get("tags", {})
            if not tags.get("name"):
                continue  # unnamed POIs are not businesses for our purposes
            lat = el.get("lat") or (el.get("center") or {}).get("lat")
            lon = el.get("lon") or (el.get("center") or {}).get("lon")
            if lat is None or lon is None:
                continue
            yield RawRecord(
                source=self.name,
                native_id=f"{el.get('type')}/{el.get('id')}",
                fields={
                    "name": tags.get("name", ""),
                    "raw_category": self._raw_category(tags),
                    "suburb": tags.get("addr:suburb", ""),
                    "state": tags.get("addr:state", ""),
                    "postcode": tags.get("addr:postcode", ""),
                    "street": self._street(tags),
                    "lat": float(lat),
                    "lon": float(lon),
                    "phone": tags.get("phone") or tags.get("contact:phone", ""),
                    "website": tags.get("website") or tags.get("contact:website", ""),
                    "opening_hours": tags.get("opening_hours", ""),
                },
            )

    @staticmethod
    def _street(tags: Dict[str, str]) -> str:
        num, street = tags.get("addr:housenumber", ""), tags.get("addr:street", "")
        return f"{num} {street}".strip()

    @staticmethod
    def _raw_category(tags: Dict[str, str]) -> str:
        for key in ("amenity", "shop", "craft", "leisure", "healthcare"):
            if tags.get(key):
                return f"{key}={tags[key]}"
        return ""


def fetch_suburb_centroids(area: Area) -> List[Tuple[str, float, float]]:
    """Suburb centroids for nearest-neighbour assignment.

    Needed because addr:suburb is populated on only ~13% of records, so suburb
    has to be derived from coordinates (architecture §5.1).
    """
    # Australian suburbs are tagged as place=suburb nodes, not admin_level=10
    # boundary relations (which returned zero for Greater Sydney).
    q = (f"[out:json][timeout:180];\n"
         f'(node["place"~"^(suburb|neighbourhood|town)$"]({area.bbox});)\n;'
         f"\nout tags center;")
    text = post_cached(ENDPOINT, {"data": q}, cache_key=f"osm:suburbs2:{area.slug}")
    out = []
    for el in load_json(text).get("elements", []):
        name = el.get("tags", {}).get("name")
        lat = el.get("lat") or (el.get("center") or {}).get("lat")
        lon = el.get("lon") or (el.get("center") or {}).get("lon")
        if name and lat is not None:
            out.append((name, float(lat), float(lon)))
    return out
