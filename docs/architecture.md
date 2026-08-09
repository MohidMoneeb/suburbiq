# Architecture — SuburbIQ

**BMAD Phase 4 · Architect** · v1.0 · 2026-08-05
**Input:** [prd.md](prd.md) · **Implements:** FR1–FR20, NFR1–NFR6

---

## 1. Architectural Drivers

Three findings from the brief dictate the design. Everything else follows.

| Driver | Evidence | Architectural consequence |
|---|---|---|
| **The primary source is hostile** | YP returns 403 even on `robots.txt` | Source access must be a **pluggable adapter**, never a hardcoded assumption. The domain model cannot know where data came from. |
| **Every source rate-limits** | Overpass returned 429 after 2 rapid queries | **Cache-first** fetching + backoff must live in shared infrastructure, not per-adapter. |
| **Fields are sparse and inconsistent** | `addr:suburb` present on only 13% of records | **Derivation is a required pipeline stage.** Missing data is scored, not discarded. |

---

## 2. System Overview

```
┌──────────────────────────────────────────────────────────────┐
│                          CLI (cli.py)                        │
│              ingest  ·  report  ·  export  ·  stats          │
└───────────────┬──────────────────────────────────────────────┘
                │
     ┌──────────▼───────────┐
     │   SourceAdapter ABC  │◄──── the seam that de-risks the product
     │      fetch()         │
     └──────────┬───────────┘
                │
     ┌──────────┴────────────┬──────────────────┐
     │                       │                  │
┌────▼─────────┐   ┌─────────▼────────┐  ┌──────▼────────┐
│ OSMAdapter   │   │ YellowPages      │  │ (future:      │
│ Overpass API │   │ Adapter          │  │  TrueLocal,   │
│ ODbL · LIVE  │   │ block-aware      │  │  Places, ABN) │
└────┬─────────┘   └─────────┬────────┘  └───────────────┘
     │                       │
     └───────────┬───────────┘
                 │  raw dicts
     ┌───────────▼────────────┐
     │   HTTP layer (http.py) │  cache · rate-limit · backoff
     └───────────┬────────────┘
                 │
     ┌───────────▼────────────┐
     │  Normaliser            │  phone fmt · suburb derivation · dedupe
     └───────────┬────────────┘
                 │  Business objects
     ┌───────────▼────────────┐
     │  Store (SQLite)        │  idempotent upsert
     └───────────┬────────────┘
                 │
     ┌───────────▼────────────┐
     │  Analytics             │  saturation · gap score · opportunity
     └───────────┬────────────┘
                 │
     ┌───────────▼────────────┐
     │  Reporter              │  single-file HTML + CSV
     └────────────────────────┘
```

---

## 3. The Source Adapter Contract

The single most important interface in the system. It is deliberately narrow: an adapter's only job is to produce raw records for a category and area. It knows nothing about SQLite, scoring, or rendering.

```python
class SourceAdapter(ABC):
    name: str            # provenance tag stored on every row
    licence: str         # rendered in the dashboard footer
    @abstractmethod
    def fetch(self, category: str, area: Area) -> Iterator[RawRecord]: ...
```

**Why this is the critical seam:** the Yellow Pages block is a *source* problem. Because it is contained behind `fetch()`, YP being unavailable degrades the system to "one fewer adapter" instead of breaking it. Adding TrueLocal later is a new file, not a refactor.

### 3.1 Blocked-source protocol

Adapters raise a typed `SourceBlocked` exception rather than returning empty. The CLI catches it, prints a diagnostic (status code, detected protection vendor, remediation), and exits non-zero. **A block is a reportable outcome, not a crash and not silent emptiness** — this is FR4, and it is what keeps the demo honest.

---

## 4. Data Model

### 4.1 Unified `Business` schema

| Field | Type | Source | Notes |
|---|---|---|---|
| `id` | str (PK) | derived | stable hash of source + native id |
| `source` | str | adapter | `osm` \| `yellowpages` |
| `name` | str | source | required; records without it are dropped |
| `category` | str | ingest param | normalised category slug |
| `raw_category` | str | source | original tag, kept for traceability |
| `suburb` | str | **derived** | nearest-centroid when absent |
| `state`, `postcode` | str | source | often null |
| `street` | str | source | assembled from housenumber + street |
| `lat`, `lon` | float | source | required for suburb derivation |
| `phone` | str | source | normalised to `0X XXXX XXXX` |
| `website` | str | source | |
| `opening_hours` | str | source | |
| `digital_gap_score` | int | **computed** | 0–100 |
| `ingested_at` | ts | system | provenance |

**Design note:** `digital_gap_score` is materialised into the table rather than computed at query time. It is read far more often than written, and persisting it keeps the reporting layer free of scoring logic.

### 4.2 Idempotency

`id = sha1(source + ":" + native_id)` with `INSERT ... ON CONFLICT(id) DO UPDATE`. Re-ingest refreshes fields and `ingested_at` without duplicating (FR12).

---

## 5. Key Algorithms

### 5.1 Suburb derivation (FR9)

Since `addr:suburb` covers only 13% of records:

1. Fetch `admin_level=10` boundary relations for the metro bbox once; cache their centroids.
2. For each business, assign the nearest centroid by haversine distance.
3. Prefer the source's own `addr:suburb` when present (it is authoritative).

Nearest-centroid rather than point-in-polygon is a deliberate PoC trade-off: it avoids a geometry dependency and is accurate enough for suburb-level aggregation. Point-in-polygon is the v1.1 upgrade.

### 5.2 Digital Gap Score (FR14)

Weighted sum of missing attributes — higher score = bigger gap = better prospect for Priya.

| Missing attribute | Weight | Rationale |
|---|---|---|
| website | 40 | The largest and most sellable gap |
| phone | 25 | Hard to transact without it |
| opening_hours | 20 | Primary driver of local search ranking |
| street address | 15 | Weakens map/GBP presence |

A business missing everything scores 100. One fully present scores 0.

### 5.3 Opportunity Index (FR15)

Per suburb, combining scarcity of supply with weakness of incumbents:

```
opportunity = 0.6 · norm(1 / (1 + business_count))  +  0.4 · norm(mean_digital_gap)
```

Normalised 0–100 across suburbs in the run. High = few competitors *and* the ones present are weak online. Suburbs below a minimum business count are excluded to suppress noise from single-record suburbs.

---

## 6. Technology Choices

| Layer | Choice | Rationale |
|---|---|---|
| Language | Python 3.9+ | Pre-installed; matches available libs (NFR2) |
| HTTP | `requests` | Already present; adequate for polite sequential fetching |
| Parsing | `BeautifulSoup4` | For the YP adapter's HTML path |
| Storage | SQLite (stdlib) | Zero-install, file-portable, sufficient at PoC scale |
| Analytics | stdlib + `pandas` | pandas already present; used sparingly |
| Charts | Hand-rolled inline SVG | **No CDN** — keeps the HTML single-file and offline (NFR3) |
| Dashboard | Jinja-free Python string templating | Avoids a dependency for one template |

**Rejected:** Scrapy (too heavy for a PoC and pointless against a blocked source); Playwright (its value is bypassing bot protection, which is out of scope by policy); Postgres/PostGIS (correct for v1.2 multi-tenant, overkill now).

---

## 7. PoC vs. Full Product

| Concern | PoC (this week) | Full product (v1.2+) |
|---|---|---|
| Storage | SQLite file | Postgres + PostGIS |
| Suburb assignment | Nearest centroid | Point-in-polygon on ABS SA2 boundaries |
| Ingest trigger | Manual CLI | Celery/cron scheduled crawls |
| Dashboard | Static HTML file | React SPA + FastAPI |
| Sources | OSM + YP | + TrueLocal, Google Places, ABN Lookup |
| Demand signal | Supply-side only | Joined with ABS demographics |
| Tenancy | Single user | Multi-tenant, saved searches, billing |

**Deliberate PoC limitation:** the Opportunity Index currently measures *supply* only — it infers demand from the absence of competitors. That is a real analytical weakness, honestly stated. Genuine demand modelling requires the ABS population/income join scheduled for v1.3. The PoC is a directional tool, not a valuation model.

---

## 8. Failure Modes

| Failure | Handling |
|---|---|
| Source blocked (403/challenge) | `SourceBlocked` → diagnostic + non-zero exit |
| Rate limited (429) | Exponential backoff, up to 4 retries |
| Partial chunk failure | Logged and skipped; run continues (NFR4) |
| Record missing name or coords | Dropped at normalisation with a counted reason |
| Empty result set | Report renders with an explicit "no data" state |

---

## 9. Repository Layout

```
suburbiq/
├── docs/           brief.md · prd.md · architecture.md · ux-spec.md · stories/
├── mockup/         dashboard-mock.html      (UX phase, pre-code)
├── poc/suburbiq/
│   ├── models.py   Business, Area, RawRecord, SourceBlocked
│   ├── http.py     cache · rate limit · backoff
│   ├── sources/    base.py · osm.py · yellowpages.py
│   ├── normalise.py  phone · suburb · dedupe
│   ├── store.py    SQLite upsert + queries
│   ├── analytics.py  saturation · gap · opportunity
│   ├── report.py   single-file HTML + CSV
│   └── cli.py      ingest · report · export · stats
├── data/           suburbiq.db · http cache
└── out/            dashboard.html · leads.csv
```
