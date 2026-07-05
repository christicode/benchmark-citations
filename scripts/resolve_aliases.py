#!/usr/bin/env python3
"""Resolve still-unmatched citations against the curated alias registry (data/aliases.yaml).

Root-cause fix: build_citations.canon() matches raw benchmark names via a dict hardcoded in
build_citations.py, and a code edit (commit ec2024a) silently deleted 29 alias entries -- so
29 real benchmarks (incl. scicode/bixbench/aa-lcr/widesearch, which have Harbor adapters)
reverted to "unmatched -> needs_review (register in aliases)" and vanished from the dashboard,
even though data/aliases.yaml -- the curated registry AGENTS.md calls the source of truth --
already listed them.

This step makes aliases.yaml authoritative for IDENTITY: after build_citations, any record
still unmatched whose raw name equals an alias in aliases.yaml is resolved deterministically to
its canonical (+ type from the registry's `axis`), and its "register in aliases" review flag is
cleared. Genuinely novel names (not in aliases.yaml) stay unmatched -- the only residual human
gate, surfaced in the change log. Because identity lives in a data file, a future code edit can't
un-register a benchmark; onboarding an alias is a data edit, not a code change.

domain is a separate classification axis that already lives in code (build_citations.domain_of);
the 29 names ec2024a dropped are restored here from DOMAIN (a small, explicit restoration table).
Migrating all domains into aliases.yaml would let this table go away -- a clean follow-up.

Pipeline: build_citations.py -> resolve_aliases.py -> sync_harbor.py -> gen_aliases.py -> build_dashboard.py
Matching is exact/normalized (punctuation-insensitive whole-string), never fuzzy.
"""
from __future__ import annotations
import datetime
import json
import pathlib
import re
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
ALIASES = ROOT / "data" / "aliases.yaml"
CITES = ROOT / "data" / "citations.jsonl"
CHANGELOG = ROOT / "data" / "changelog.jsonl"

UNMATCHED_REASON = "unmatched benchmark name - register in aliases"

# domain per canonical for names not in build_citations.domain_of() (the 29 issue-#8 names it
# dropped). Mirrors build_citations.DOMAIN buckets. Unlisted canonicals fall back to "knowledge"
# (same default as domain_of), so a genuinely new alias still resolves, just domain-defaulted.
DOMAIN = {
    "coding": ["expert-swe", "frontierbench", "mle-bench", "ojbench", "webdev-arena"],
    "math": ["frontiermath"],
    "science": ["biopipelinebench", "bixbench", "frontier-science-research", "genebench", "scicode"],
    "knowledge": ["aa-lcr", "chinese-simpleqa", "corpusqa", "ifbench", "supergpqa", "widesearch"],
    "cyber": ["exploitgym"],
    "computer-use": ["mcpmark", "online-mind2web"],
    "professional": ["apex-agents", "biglaw-bench", "gdpval-gold"],
    "multimodal": ["babyvision", "longvideobench", "mathvision", "omnidocbench", "worldvqa", "zerobench"],
}
DOMAIN_OF = {c: d for d, cs in DOMAIN.items() for c in cs}


def norm(s):
    """lowercase; collapse non-alphanumeric runs to one space (punctuation-insensitive)."""
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def load_alias_map():
    """norm(alias) -> (canonical, type) from the curated registry. Whole-string exact match."""
    reg = yaml.safe_load(ALIASES.read_text()) or {}
    amap, collisions = {}, []
    for b in reg.get("benchmarks", []):
        canon = b.get("canonical")
        if not canon:
            continue
        typ = "agentic" if b.get("axis") == "agentic" else "chat"   # static/safety -> chat
        keys = {norm(canon)} | {norm(a) for a in (b.get("aliases") or [])}
        for k in keys:
            if not k:
                continue
            if k in amap and amap[k][0] != canon:
                collisions.append((k, amap[k][0], canon))   # never silently pick one
                continue
            amap[k] = (canon, typ)
    if collisions:
        for k, a, c in collisions:
            print(f"alias collision: {k!r} -> {a} vs {c} (skipped)", file=sys.stderr)
    return amap


def main():
    amap = load_alias_map()
    rows = [json.loads(l) for l in open(CITES) if l.strip()]

    resolved, still_unmatched = [], set()
    for r in rows:
        if r.get("benchmark_canonical"):
            continue
        # only touch records left unmatched by build_citations (raw name had no alias);
        # never image/chart/gated placeholders (those carry a different review_reason).
        if r.get("review_reason") != UNMATCHED_REASON:
            continue
        raw = r.get("benchmark_raw")
        hit = amap.get(norm(raw))
        if not hit:
            still_unmatched.add(raw)
            continue
        canon, typ = hit
        r["benchmark_canonical"] = canon
        r["type"] = typ
        r["domain"] = DOMAIN_OF.get(canon, "knowledge")
        r["needs_review"] = False
        r["review_reason"] = None
        r["review_issue"] = None
        resolved.append((raw, canon))

    with open(CITES, "w") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    uniq = sorted(set(resolved), key=lambda x: x[1])
    print(f"resolve_aliases: resolved {len(resolved)} record(s) into {len(uniq)} canonical(s) "
          f"via aliases.yaml; {len(still_unmatched)} raw name(s) still unmatched (truly novel)")
    for raw, canon in uniq:
        print(f"  {raw!r} -> {canon}")
    if still_unmatched:
        print("  still unmatched (register in aliases.yaml):", sorted(still_unmatched))

    if uniq:
        entry = {"ts": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
                 "alias_resolutions": [{"raw": raw, "canonical": canon} for raw, canon in uniq],
                 "still_unmatched": sorted(still_unmatched)}
        with open(CHANGELOG, "a") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
