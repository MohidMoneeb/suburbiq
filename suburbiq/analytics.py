"""The three analytics that make this a product rather than a scraper dump."""
from typing import Dict, List, Sequence

# Suburbs with fewer than this many businesses are excluded from the
# Opportunity Index: with 1-2 records the mean gap score is noise, and a
# suburb with one café would otherwise rank as the biggest opportunity.
MIN_BUSINESSES_FOR_OPPORTUNITY = 5

# Shrinkage strength for the gap estimate. Without this, any small suburb whose
# handful of businesses all lack a website scores exactly 100, producing large
# ties at the top of the ranking and an arbitrary headline verdict. Pulling
# small-sample means toward the global mean makes the index discriminate on
# evidence rather than on sample size.
SHRINKAGE_K = 8


def coverage(rows: Sequence) -> Dict[str, object]:
    """Field-completeness stats (FR16). Low coverage is the product signal."""
    n = len(rows)
    if not n:
        return {"total": 0}
    have = lambda f: sum(1 for r in rows if (r[f] or "").strip())
    return {
        "total": n,
        "with_phone": have("phone"),
        "with_website": have("website"),
        "with_hours": have("opening_hours"),
        "with_street": have("street"),
        "pct_no_website": round(100 * (n - have("website")) / n),
        "pct_no_phone": round(100 * (n - have("phone")) / n),
        "avg_gap": round(sum(r["digital_gap_score"] for r in rows) / n),
        "suburbs": len({r["suburb"] for r in rows if r["suburb"]}),
    }


def saturation(rows: Sequence) -> List[Dict[str, object]]:
    """Business count per suburb (FR13)."""
    counts: Dict[str, int] = {}
    for r in rows:
        if r["suburb"]:
            counts[r["suburb"]] = counts.get(r["suburb"], 0) + 1
    return [{"suburb": s, "count": c}
            for s, c in sorted(counts.items(), key=lambda kv: -kv[1])]


def gap_histogram(rows: Sequence, buckets: int = 10) -> List[Dict[str, object]]:
    """Distribution of digital gap scores across deciles."""
    hist = [0] * buckets
    for r in rows:
        idx = min(int(r["digital_gap_score"] / (100 / buckets)), buckets - 1)
        hist[idx] += 1
    width = 100 // buckets
    return [{"lo": i * width, "hi": (i + 1) * width, "count": c}
            for i, c in enumerate(hist)]


def _normalise(values: Dict[str, float]) -> Dict[str, float]:
    """Scale a dict of values to 0..1. Flat input maps to 0.5, not a div-by-zero."""
    if not values:
        return {}
    lo, hi = min(values.values()), max(values.values())
    if hi == lo:
        return {k: 0.5 for k in values}
    return {k: (v - lo) / (hi - lo) for k, v in values.items()}


def opportunity(rows: Sequence) -> List[Dict[str, object]]:
    """Suburbs ranked by low supply + weak incumbent digital presence (FR15).

    Caveat (architecture §7): this is a supply-side proxy. It infers demand from
    the absence of competitors, which is directional, not a demand model.
    """
    agg: Dict[str, List[int]] = {}
    for r in rows:
        if r["suburb"]:
            agg.setdefault(r["suburb"], []).append(r["digital_gap_score"])

    eligible = {s: g for s, g in agg.items()
                if len(g) >= MIN_BUSINESSES_FOR_OPPORTUNITY}
    if not eligible:
        return []

    # Global mean gap across all scored businesses, used as the shrinkage prior.
    all_scores = [s for g in eligible.values() for s in g]
    prior = sum(all_scores) / len(all_scores)

    scarcity = {s: 1 / (1 + len(g)) for s, g in eligible.items()}
    # Shrunk mean: small samples are pulled toward the global mean, so a
    # 5-business suburb cannot outrank a 40-business one on noise alone.
    weakness = {s: (sum(g) + SHRINKAGE_K * prior) / (len(g) + SHRINKAGE_K)
                for s, g in eligible.items()}
    ns, nw = _normalise(scarcity), _normalise(weakness)

    out = []
    for s in eligible:
        score = 0.6 * ns[s] + 0.4 * nw[s]
        out.append({
            "suburb": s,
            "count": len(eligible[s]),
            "avg_gap": round(sum(eligible[s]) / len(eligible[s])),
            "raw": score,
        })
    # Tie-break on fewer competitors, then name, so ordering is deterministic.
    out.sort(key=lambda d: (-d["raw"], d["count"], d["suburb"]))

    # Rescale to a readable 0-100 across the ranked set.
    top = out[0]["raw"] or 1
    for d in out:
        d["index"] = round(100 * d["raw"] / top)
        del d["raw"]
    return out


def leads(rows: Sequence, limit: int = 0) -> List[Dict[str, object]]:
    """Businesses ranked by digital gap — Priya's prospect list (FR14/FR19)."""
    ranked = sorted(rows, key=lambda r: (-r["digital_gap_score"], r["name"]))
    if limit:
        ranked = ranked[:limit]
    return [{
        "name": r["name"], "suburb": r["suburb"], "phone": r["phone"],
        "website": r["website"], "opening_hours": r["opening_hours"],
        "street": r["street"], "gap": r["digital_gap_score"],
    } for r in ranked]
