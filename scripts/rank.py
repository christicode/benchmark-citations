#!/usr/bin/env python3
"""Priority ranking for 'convert this benchmark to Harbor next'.

Inputs:
  - data/citations.jsonl   (benchmark-first citation records)
  - data/aliases.yaml      (canonical names + Harbor match status)
  - Harbor registry.json   (fetched LIVE from main each run; dedupe by (name,version))

Score axes (agentic/static kept SEPARATE, per spec — surfaced, not folded in):
  usage    = prominence-weighted citation volume * lab-diversity multiplier
  headroom = saturation headroom (lower max reported solve rate => longer half-life)
Excludes benchmarks already in Harbor (harbor_status: confirmed); down-ranks needs_review.
"""
from __future__ import annotations
import json, sys, urllib.request, pathlib, collections
try:
    import yaml
except ImportError:
    sys.exit("pip install pyyaml")

ROOT = pathlib.Path(__file__).resolve().parents[1]
RAW = "https://raw.githubusercontent.com/harbor-framework/harbor/main/registry.json"
PROMINENCE_W = {"headline": 3.0, "table_row": 1.0, "footnote": 0.5, "prose": 0.5}


def load_harbor() -> set[tuple[str, str]]:
    """Fetch live; fall back to local cache. Dedupe by (name, version)."""
    try:
        with urllib.request.urlopen(RAW, timeout=30) as r:
            data = json.load(r)
        src = "live:main"
    except Exception as e:
        cache = ROOT.parent / "harbor_registry.json"
        data = json.load(open(cache)); src = f"cache:{cache} ({e})"
    keys = {(d["name"], str(d.get("version"))) for d in data}
    print(f"# harbor registry: {len(data)} entries, {len(keys)} unique (name,version) [{src}]", file=sys.stderr)
    return keys


def main() -> None:
    aliases = yaml.safe_load(open(ROOT / "data" / "aliases.yaml"))
    by_canon = {b["canonical"]: b for b in aliases["benchmarks"]}
    load_harbor()  # validates live fetch + dedupe; exclusion uses harbor_status in aliases.yaml

    agg: dict[str, dict] = collections.defaultdict(
        lambda: {"usage": 0.0, "labs": set(), "solve": [], "docs": 0})
    for line in open(ROOT / "data" / "citations.jsonl"):
        line = line.strip()
        if not line:
            continue
        c = json.loads(line)
        canon = c["benchmark_canonical"]
        if not canon:
            continue  # unmatched -> handled by review queue, not ranked
        a = agg[canon]
        a["usage"] += PROMINENCE_W.get(c["prominence"]["type"], 0.5)
        a["labs"].add(c["citing_lab"]); a["docs"] += 1
        rep = c.get("reported") or {}
        if rep.get("unit") == "percent" and isinstance(rep.get("value"), (int, float)):
            a["solve"].append(rep["value"] / 100.0)

    rows = []
    for canon, a in agg.items():
        meta = by_canon.get(canon, {})
        status = meta.get("harbor_status", "not_in_harbor")
        if status == "confirmed":
            continue  # already in Harbor -> exclude
        diversity = 1 + 0.5 * (len(a["labs"]) - 1)
        usage = a["usage"] * diversity
        headroom = (1 - max(a["solve"])) if a["solve"] else 0.5  # unknown ceiling -> neutral
        penalty = 0.6 if status == "needs_review" else (0.3 if meta.get("vendor_proprietary") else 1.0)
        priority = (usage * 0.6 + headroom * 4 * 0.4) * penalty
        rows.append((priority, canon, meta.get("axis", "?"), usage, headroom,
                     len(a["labs"]), a["docs"], status))

    rows.sort(reverse=True)
    print(f"\n{'PRIORITY':>8}  {'AXIS':7} {'BENCHMARK':22} {'usage':>6} {'headroom':>8} {'labs':>4} {'docs':>4}  status")
    print("-" * 88)
    for pr, canon, axis, usage, hr, labs, docs, status in rows:
        print(f"{pr:8.2f}  {axis:7} {canon:22} {usage:6.1f} {hr:8.2f} {labs:4d} {docs:4d}  {status}")


if __name__ == "__main__":
    main()
