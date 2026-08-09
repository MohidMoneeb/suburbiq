"""SuburbIQ CLI: ingest · report · export · stats."""
import argparse
import os
import sys
from datetime import datetime, timezone

from . import report, store
from .models import AREAS, CATEGORIES, SourceBlocked
from .normalise import SuburbResolver, normalise
from .sources.osm import OSMAdapter, fetch_suburb_centroids
from .sources.yellowpages import YellowPagesAdapter

from .paths import OUT_DIR

ADAPTERS = {"osm": OSMAdapter, "yellowpages": YellowPagesAdapter}


def _adapter(name: str):
    if name not in ADAPTERS:
        sys.exit(f"unknown source '{name}'. known: {', '.join(ADAPTERS)}")
    return ADAPTERS[name]()


def cmd_ingest(args) -> int:
    area = AREAS.get(args.area)
    if not area:
        sys.exit(f"unknown area '{args.area}'. known: {', '.join(AREAS)}")

    adapter = _adapter(args.source)
    print(f"\n[ingest] source={adapter.name} category={args.category} area={area.label}")

    try:
        records = list(adapter.fetch(args.category, area))
    except SourceBlocked as exc:
        print(f"\n  ✗ SOURCE BLOCKED — {exc.source} returned HTTP {exc.status}")
        print(f"    {exc.detail}")
        print(f"\n    {exc.remediation}\n")
        return 2
    except RuntimeError as exc:
        # Retries exhausted (typically sustained Overpass throttling). Report it
        # as an outcome rather than a traceback, and leave the db untouched.
        print(f"\n  ✗ SOURCE UNAVAILABLE — {exc}")
        print("    The source is throttling. Wait a few minutes and re-run; "
              "completed categories already in the database are unaffected.\n")
        return 3

    print(f"  fetched {len(records)} raw records")

    centroids = []
    if any(r.fields.get("lat") is not None for r in records):
        print("  fetching suburb centroids for derivation...")
        try:
            centroids = fetch_suburb_centroids(area)
            print(f"  loaded {len(centroids)} suburb centroids")
        except Exception as exc:  # non-fatal: source suburbs still work
            print(f"  ! centroid fetch failed ({exc}); relying on source suburbs only")

    businesses, dropped = normalise(records, args.category, SuburbResolver(centroids))
    print(f"  normalised {len(businesses)} businesses "
          f"(dropped: {dropped['no_name']} unnamed, {dropped['no_suburb']} no-suburb, "
          f"{dropped['duplicate']} duplicates)")

    conn = store.connect()
    result = store.upsert(conn, businesses)
    print(f"  stored: {result['inserted']} new, {result['updated']} updated, "
          f"{result['total']} total rows in db")
    return 0


def _load(args):
    conn = store.connect()
    rows = store.query(conn, args.category, args.source if args.source != "any" else "")
    if not rows:
        sys.exit(f"no data for category '{args.category}'. Run ingest first.")
    return rows


def cmd_report(args) -> int:
    rows = _load(args)
    os.makedirs(OUT_DIR, exist_ok=True)
    area = AREAS.get(args.area)
    src = rows[0]["source"]
    licence = ADAPTERS[src]().licence if src in ADAPTERS else ""
    generated = max(r["ingested_at"] or "" for r in rows) or \
        datetime.now(timezone.utc).isoformat(timespec="seconds")

    html_doc = report.render_html(
        rows, category=args.category,
        area_label=area.label if area else args.area,
        source=src, licence=licence, generated=generated,
    )
    path = os.path.abspath(os.path.join(OUT_DIR, args.out))
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(html_doc)
    report.write_json(rows, os.path.join(OUT_DIR, "analytics.json"))
    print(f"\n  dashboard → {path}\n  ({len(rows):,} businesses)")
    return 0


def cmd_export(args) -> int:
    rows = _load(args)
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.abspath(os.path.join(OUT_DIR, args.out))
    n = report.write_csv(rows, path)
    print(f"  exported {n:,} leads → {path}")
    return 0


def cmd_stats(args) -> int:
    conn = store.connect()
    rows = store.categories(conn)
    if not rows:
        print("  database is empty")
        return 0
    print(f"\n  {'category':<14}{'source':<14}{'rows':>7}   last ingest")
    print("  " + "-" * 58)
    for r in rows:
        print(f"  {r['category']:<14}{r['source']:<14}{r['n']:>7}   {r['last']}")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="suburbiq",
                                description="Suburb-level market intelligence for Australian local business.")
    sub = p.add_subparsers(dest="cmd", required=True)

    ing = sub.add_parser("ingest", help="fetch and store businesses")
    ing.add_argument("--source", default="osm", choices=list(ADAPTERS))
    ing.add_argument("--category", required=True, choices=sorted(CATEGORIES))
    ing.add_argument("--area", default="sydney", choices=sorted(AREAS))
    ing.set_defaults(fn=cmd_ingest)

    rep = sub.add_parser("report", help="render the HTML dashboard")
    rep.add_argument("--category", required=True)
    rep.add_argument("--area", default="sydney")
    rep.add_argument("--source", default="any")
    rep.add_argument("--out", default="dashboard.html")
    rep.set_defaults(fn=cmd_report)

    exp = sub.add_parser("export", help="export ranked leads as CSV")
    exp.add_argument("--category", required=True)
    exp.add_argument("--area", default="sydney")
    exp.add_argument("--source", default="any")
    exp.add_argument("--out", default="leads.csv")
    exp.set_defaults(fn=cmd_export)

    st = sub.add_parser("stats", help="what is in the database")
    st.set_defaults(fn=cmd_stats)

    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
