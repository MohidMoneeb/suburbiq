"""Yellow Pages Australia adapter.

STATUS: structure-complete, but blocked in practice.

yellowpages.com.au sits behind Cloudflare bot protection that returns HTTP 403
to automated clients — including on /robots.txt itself, so the site's own crawl
policy cannot be read.

Deliberate design decision (brief §4.3): this adapter does NOT attempt to
circumvent that protection. No CAPTCHA solving, no proxy rotation, no
fingerprint spoofing. It makes one polite, well-formed request and, if blocked,
raises SourceBlocked with a clear diagnostic.

The parsing path below targets the real page structure and runs whenever a
response is actually obtained (e.g. from a permitted/licensed context). Because
we cannot load a live page, the selectors are defensive: several candidate
selectors per field, plus a JSON-LD fallback, so a partial structure change
degrades rather than breaks.
"""
from typing import Iterator, Optional
import json
import re

from bs4 import BeautifulSoup

from ..models import Area, RawRecord, SourceBlocked
from ..http import get_raw
from .base import SourceAdapter

BASE = "https://www.yellowpages.com.au"
SEARCH = BASE + "/search/listings?clue={clue}&locationClue={loc}&pageNumber={page}"

# Markers that identify a bot-protection interstitial rather than a results page.
BLOCK_MARKERS = (
    "attention required", "cloudflare", "you have been blocked",
    "sorry, you have been blocked", "cf-error-details", "just a moment",
    "enable javascript and cookies",
)


class YellowPagesAdapter(SourceAdapter):
    name = "yellowpages"
    licence = ("Facts not protected by copyright in AU per Telstra v Phone "
               "Directories [2010] FCA 44; site Terms of Use restrict automated access.")

    def __init__(self, max_pages: int = 3):
        self.max_pages = max_pages

    def fetch(self, category: str, area: Area) -> Iterator[RawRecord]:
        loc = area.label.replace("Greater ", "")
        found = 0
        for page in range(1, self.max_pages + 1):
            url = SEARCH.format(clue=category, loc=loc.replace(" ", "+"), page=page)
            print(f"  GET {url}")
            resp = get_raw(url)
            self._guard(resp.status_code, resp.text)

            records = list(self._parse(resp.text, category))
            if not records:
                break
            for rec in records:
                found += 1
                yield rec
        print(f"  yellowpages: {found} listings parsed")

    def _guard(self, status: int, body: str) -> None:
        """Turn bot protection into an explicit, reportable outcome (FR4)."""
        low = body[:4000].lower()
        hit = next((m for m in BLOCK_MARKERS if m in low), None)
        if status in (403, 429, 503) or hit:
            raise SourceBlocked(
                source=self.name,
                status=status,
                detail=(f"bot protection detected"
                        + (f" (marker: '{hit}')" if hit else "")),
                remediation=(
                    "Yellow Pages AU is protected by Cloudflare and returns 403 to "
                    "automated clients, including on /robots.txt. SuburbIQ does not "
                    "circumvent access controls by design. Use --source osm (ODbL, "
                    "open) for the analytics pipeline, or obtain a licensed data feed "
                    "from Thryv Australia."
                ),
            )

    def _parse(self, html: str, category: str) -> Iterator[RawRecord]:
        soup = BeautifulSoup(html, "html.parser")

        # Preferred path: structured data, which is stabler than CSS classes.
        for rec in self._parse_jsonld(soup, category):
            yield rec
            return

        # Fallback: DOM scraping with several candidate selectors per field.
        cards = (soup.select("div.listing-item")
                 or soup.select("div[class*='listing-content']")
                 or soup.select("article[class*='listing']"))
        for card in cards:
            name = self._text(card, ["a.listing-name", "h3 a", "[class*='listing-name']"])
            if not name:
                continue
            yield RawRecord(
                source=self.name,
                native_id=self._native_id(card, name),
                fields={
                    "name": name,
                    "raw_category": self._text(card, ["[class*='listing-heading']"]) or category,
                    "street": self._text(card, ["[class*='listing-address']", "p.listing-address"]),
                    "suburb": self._text(card, ["[class*='listing-suburb']"]),
                    "state": self._text(card, ["[class*='listing-state']"]),
                    "postcode": self._text(card, ["[class*='listing-postcode']"]),
                    "phone": self._phone(card),
                    "website": self._website(card),
                    "opening_hours": self._text(card, ["[class*='open-status']"]),
                    "lat": None,
                    "lon": None,
                },
            )

    def _parse_jsonld(self, soup, category: str) -> Iterator[RawRecord]:
        for tag in soup.find_all("script", {"type": "application/ld+json"}):
            try:
                data = json.loads(tag.string or "{}")
            except (json.JSONDecodeError, TypeError):
                continue
            for item in self._iter_entities(data):
                if not item.get("name"):
                    continue
                addr = item.get("address") or {}
                geo = item.get("geo") or {}
                yield RawRecord(
                    source=self.name,
                    native_id=item.get("@id") or item["name"],
                    fields={
                        "name": item.get("name", ""),
                        "raw_category": category,
                        "street": addr.get("streetAddress", ""),
                        "suburb": addr.get("addressLocality", ""),
                        "state": addr.get("addressRegion", ""),
                        "postcode": addr.get("postalCode", ""),
                        "phone": item.get("telephone", ""),
                        "website": item.get("url", ""),
                        "opening_hours": self._hours(item.get("openingHours")),
                        "lat": self._float(geo.get("latitude")),
                        "lon": self._float(geo.get("longitude")),
                    },
                )

    @staticmethod
    def _iter_entities(data):
        """JSON-LD arrives as an object, a list, or an @graph wrapper."""
        if isinstance(data, list):
            for d in data:
                yield from YellowPagesAdapter._iter_entities(d)
        elif isinstance(data, dict):
            if "@graph" in data:
                yield from YellowPagesAdapter._iter_entities(data["@graph"])
            elif "itemListElement" in data:
                for el in data["itemListElement"]:
                    item = el.get("item", el) if isinstance(el, dict) else el
                    yield from YellowPagesAdapter._iter_entities(item)
            elif data.get("name"):
                yield data

    @staticmethod
    def _hours(v) -> str:
        if isinstance(v, list):
            return "; ".join(str(x) for x in v)
        return str(v) if v else ""

    @staticmethod
    def _float(v) -> Optional[float]:
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _text(card, selectors) -> str:
        for sel in selectors:
            el = card.select_one(sel)
            if el and el.get_text(strip=True):
                return el.get_text(" ", strip=True)
        return ""

    @staticmethod
    def _phone(card) -> str:
        el = card.select_one("a[href^='tel:']")
        if el:
            return el["href"].replace("tel:", "").strip()
        el = card.select_one("[class*='contact-phone'], [data-phone]")
        if el:
            return el.get("data-phone") or el.get_text(strip=True)
        return ""

    @staticmethod
    def _website(card) -> str:
        for a in card.select("a[href^='http']"):
            href = a["href"]
            if "yellowpages.com.au" not in href:
                return href
        return ""

    @staticmethod
    def _native_id(card, name: str) -> str:
        for attr in ("data-listing-id", "id"):
            if card.get(attr):
                return str(card[attr])
        link = card.select_one("a[href*='/listing']")
        if link:
            m = re.search(r"/(\d+)", link["href"])
            if m:
                return m.group(1)
        return name
