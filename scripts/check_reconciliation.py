#!/usr/bin/env python3
"""Reconciliation invariant for the coverage matrix (docs/coverage.html).

Fails (exit 1) if a cited benchmark is normalized-identical to a Harbor adapter/registry
entry yet would NOT merge onto that row in build_dashboard._build_coverage. That is exactly
the "AIME shows twice / 0 in all three" failure that shipped when a citations.jsonl edit
briefly dropped the harbor_type classification: with no harbor_type, the citation->Harbor
join matches nothing and every benchmark splits into a cite-only row and a harbor-only row.

A curated non-merge (harbor_type == "none": a reviewed name collision where the cited
benchmark is genuinely NOT the same as the same-named Harbor entry) is legitimate and
suppressed. Anything else aborts the build so the regenerate Action goes red and the
last-good docs/coverage.html stays deployed instead of being overwritten with a split matrix.

Run standalone (`python scripts/check_reconciliation.py`) or as a CI gate before the
regenerate Action's commit step. Reads only data/citations.jsonl + data/harbor_adapters.json.
"""
from __future__ import annotations
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]


def norm(s):
    # identical to build_dashboard._build_coverage.norm
    return "".join(ch for ch in (s or "").lower() if ch.isalnum())


def main():
    rows = [json.loads(l) for l in open(ROOT / "data" / "citations.jsonl") if l.strip()]
    snap = json.loads((ROOT / "data" / "harbor_adapters.json").read_text())

    reg_norm = {norm(rg["name"]) for rg in snap.get("registry", [])}
    ad_names = {ad["name"] for ad in snap.get("adapters", [])}
    # every Harbor identity a citation could legitimately line up with, normalized
    harbor_norm = set(reg_norm)
    harbor_norm |= {norm(nm) for nm in ad_names}
    harbor_norm |= {norm(ad["registry_name"]) for ad in snap.get("adapters", []) if ad.get("registry_name")}

    # aggregate the Harbor-linking fields per canonical, mirroring _build_coverage's `cite` dict
    agg = {}
    for r in rows:
        c = r.get("benchmark_canonical")
        if not c:
            continue
        d = agg.setdefault(c, {"htype": None, "hname": None, "hadapter": None})
        d["htype"] = r.get("harbor_type") or d["htype"]
        d["hname"] = r.get("harbor_name") or d["hname"]
        d["hadapter"] = r.get("harbor_adapter") or d["hadapter"]

    unreconciled = []
    for c, d in agg.items():
        # does this citation merge onto a Harbor row? (same predicate as _build_coverage)
        merged = False
        if d["htype"] in ("native", "fork", "adapter"):
            if (d["hname"] and norm(d["hname"]) in reg_norm) \
               or (d["hadapter"] in ad_names) \
               or (d["hadapter"] and norm(d["hadapter"]) in reg_norm):
                merged = True
        if merged:
            continue
        if d["htype"] == "none":          # curated, reviewed non-merge -> legitimate
            continue
        if norm(c) in harbor_norm:         # same identity as a Harbor entry but did NOT merge
            unreconciled.append((c, d["htype"]))

    if unreconciled:
        unreconciled.sort()
        print("RECONCILIATION ERROR: coverage matrix is NOT reconciled.", file=sys.stderr)
        print(f"{len(unreconciled)} cited benchmark(s) are name-identical to a Harbor "
              "adapter/registry entry but would not merge onto that row "
              "(usually a missing harbor_type in data/citations.jsonl):", file=sys.stderr)
        for c, ht in unreconciled:
            print(f"  - {c}  (harbor_type={ht!r})", file=sys.stderr)
        print("Refusing to publish a split coverage matrix. This normally means sync_harbor.py "
              "did not set harbor_type (rerun it), or the name is a genuine (reviewed) collision "
              "that should be recorded as a `collision:` note in registry.yaml.", file=sys.stderr)
        return 1

    print(f"reconciliation OK: {len(agg)} cited canonicals, 0 unreconciled "
          f"name-collisions against {len(harbor_norm)} Harbor identities.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
