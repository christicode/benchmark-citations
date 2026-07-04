#!/usr/bin/env python3
"""Regenerate data/aliases_generated.yaml from data/citations.jsonl (auto-registered canonicals).

The curated core + collision flags live in aliases.yaml (hand-maintained). This file
holds every canonical seen in the citation graph so extract.py can normalize them.
Each canonical carries its two orthogonal axes: type (agentic|static) and domain.
"""
import json, collections, pathlib
ROOT = pathlib.Path(__file__).resolve().parents[1]
agg = collections.defaultdict(lambda: {"raws": set(), "type": None, "domain": None,
                                        "hs": "not_in_harbor", "hn": None})
for line in open(ROOT / "data" / "citations.jsonl"):
    line = line.strip()
    if not line:
        continue
    c = json.loads(line)
    canon = c["benchmark_canonical"]
    if not canon:
        continue
    a = agg[canon]
    a["raws"].add(c["benchmark_raw"])
    a["type"] = c.get("type") or a["type"]
    a["domain"] = c.get("domain") or a["domain"]
    a["hs"] = c.get("harbor_status", "not_in_harbor"); a["hn"] = c.get("harbor_name")
out = ["# aliases_generated.yaml - AUTO-GENERATED from citations.jsonl. DO NOT EDIT.",
       "# Curated core + collision flags live in aliases.yaml.",
       "# type = agentic|static (Harbor prefers agentic); domain = subject (kept orthogonal).",
       "schema_version: 2", "benchmarks:"]
for c, v in sorted(agg.items()):
    out.append(f"  - canonical: {c}")
    out.append(f"    type: {v['type']}")
    out.append(f"    domain: {v['domain']}")
    out.append("    aliases: [" + ", ".join('"' + x + '"' for x in sorted(v["raws"])) + "]")
    out.append(f"    harbor_status: {v['hs']}")
    if v["hn"]:
        out.append(f"    harbor_match: {{name: {v['hn']}}}")
(ROOT / "data" / "aliases_generated.yaml").write_text("\n".join(out) + "\n")
print("wrote aliases_generated.yaml:", len(agg), "canonicals")
