# UX Specification — SuburbIQ

**BMAD Phase 3 · UX Expert** · v1.0 · 2026-08-05
**Input:** [prd.md](prd.md) · **Mockup:** [../mockup/dashboard-mock.html](../mockup/dashboard-mock.html)

---

## 1. Design Principles

1. **Answer first, evidence second.** Dan wants "go to Marrickville," not a table. The top of the page states a conclusion; the data supporting it sits below.
2. **Honest about sparsity.** Coverage percentages are shown, not hidden. A user who doesn't know 21% of records have websites will misread every chart.
3. **One page, no navigation.** The PoC output is a single scrollable document. No tabs, no routing, no server.
4. **Readable cold.** Someone opening the file with no context should understand what it is within 5 seconds.

---

## 2. Information Architecture

Single-page, five zones, ordered by decreasing abstraction:

```
┌─ 1. HEADER ─────────────────────────────────────┐
│  Category · Area · ingest timestamp · source    │
├─ 2. VERDICT ────────────────────────────────────┤
│  Top opportunity suburb, stated as a sentence   │
│  + 4 KPI tiles (businesses, suburbs, avg gap,   │
│    % with no website)                           │
├─ 3. OPPORTUNITY ────────────────────────────────┤
│  Ranked horizontal bars — best suburbs to enter │
├─ 4. SATURATION + GAP ───────────────────────────┤
│  Two columns: density by suburb | gap histogram │
├─ 5. LEADS TABLE ────────────────────────────────┤
│  Searchable, sorted by gap score desc           │
└─ 6. FOOTER: provenance + ODbL attribution ──────┘
```

**Rationale for ordering:** zone 2 serves Dan (verdict), zone 5 serves Priya (leads). Both personas get their payload without scrolling past the other's.

---

## 3. Screen Flow

The MVP is a CLI-driven artefact, so the "flow" is a command sequence:

```
   ingest ──────────► store ──────────► report ──────────► open HTML
   (progress log)     (row counts)      (file path)        (the product)
                                          │
                                          └──► export CSV (Priya's path)
```

There is no interactive state to design. Every user decision (category, area) is made at the CLI before rendering.

---

## 4. Component Specifications

### KPI tile
Large numeral, small uppercase label, optional context line. Four across on desktop, two on tablet, one on mobile.

### Opportunity bars
Horizontal bars, ranked descending, value labelled at the bar end. Rank 1 emphasised in the accent colour; ranks 2–n in a muted tone. Bar length maps to the 0–100 index.

### Saturation list
Suburb name + count + proportional bar. Sorted by count descending. Deliberately *not* a map — a choropleth needs boundary geometry that the PoC intentionally does not carry.

### Gap histogram
Vertical bars bucketing businesses into gap-score deciles. Buckets ≥60 tinted as the "opportunity zone" to make Priya's target visually obvious.

### Leads table
Columns: Business · Suburb · Phone · Website · Hours · Gap. Missing values render as a muted "—" rather than blank, so absence reads as *recorded* rather than *broken*. Client-side text filter. Capped at 100 rows in-page; full set goes to CSV.

---

## 5. Visual Language

| Token | Value | Use |
|---|---|---|
| Accent | `#f4b41a` (Yellow Pages–adjacent amber) | Primary bars, rank 1, links |
| Ink | `#12141a` | Text |
| Muted | `#6b7280` | Labels, secondary bars |
| Surface | `#ffffff` / `#171a21` dark | Cards |
| Positive | `#16a34a` | Present data |
| Warn | `#dc2626` | High gap / missing data |

Type: system UI stack. Numerals tabular so columns align. Generous whitespace — this is a document to be read, not a control panel.

**Theme:** respects `prefers-color-scheme`. The artefact may be opened in either mode.

---

## 6. Accessibility

- Colour never the sole signal — bars carry numeric labels; missing data carries the "—" glyph.
- Contrast ≥ 4.5:1 for text in both themes.
- Table is real `<table>` markup with `<th scope>`, so screen readers and paste-into-Excel both work.
- Charts are inline SVG with `<title>` elements rather than images.

---

## 7. Responsive Behaviour

| Breakpoint | Layout |
|---|---|
| ≥1000px | 4 KPI columns; saturation and gap side by side |
| 640–999px | 2 KPI columns; charts stack |
| <640px | 1 column; leads table scrolls horizontally in its own container |
