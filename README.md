# SuburbIQ

Live Website @ https://suburbiq-jpjo.onrender.com/

**Find the Australian suburbs where a local business would actually have room to breathe.**

Pick a category and a city. SuburbIQ tells you where the competition is thin, and hands you a
list of the businesses already there that barely exist online.

![status](https://img.shields.io/badge/tests-31%20passing-brightgreen)
![python](https://img.shields.io/badge/python-3.9%2B-blue)
![licence](https://img.shields.io/badge/data-ODbL-lightgrey)

---

## The story behind it

This started as "scrape Yellow Pages Australia and chart the results."

That plan died about ten minutes in. Yellow Pages sits behind Cloudflare and returns
`403` to anything automated — including `/robots.txt` itself, so you can't even read the
site's own rules about crawling it.

I could have gone down the proxy-rotation rabbit hole. I didn't, for two reasons. One,
working around someone's bot protection is a fight you re-fight every week. Two, a product
whose entire data supply can be switched off by a single firewall rule isn't a product.

So the data source became a **swappable adapter**, and the default is OpenStreetMap —
open, ODbL-licensed, genuinely redistributable. The Yellow Pages adapter is still in here,
built against the real page structure. It just tells you honestly when it's been blocked
instead of pretending it returned nothing:

```
✗ SOURCE BLOCKED — yellowpages returned HTTP 403
  bot protection detected (marker: 'attention required')
```

The interesting legal wrinkle: in *Telstra v Phone Directories* [2010] FCA 44 the Federal
Court held there's **no copyright** in the Yellow/White Pages listings — Australia has no
database right, and "sweat of the brow" isn't enough. So the facts were never the problem.
The locked front door was.

## The part that turned out to matter

The first real scrape came back looking broken. Of 2,625 Sydney cafés:

- **78%** had no website
- **87%** had no phone number listed

I nearly went hunting for a better data source. Then it clicked — that *is* the product.
A digital agency doesn't want a tidy directory. It wants the 2,051 businesses with no
website and a way to rank them. Sparse data was the signal, not the noise.

That became the **Digital Gap Score** (0–100, weighted by what's missing), and everything
else grew around it.

## What you get

**Opportunity Index** — suburbs ranked by "few competitors, and the ones there are weak online."

**Saturation** — how crowded each suburb already is.

**Digital Gap Score** — per business, ranked and exportable to CSV. This is the sales list.

Click any suburb on a chart to filter the table to it.

## Running it

```bash
pip install -r requirements.txt
```

Grab some data (a few minutes on a cold cache — Overpass throttles, so it backs off politely):

```bash
python -m suburbiq.cli ingest --source osm --category cafe --area sydney
```

Start the app at http://localhost:8000:

```bash
python -m uvicorn suburbiq.api:app --reload
```

Or skip the web app entirely and get a standalone HTML report:

```bash
python -m suburbiq.cli report --category cafe --area sydney
```

## Putting it online

There's a `render.yaml` in the repo, so deploying is mostly clicking:

1. Go to [render.com](https://render.com) and sign in with GitHub
2. **New → Blueprint**, pick this repo, **Apply**

A few minutes later you have a public `https://…onrender.com` URL. The blueprint sets
`HOST=0.0.0.0` for you, and the free plan doesn't ask for a card.

It won't come up empty: `seed/suburbiq-seed.db` holds a real Sydney ingest (2,625 cafés)
and is restored on first boot if no database exists yet.

Two things to know about the free tier:

- **It sleeps after ~15 minutes idle**, so the first request after that takes ~30–50s to wake.
- **Disk is ephemeral.** Anything scraped from the live site vanishes on the next restart
  and it falls back to the seed. Fine for a demo — for anything real, move to Postgres,
  which is the v1.2 plan in [the architecture doc](docs/architecture.md).

Any host that injects `PORT` works the same way; the start command is `python serve.py`.

**Categories:** cafe, restaurant, plumber, electrician, hairdresser, gym, dentist, bakery, childcare, veterinary
**Areas:** sydney, melbourne, brisbane, perth, adelaide

## Tests

```bash
python -m unittest discover -s tests
```

31 tests, no network required.

## How it fits together

```
adapters (osm / yellowpages)  ->  normalise  ->  SQLite  ->  analytics  ->  API + web
```

The adapter boundary is the whole point. Adding TrueLocal or Google Places is one new file,
not a refactor.

A few things worth knowing:

- **Suburbs are derived, not read.** Only 13% of records carry `addr:suburb`, so the rest
  get assigned by nearest suburb centroid. (Australian suburbs are `place=suburb` nodes in
  OSM, not `admin_level=10` boundaries — that one cost me an afternoon and 2,291 dropped rows.)
- **Re-ingesting updates rather than duplicates.** Stable hash primary key, upsert on conflict.
- **The Opportunity Index is a supply-side proxy.** It infers demand from the *absence* of
  competitors, which is directional, not gospel. Real demand modelling needs ABS population
  and income data — that's the next thing on the list, not something I'm going to pretend
  is already here.

## Docs

Built with the BMAD method, so the thinking is all written down:

| | |
|---|---|
| [Brief](docs/brief.md) | Market research, the legal analysis, feasibility evidence |
| [PRD](docs/prd.md) | Personas, requirements, epics |
| [UX spec](docs/ux-spec.md) | Information architecture and visual language |
| [Architecture](docs/architecture.md) | Why the adapter seam exists, data model, algorithms |

## Attribution

Business data © OpenStreetMap contributors, licensed under
[ODbL](https://opendatacommons.org/licenses/odbl/).

SuburbIQ does not circumvent bot protection on any source, by design.
