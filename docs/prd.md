# Product Requirements Document — SuburbIQ

**BMAD Phase 2 · Product Manager** · v1.0 · 2026-08-05
**Input:** [brief.md](brief.md) · **Output feeds:** [architecture.md](architecture.md), [ux-spec.md](ux-spec.md)

---

## 1. Goals

| # | Goal | Measure |
|---|---|---|
| G1 | Turn raw AU directory listings into decision-grade suburb intelligence | 3 analytics shipped, all from real data |
| G2 | Never depend on a single data source | ≥2 adapters behind one interface |
| G3 | Operate legally and transparently | No bot-protection circumvention; ODbL attribution rendered |
| G4 | Deliver an answer in one command | `ingest` → `report` in <5 min for a metro category |
| G5 | Make digital-gap leads directly actionable | CSV export with contactable, ranked businesses |

---

## 2. Personas

### P1 — "Dan", trades operator (primary, MVP)
Runs a 4-van plumbing business in Western Sydney. Wants a fifth van but doesn't know which suburb. Not technical; will read a chart, will not read a CSV.
- **Job:** "Show me which nearby suburbs are underserved."
- **Success:** a ranked suburb shortlist he can defend to his business partner.

### P2 — "Priya", agency owner (primary, monetisation)
Runs a 6-person digital agency in Melbourne selling websites and GBP management. Prospecting is her bottleneck.
- **Job:** "Give me 200 local businesses with no website, with phone numbers."
- **Success:** a CSV her sales rep can call down today.

### P3 — "Marcus", franchise development manager (secondary, expansion)
Assesses territories for a food franchise. Currently pays for enterprise GIS.
- **Job:** "Compare competitive density across 40 suburbs."
- **Success:** a saturation map he can paste into a board deck.

**MVP prioritisation:** P1 and P2 drive all MVP requirements. P3 is served incidentally by the Saturation Map.

---

## 3. Functional Requirements

### Data acquisition
- **FR1** The system SHALL define a single source-adapter interface that all data sources implement.
- **FR2** The system SHALL provide an OpenStreetMap/Overpass adapter as the default source.
- **FR3** The system SHALL provide a Yellow Pages AU adapter implementing the real site's request and parse structure.
- **FR4** The YP adapter SHALL detect bot-protection blocks (HTTP 403/429/challenge markers) and terminate with a clear diagnostic. It SHALL NOT attempt to circumvent them.
- **FR5** All adapters SHALL rate-limit requests and apply exponential backoff on 429.
- **FR6** The system SHALL cache raw source responses on disk, keyed by request, so re-runs do not re-hit the network.
- **FR7** The system SHALL accept a category and a named metro area as ingest parameters.

### Normalisation
- **FR8** Every adapter SHALL emit records conforming to one unified `Business` schema.
- **FR9** The system SHALL derive `suburb` from coordinates when the source omits it.
- **FR10** The system SHALL normalise Australian phone numbers to a canonical format.
- **FR11** The system SHALL deduplicate businesses across and within sources.
- **FR12** The system SHALL persist to SQLite idempotently — re-ingesting SHALL update, not duplicate.

### Analytics
- **FR13** The system SHALL compute **Saturation**: business count per suburb per category.
- **FR14** The system SHALL compute a per-business **Digital Gap Score** (0–100) from presence of website, phone, opening hours, and address completeness.
- **FR15** The system SHALL compute an **Opportunity Index** per suburb combining low supply with weak incumbent digital presence.
- **FR16** The system SHALL report field-coverage statistics for every ingested dataset.

### Presentation
- **FR17** The system SHALL render a self-contained HTML dashboard requiring no server or network.
- **FR18** The dashboard SHALL present saturation, opportunity ranking, digital-gap distribution, and a searchable business table.
- **FR19** The system SHALL export the ranked digital-gap business list as CSV.
- **FR20** The dashboard SHALL display data provenance, ingest timestamp, and ODbL attribution.

---

## 4. Non-Functional Requirements

- **NFR1** A 3,000-business metro ingest SHALL complete in under 5 minutes on a warm cache.
- **NFR2** The PoC SHALL run on Python 3.9+ with no paid services and no API keys.
- **NFR3** The dashboard HTML SHALL be a single file, openable offline.
- **NFR4** The system SHALL be resilient to partial source failure — one failed chunk SHALL NOT abort the run.
- **NFR5** No personal names or email addresses SHALL be collected (Privacy Act posture).
- **NFR6** All network access SHALL be politely paced (≥1s between Overpass calls).

---

## 5. Epics & Stories

### Epic 1 — Ingestion Foundation
- **1.1** As a developer, I want a `Business` dataclass and SQLite store so every source lands in one shape.
- **1.2** As a developer, I want a `SourceAdapter` ABC so sources are swappable.
- **1.3** As an operator, I want a disk cache so repeated runs are fast and polite.

### Epic 2 — Source Adapters
- **2.1** As an analyst, I want an OSM adapter that pulls a category across a metro bbox.
- **2.2** As an analyst, I want suburb derivation from coordinates so grouping works despite sparse `addr:suburb`.
- **2.3** As a stakeholder, I want a YP adapter that proves the site structure is understood and reports blocks honestly.

### Epic 3 — Analytics
- **3.1** As Dan, I want saturation per suburb so I can see competitive density.
- **3.2** As Priya, I want a Digital Gap Score per business so I can rank prospects.
- **3.3** As Dan, I want an Opportunity Index so underserved suburbs surface automatically.
- **3.4** As a user, I want coverage stats so I know how complete the data is.

### Epic 4 — Dashboard & Export
- **4.1** As Dan, I want a visual dashboard so I can read the result without SQL.
- **4.2** As Priya, I want CSV export of ranked leads.
- **4.3** As a compliance reviewer, I want provenance and licence attribution visible.

---

## 6. MVP Acceptance Criteria

The PoC is accepted when:

1. `python -m suburbiq.cli ingest --source osm --category cafe --area sydney` ingests **≥1,000 real businesses**.
2. `report` emits a single HTML file rendering all three analytics from that data.
3. Digital-gap CSV export opens with correct headers and ranked rows.
4. `--source yellowpages` runs and reports the Cloudflare block explicitly, exiting non-zero without a stack trace.
5. Re-running ingest does not duplicate rows.
6. Dashboard shows the ODbL attribution and ingest timestamp.

---

## 7. Out of Scope (post-MVP roadmap)

| Phase | Capability |
|---|---|
| v1.1 | Scheduled re-crawls, change detection ("new businesses this month") |
| v1.2 | Multi-tenant SaaS: accounts, saved searches, billing |
| v1.3 | ABS demographic joins (population, income) for true demand modelling |
| v1.4 | Additional adapters: TrueLocal, Google Places, ABN Lookup |
| v2.0 | Alerting: notify when a suburb crosses a saturation threshold |
