"""Renders the single-file HTML dashboard and CSV export.

No CDN, no build step, no server: the output must open offline (NFR3).
Charts are inline SVG/divs rather than a chart library for the same reason.
"""
import csv
import html
import json
from typing import Dict, List, Sequence

from . import analytics

CSS = """
:root{--accent:#f4b41a;--ink:#12141a;--muted:#6b7280;--surface:#fff;--bg:#f6f7f9;
--line:#e5e7eb;--pos:#16a34a;--warn:#dc2626;}
@media (prefers-color-scheme:dark){:root{--ink:#e8eaed;--muted:#9aa1ab;--surface:#171a21;
--bg:#0e1015;--line:#262b35;}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 -apple-system,
BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;font-variant-numeric:tabular-nums;}
.wrap{max-width:1120px;margin:0 auto;padding:28px 20px 64px}
header h1{margin:0 0 4px;font-size:26px;letter-spacing:-.02em}
header h1 span{color:var(--accent)}
.meta{color:var(--muted);font-size:13px}
.card{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:18px 20px}
.verdict{margin:22px 0 18px;border-left:4px solid var(--accent)}
.verdict .lead{font-size:19px;font-weight:600;letter-spacing:-.01em}
.verdict .lead em{color:var(--accent);font-style:normal}
.verdict p{margin:8px 0 0;color:var(--muted);font-size:14px}
.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:26px}
.kpi .n{font-size:28px;font-weight:700;letter-spacing:-.02em}
.kpi .l{font-size:11px;text-transform:uppercase;letter-spacing:.07em;color:var(--muted);margin-top:2px}
.kpi .c{font-size:12px;color:var(--muted);margin-top:5px}
h2{font-size:14px;text-transform:uppercase;letter-spacing:.07em;color:var(--muted);margin:0 0 14px}
.cols{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:16px}
.row{display:grid;grid-template-columns:150px 1fr 52px;align-items:center;gap:10px;
margin-bottom:9px;font-size:14px}
.row span:first-child{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.track{background:var(--line);border-radius:5px;height:12px;overflow:hidden}
.fill{height:100%;background:var(--accent);border-radius:5px}
.fill.mut{background:var(--muted);opacity:.55}
.val{text-align:right;font-size:13px;color:var(--muted)}
.tablewrap{overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:13.5px;margin-top:6px}
th{text-align:left;font-size:11px;text-transform:uppercase;letter-spacing:.06em;
color:var(--muted);border-bottom:1px solid var(--line);padding:7px 8px;white-space:nowrap}
td{padding:8px;border-bottom:1px solid var(--line)}
.none{color:var(--muted)}
.pill{display:inline-block;min-width:34px;text-align:center;padding:2px 7px;
border-radius:999px;font-size:12px;font-weight:600}
.hi{background:rgba(220,38,38,.14);color:var(--warn)}
.md{background:rgba(244,180,26,.18);color:#a97a06}
.lo{background:rgba(22,163,74,.14);color:var(--pos)}
@media (prefers-color-scheme:dark){.md{color:var(--accent)}}
input{width:100%;padding:9px 11px;border:1px solid var(--line);border-radius:8px;
background:var(--bg);color:var(--ink);margin-bottom:10px;font-size:14px}
footer{margin-top:32px;color:var(--muted);font-size:12px;line-height:1.7}
@media(max-width:999px){.kpis{grid-template-columns:repeat(2,1fr)}.cols{grid-template-columns:1fr}}
@media(max-width:639px){.kpis{grid-template-columns:1fr}.row{grid-template-columns:100px 1fr 46px}}
"""

JS = """
const q=document.getElementById('flt');
if(q){q.addEventListener('input',e=>{
  const v=e.target.value.toLowerCase();
  document.querySelectorAll('#leads tbody tr').forEach(tr=>{
    tr.style.display=tr.dataset.k.includes(v)?'':'none';});
});}
"""


def _e(s) -> str:
    return html.escape(str(s if s is not None else ""))


def _cell(v: str) -> str:
    return _e(v) if (v or "").strip() else '<span class="none">—</span>'


def _pill(score: int) -> str:
    cls = "hi" if score >= 60 else ("md" if score >= 30 else "lo")
    return f'<span class="pill {cls}">{score}</span>'


def _bars(items: List[Dict], label_key: str, value_key: str) -> str:
    if not items:
        return '<p class="meta">No data.</p>'
    top = max(i[value_key] for i in items) or 1
    out = []
    for n, it in enumerate(items):
        pct = 100 * it[value_key] / top
        cls = "fill" if n == 0 else "fill mut"
        out.append(
            f'<div class="row"><span title="{_e(it[label_key])}">{_e(it[label_key])}</span>'
            f'<div class="track"><div class="{cls}" style="width:{pct:.1f}%"></div></div>'
            f'<span class="val">{it[value_key]}</span></div>'
        )
    return "".join(out)


def _histogram(hist: List[Dict]) -> str:
    top = max((h["count"] for h in hist), default=1) or 1
    w, gap, h_max = 26, 9, 118
    bars = []
    for i, b in enumerate(hist):
        bh = max(2, h_max * b["count"] / top)
        x = 8 + i * (w + gap)
        colour = "#f4b41a" if b["lo"] >= 50 else "#6b7280"
        op = "1" if b["lo"] >= 50 else ".5"
        bars.append(
            f'<rect x="{x}" y="{130 - bh:.1f}" width="{w}" height="{bh:.1f}" '
            f'fill="{colour}" opacity="{op}"><title>gap {b["lo"]}-{b["hi"]}: '
            f'{b["count"]} businesses</title></rect>'
        )
    return (f'<svg viewBox="0 0 {8 + len(hist) * (w + gap)} 150" width="100%" height="150" role="img">'
            f'<title>Digital gap score distribution</title>{"".join(bars)}'
            f'<line x1="4" y1="131" x2="{4 + len(hist) * (w + gap)}" y2="131" '
            f'stroke="#6b7280" stroke-width="1" opacity=".4"/></svg>')


def render_html(rows: Sequence, *, category: str, area_label: str,
                source: str, licence: str, generated: str,
                table_limit: int = 100) -> str:
    cov = analytics.coverage(rows)
    sat = analytics.saturation(rows)
    opp = analytics.opportunity(rows)
    hist = analytics.gap_histogram(rows)
    lead_rows = analytics.leads(rows, limit=table_limit)
    total_leads = len(rows)

    if opp:
        top = opp[0]
        verdict = (f'<div class="lead">Best opportunity: <em>{_e(top["suburb"])}</em> — '
                   f'{top["count"]} {_e(category)} businesses, average digital gap '
                   f'{top["avg_gap"]}/100.</div>'
                   f'<p>Few incumbents, and those present are weakly represented online. '
                   f'Ranked 1st of {len(opp)} suburbs on the Opportunity Index.</p>')
    else:
        verdict = ('<div class="lead">Not enough data to rank suburbs.</div>'
                   '<p>No suburb met the minimum business count for the Opportunity Index.</p>')

    trs = []
    for L in lead_rows:
        key = f'{L["name"]} {L["suburb"]}'.lower()
        trs.append(
            f'<tr data-k="{_e(key)}"><td>{_e(L["name"])}</td><td>{_e(L["suburb"])}</td>'
            f'<td>{_cell(L["phone"])}</td><td>{_cell(L["website"])}</td>'
            f'<td>{_cell(L["opening_hours"])}</td><td>{_pill(L["gap"])}</td></tr>'
        )

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>SuburbIQ — {_e(category)} in {_e(area_label)}</title>
<style>{CSS}</style></head><body><div class="wrap">

<header><h1>Suburb<span>IQ</span></h1>
<div class="meta">{_e(category.title())} · {_e(area_label)} · ingested {_e(generated)} · source: {_e(source)}</div>
</header>

<div class="card verdict">{verdict}</div>

<section class="kpis">
  <div class="card kpi"><div class="n">{cov.get('total',0):,}</div><div class="l">Businesses</div>
    <div class="c">across {cov.get('suburbs',0)} suburbs</div></div>
  <div class="card kpi"><div class="n">{cov.get('avg_gap',0)}</div><div class="l">Avg digital gap</div>
    <div class="c">0 = complete, 100 = absent</div></div>
  <div class="card kpi"><div class="n">{cov.get('pct_no_website',0)}%</div><div class="l">No website</div>
    <div class="c">{cov.get('total',0)-cov.get('with_website',0):,} businesses</div></div>
  <div class="card kpi"><div class="n">{cov.get('pct_no_phone',0)}%</div><div class="l">No phone listed</div>
    <div class="c">{cov.get('total',0)-cov.get('with_phone',0):,} businesses</div></div>
</section>

<div class="card"><h2>Opportunity Index — best suburbs to enter</h2>
{_bars(opp[:12], 'suburb', 'index')}
<div class="meta" style="margin-top:10px">Supply-side proxy: combines low competitor
count (60%) with weak incumbent digital presence (40%). Suburbs with fewer than
{analytics.MIN_BUSINESSES_FOR_OPPORTUNITY} businesses are excluded.</div></div>

<div class="cols">
  <div class="card"><h2>Saturation — {_e(category)} per suburb</h2>
  {_bars(sat[:12], 'suburb', 'count')}</div>
  <div class="card"><h2>Digital gap distribution</h2>
  {_histogram(hist)}
  <div class="meta">Amber = gap ≥ 50 (agency target zone)</div></div>
</div>

<div class="card" style="margin-top:16px"><h2>Leads — ranked by digital gap</h2>
<input id="flt" placeholder="Filter by business or suburb…">
<div class="tablewrap"><table id="leads">
<thead><tr><th scope="col">Business</th><th scope="col">Suburb</th><th scope="col">Phone</th>
<th scope="col">Website</th><th scope="col">Hours</th><th scope="col">Gap</th></tr></thead>
<tbody>{''.join(trs)}</tbody></table></div>
<div class="meta" style="margin-top:10px">Showing {len(lead_rows):,} of {total_leads:,};
full set available via <code>export</code>.</div></div>

<footer>
<strong>Provenance:</strong> {_e(source)} · ingested {_e(generated)} · {cov.get('total',0):,} records<br>
{_e(licence)}<br>
Field coverage — phone {cov.get('with_phone',0):,} · website {cov.get('with_website',0):,} ·
hours {cov.get('with_hours',0):,} · street {cov.get('with_street',0):,}
</footer>

</div><script>{JS}</script></body></html>"""


def write_csv(rows: Sequence, path: str) -> int:
    lead_rows = analytics.leads(rows)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["name", "suburb", "street", "phone",
                                           "website", "opening_hours", "gap"])
        w.writeheader()
        w.writerows(lead_rows)
    return len(lead_rows)


def write_json(rows: Sequence, path: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({
            "coverage": analytics.coverage(rows),
            "saturation": analytics.saturation(rows),
            "opportunity": analytics.opportunity(rows),
        }, fh, indent=2)
