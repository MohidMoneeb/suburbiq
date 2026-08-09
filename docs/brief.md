# Project Brief — SuburbIQ

**BMAD Phase 1 · Analyst** · Author: Claude · Date: 2026-08-05 · Status: Approved for PRD

---

## 1. Executive Summary

**SuburbIQ** turns Australian business-directory data into suburb-level market intelligence.

The original idea was "scrape Yellow Pages Australia and show analytics in a dashboard." Research showed that idea is directionally right but needs two corrections to become a product:

1. **A raw directory dashboard is not a product.** Yellow Pages already shows people a list of plumbers. Counting those plumbers on a chart adds nothing a user would pay for. The value is not the listings — it's the *derived* signal: which suburbs are saturated, which are underserved, and which businesses have weak digital presence.
2. **Yellow Pages cannot be the only source.** It is hard-blocked (see §5) and legally contested. The product must be source-agnostic from day one.

The reframed product: **a market-gap and lead-quality engine for Australian local markets.** Pick a category and a metro area; SuburbIQ tells you where the demand/supply imbalance is, and hands you a ranked list of businesses with fixable digital gaps.

---

## 2. Problem Statement

Three distinct groups repeatedly do the same painful manual work:

**A. Trades/services operators expanding territory.** A plumbing or physio business deciding which suburb to open in searches directories by hand, counts competitors, and guesses. There is no cheap way to compare 40 suburbs on competitive density.

**B. Digital marketing agencies prospecting.** Agencies selling websites, SEO, and Google Business Profile management need lists of local businesses with *demonstrable* digital weakness — no website, no listed hours, no phone. Today they trawl directories one listing at a time.

**C. Franchise development managers.** Evaluating territories requires competitor counts per suburb. Existing site-selection tools (Maptitude and similar) cost $200–$10,000/month and are aimed at enterprise.

The common gap: **directory data is browsable but not analysable.** Nobody sells the aggregate view at a small-business price point.

---

## 3. Market & Domain Research

### 3.1 The Yellow Pages AU landscape

- Yellow Pages AU is operated by **Sensis**, acquired by Nasdaq-listed **Thryv** in March 2021 for ~A$260M and rebranded Thryv Australia in September 2021.
- Sensis is Australia's largest directory publisher, also operating White Pages, TrueLocal, and Whereis.
- Yellow.com.au reports **6M+ searches/month** — the category still has real consumer usage.

**Implication:** the directory data has commercial relevance, and the incumbent monetises *advertising to listed businesses*, not analytics. The analytics layer is an unoccupied adjacent niche.

### 3.2 Competitive landscape

| Segment | Examples | Price | Gap SuburbIQ exploits |
|---|---|---|---|
| Enterprise site selection | Maptitude, Locus, Location Genius | $200–$10k/mo | Too expensive/heavy for SMBs and small agencies |
| Competitive intelligence | Prisync, Capterra-listed CI tools | Mid | Focused on **pricing/e-commerce**, not local service density |
| Directories themselves | Yellow Pages, TrueLocal, Google Maps | Free | Browse-only; no aggregate, no gap analysis, no export |
| Generic scrapers | Apify actors, Octoparse | Low | Deliver raw rows; user still has to do all analysis |

**Positioning:** SuburbIQ sits between "raw scraper output" and "enterprise GIS." It is the *analysis layer* — opinionated, category-specific, and priced for SMBs/agencies.

### 3.3 Domain constraints unique to Australia

- Population is extremely concentrated in a handful of metros, so **suburb** (not state or postcode) is the right analytical unit.
- Suburb names are the natural vocabulary of both consumers and operators ("a plumber in Marrickville").
- Australian addresses in open data are inconsistently tagged, so suburb must often be **derived from coordinates**, not read from a field. This is confirmed empirically in §5.

---

## 4. Legal & Ethical Assessment

This drove the architecture more than any other factor.

### 4.1 Copyright — favourable

In **Telstra Corporation Ltd v Phone Directories Company Pty Ltd [2010] FCA 44** (upheld on appeal), the Federal Court held that **copyright does not subsist in the White Pages and Yellow Pages directories**. They are not original literary works: "sweat of the brow" compilation is insufficient, and the automated production process defeated the requirement of a human author's independent intellectual effort. Australia has **no sui generis database right** (unlike the EU).

**So:** the *facts* in a directory — business name, address, phone — are not protected by copyright in Australia.

### 4.2 What still constrains us

Copyright is not the only barrier, and this is where the original idea gets into trouble:

- **Contract.** Yellow Pages' Terms of Use prohibit automated access. That is a contractual matter independent of copyright.
- **Technical access controls.** The site is protected by Cloudflare. Circumventing an access control is a different act from copying an unprotected fact.
- **Privacy Act 1988.** Sole-trader listings can constitute personal information. Scale collection of individuals' contact details carries obligations.

### 4.3 Position taken

SuburbIQ **does not circumvent bot protection**. No CAPTCHA solving, no residential proxy rotation, no browser-fingerprint spoofing. The Yellow Pages adapter is built to the real site structure and is polite and rate-limited, but if the site blocks it, **it reports the block and stops** — it does not escalate.

The default production source is **OpenStreetMap via the Overpass API**, which is licensed under **ODbL**: explicitly open, commercially usable, and redistributable with attribution to "© OpenStreetMap contributors."

This is not a compromise — it is a better commercial foundation. A product whose data supply can be terminated by one Cloudflare rule is not investable.

---

## 5. Technical Feasibility — Evidence

Probes run 2026-08-05 from this environment.

| Test | Result |
|---|---|
| `curl` → `yellowpages.com.au/robots.txt` | **HTTP 403** — Cloudflare "Sorry, you have been blocked" |
| `curl` → YP search results page | **HTTP 403** |
| Real browser engine → yellowpages.com.au | **Hard block**, not a solvable JS challenge |
| Overpass API → cafés, Greater Sydney bbox | **HTTP 200 — 2,791 businesses** |
| Overpass, rapid successive queries | **HTTP 429** — rate limited |

Field coverage on the 2,791-café Sydney sample:

| Field | Coverage |
|---|---|
| name | 2,639 (95%) |
| cuisine | 1,012 (36%) |
| opening_hours | 792 (28%) |
| website | 582 (21%) |
| phone | 351 (13%) |
| addr:suburb | 350 (13%) |

**Two conclusions that shaped the architecture:**

1. **`robots.txt` itself returns 403.** We cannot read Yellow Pages' crawl policy, let alone comply with it. Building the MVP's data supply on that source is not viable.
2. **Sparse fields are the product, not a defect.** Only 21% of Sydney cafés have a website and 13% a phone number. That *is* the digital-gap signal agencies want to buy. Low coverage in the raw data becomes the core feature.

Because `addr:suburb` is only 13% populated, suburb must be derived from lat/lon by nearest-centroid assignment — a required pipeline stage, not an optional enrichment.

---

## 6. Proposed Solution

A pipeline: **Source adapters → normalised schema → SQLite → analytics → dashboard.**

Three analytical outputs, each mapping to a user segment:

1. **Saturation Map** — businesses per suburb per category, so operators see competitive density at a glance. *(Segment A, C)*
2. **Digital Gap Score** — a 0–100 per-business score from missing website, phone, hours, and address completeness. Ranked and exportable. *(Segment B)*
3. **Opportunity Index** — suburbs ranked by low supply combined with weak incumbent digital presence: where a well-run new entrant would win. *(Segment A)*

The source-adapter boundary is the key design decision: any directory can be plugged in behind one interface, so no single provider can kill the product.

---

## 7. MVP Scope

**In scope**
- Two source adapters: OpenStreetMap/Overpass (working) and Yellow Pages (structure-complete, block-aware)
- Category + metro-area selection
- Normalisation, dedupe, suburb derivation, SQLite persistence
- The three analytics above
- Self-contained HTML dashboard with charts and an exportable business table

**Out of scope for MVP**
- User accounts, billing, multi-tenancy
- Live/scheduled re-crawls (MVP is on-demand)
- Demographic or spend data joins
- Mobile app

**Explicit non-goal:** bypassing bot protection on any source.

---

## 8. Risks

| Risk | Severity | Mitigation |
|---|---|---|
| YP remains permanently inaccessible | High | Already mitigated — OSM is the default source; YP is optional |
| Overpass rate limits (429 observed) | Medium | Exponential backoff, on-disk response cache, chunked bbox queries |
| OSM coverage thinner than YP in regional areas | Medium | Metro-first go-to-market; adapter model allows adding sources |
| Sparse fields misread as "bad data" | Low | Reframed as the Digital Gap feature; coverage shown explicitly in UI |
| Privacy Act exposure on sole traders | Medium | Business-entity fields only; no personal names; no email harvesting |

---

## 9. Success Criteria (PoC)

1. Ingest ≥1,000 real Australian businesses from a live source in one run.
2. Produce all three analytics from that real data.
3. Render a dashboard from real — never mocked — output.
4. Demonstrate the adapter interface with a second source implemented.
5. Correctly detect and report the Yellow Pages block rather than failing silently.

---

## 10. Sources

- [Yellow Pages owner Sensis sold for $260M — Startup Daily](https://www.startupdaily.net/topic/asx/yellow-pages-owner-sensis-just-sold-for-260-million-to-a-nasdaq-listed-us-software-supplier/)
- [Sensis (company) — Wikipedia](https://en.wikipedia.org/wiki/Sensis_(company))
- [No copyright in White and Yellow Pages directories — MinterEllison](https://www.minterellison.com/articles/no-copyright-in-white-and-yellow-pages-directories-in-australia-telstras-appeal-fails)
- [Telstra v Phone Directories — Mondaq](https://www.mondaq.com/australia/copyright/94168/no-copyright-protection-for-telephone-directories--telstra-v-phone-directories-company)
- [Considering Legal Perspectives and an Australian Approach to Data Scraping (AustLII)](https://classic.austlii.edu.au/au/journals/ANZCompuLawJl/2017/3.pdf)
- [Maptitude Australia site selection](https://www.caliper.com/maptitude/sitelocation/site-selection-software-australia.htm)
- [Location intelligence for franchise expansion — Locus](https://www.locusintel.io/blog/best-location-intelligence-software-franchise-expansion)
- [Overpass API — OSM Wiki](https://wiki.openstreetmap.org/wiki/Overpass_API)
- [OSM Open Data License use cases](https://wiki.openstreetmap.org/wiki/Open_Data_License/Use_Cases)
- [OSMF API usage policy](https://operations.osmfoundation.org/policies/api/)
