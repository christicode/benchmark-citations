#!/usr/bin/env python3
"""Per-benchmark citation summary (data-quality lens). NO priority score.

Priority/ranking (usage x saturation-headroom x diversity) is a deferred project. This tool
just aggregates the citation graph so humans can sanity-check the INPUT DATA:
  - citations (raw count) and weighted points (blog_headliner 3 / model_card 2 / system_card 1),
    counted as MAX per (document, model) then summed across documents;
  - how many distinct citing labs / documents;
  - type (agentic|chat) + domain;
  - live Harbor status (already synced onto each record by sync_harbor.py);
  - whether any score has been extracted yet.

Reads data/citations.jsonl only. Live-fetches the Harbor registry solely to print its size.
"""
from __future__ import annotations
import json, sys, urllib.request, pathlib, collections

from scoring import points

ROOT = pathlib.Path(__file__).resolve().parents[1]
RAW = "https://raw.githubusercontent.com/harbor-framework/harbor/main/registry.json"


def harbor_size():
    try:
        with urllib.request.urlopen(RAW, timeout=30) as r:
            data = json.load(r)
        keys = {(d["name"], str(d.get("version"))) for d in data}
        print(f"# harbor: {len(data)} entries, {len(keys)} unique (name,version) [live:main]", file=sys.stderr)
    except Exception as e:
        print(f"# harbor live fetch failed ({e}); summary uses citation records only", file=sys.stderr)


def main() -> None:
    harbor_size()
    # collapse to MAX weight per (benchmark, document, model), then aggregate per benchmark
    per_doc = collections.defaultdict(int)          # (canon, doc_id, model) -> max weight
    meta = {}
    for line in open(ROOT / "data" / "citations.jsonl"):
        line = line.strip()
        if not line:
            continue
        c = json.loads(line)
        canon = c["benchmark_canonical"]
        if not canon:
            continue
        key = (canon, c["source_doc"].get("id"), c.get("citing_model"))
        per_doc[key] = max(per_doc[key], points(c.get("weight_class")))
        m = meta.setdefault(canon, {"labs": set(), "docs": set(), "solve": [],
                                    "type": "?", "domain": "?", "status": "not_in_harbor", "scored": False})
        m["labs"].add(c["citing_lab"]); m["docs"].add(c["source_doc"].get("id"))
        m["type"] = c.get("type") or m["type"]; m["domain"] = c.get("domain") or m["domain"]
        m["status"] = c.get("harbor_status", "not_in_harbor")
        rep = c.get("reported") or {}
        if isinstance(rep.get("value"), (int, float)):
            m["scored"] = True

    weighted = collections.Counter()
    cites = collections.Counter()
    for (canon, _doc, _model), w in per_doc.items():
        weighted[canon] += w
        cites[canon] += 1

    rows = sorted(meta, key=lambda c: (weighted[c], cites[c]), reverse=True)
    print(f"\n{'WEIGHT':>6} {'CITES':>5} {'LABS':>4} {'DOCS':>4} {'TYPE':8} {'DOMAIN':12} {'BENCHMARK':26} status")
    print("-" * 92)
    for c in rows:
        m = meta[c]
        print(f"{weighted[c]:6d} {cites[c]:5d} {len(m['labs']):4d} {len(m['docs']):4d} "
              f"{m['type']:8} {m['domain']:12} {c:26} {m['status']}")
    n_cand = sum(1 for c in meta if meta[c]["status"] == "not_in_harbor")
    print(f"\n# {len(meta)} benchmarks cited | {n_cand} not currently in Harbor "
          f"(candidates for future prioritization) | weight = blog_headliner 3 / model_card 2 / system_card 1")


if __name__ == "__main__":
    main()
