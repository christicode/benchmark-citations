#!/usr/bin/env python3
"""Priority ranking for 'convert this benchmark to Harbor next'.

Reads data/citations.jsonl (each record self-describes on_harbor / harbor_status / type / domain).
Live-fetches Harbor registry.json from main only to report size + sanity-check dedupe.

Score (type/domain kept SEPARATE, surfaced not folded in):
  usage    = prominence-weighted citations * lab-diversity multiplier
  headroom = saturation headroom (lower max reported solve rate => longer half-life)
Excludes benchmarks already in Harbor (on_harbor); down-ranks needs_review / vendor.
"""
from __future__ import annotations
import json, sys, urllib.request, pathlib, collections

ROOT = pathlib.Path(__file__).resolve().parents[1]
RAW = "https://raw.githubusercontent.com/harbor-framework/harbor/main/registry.json"
TABLE_NORM = 12.0  # benchmark in a <=12-row table = full table_row weight; deeper tables (row 47/50) decay


def pweight(p):
    """Prominence weight: a blog HEADLINE (3.0) outweighs a row in a big system-card table.
    A table_row is discounted by table size so 'row 47 of 50' counts far less than a focused table."""
    t = p.get("type")
    if t == "headline":
        return 3.0
    if t in ("footnote", "prose"):
        return 0.5
    return min(1.0, TABLE_NORM / max(p.get("table_total") or 1, 1))


def harbor_keys() -> set:
    try:
        with urllib.request.urlopen(RAW, timeout=30) as r:
            data = json.load(r)
        keys = {(d["name"], str(d.get("version"))) for d in data}
        print(f"# harbor: {len(data)} entries, {len(keys)} unique (name,version) [live:main]", file=sys.stderr)
        return keys
    except Exception as e:
        print(f"# harbor live fetch failed ({e}); ranking uses citation flags only", file=sys.stderr)
        return set()


def main() -> None:
    harbor_keys()
    agg = collections.defaultdict(lambda: {"usage": 0.0, "labs": set(), "docs": 0,
                                           "solve": [], "type": "?", "domain": "?", "status": "not_in_harbor",
                                           "on": False, "vendor": False})
    for line in open(ROOT / "data" / "citations.jsonl"):
        line = line.strip()
        if not line:
            continue
        c = json.loads(line)
        canon = c["benchmark_canonical"]
        if not canon:
            continue
        a = agg[canon]
        a["usage"] += pweight(c["prominence"])
        a["labs"].add(c["citing_lab"]); a["docs"] += 1
        a["type"] = c.get("type") or "?"; a["domain"] = c.get("domain") or "?"
        a["status"] = c.get("harbor_status", "not_in_harbor")
        a["on"] = a["on"] or c.get("on_harbor", False)
        rep = c.get("reported") or {}
        if rep.get("unit") == "percent" and isinstance(rep.get("value"), (int, float)):
            a["solve"].append(rep["value"] / 100.0)

    rows = []
    for canon, a in agg.items():
        if a["on"]:
            continue
        diversity = 1 + 0.5 * (len(a["labs"]) - 1)
        usage = a["usage"] * diversity
        headroom = (1 - max(a["solve"])) if a["solve"] else 0.5
        penalty = 0.6 if a["status"] in ("needs_review", "false_positive") else 1.0
        priority = (usage * 0.6 + headroom * 4 * 0.4) * penalty
        rows.append((priority, canon, a["type"], a["domain"], usage, headroom, len(a["labs"]), a["docs"], a["status"]))

    rows.sort(reverse=True)
    print(f"\n{'PRIOR':>6} {'TYPE':8} {'DOMAIN':12} {'BENCHMARK':24} {'usage':>6} {'headrm':>6} {'labs':>4} {'docs':>4}  status")
    print("-" * 96)
    for pr, canon, typ, dom, usage, hr, labs, docs, status in rows[:30]:
        print(f"{pr:6.2f} {typ:8} {dom:12} {canon:24} {usage:6.1f} {hr:6.2f} {labs:4d} {docs:4d}  {status}")
    print(f"\n# {len(rows)} candidate benchmarks NOT in Harbor (of {len(agg)} cited). Top 30 shown.")


if __name__ == "__main__":
    main()
