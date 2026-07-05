#!/usr/bin/env python3
"""Build data/citations.jsonl from the flat-file inputs. Pure transform, NO embedded data.

Inputs (all human/agent-editable flat files):
  data/registry.yaml               - benchmark identity: raw->canonical aliases, type, domain
  data/documents.yaml              - one entry per source document (+ default_weight_class)
  data/extractions/<lab>/<id>.yaml - the benchmark mentions extracted from each document

Output:
  data/citations.jsonl             - one record per (document, benchmark), stable-sorted

Normalization is deterministic (exact/normalized alias lookup, never fuzzy). A raw name that
matches no alias is emitted unmatched (needs_review -> register it in registry.yaml; never
guessed). Harbor fields are placeholders here and are filled in live by sync_harbor.py.

Pipeline: build.py -> sync_harbor.py -> gen_models.py -> build_heatmap.py -> check_reconciliation.py
"""
from __future__ import annotations
import json, re, pathlib, sys
import yaml

from scoring import points

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


def norm(s: str) -> str:
    """lowercase; collapse every run of non-alphanumerics to one space (punctuation-insensitive)."""
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def load_registry():
    reg = yaml.safe_load((DATA / "registry.yaml").read_text()) or {}
    alias2canon, meta = {}, {}
    for b in reg.get("benchmarks", []):
        c = b["canonical"]
        meta[c] = {"type": b.get("type"), "domain": b.get("domain")}
        for a in [c] + list(b.get("aliases") or []):
            k = norm(a)
            if k and k not in alias2canon:
                alias2canon[k] = c
    return alias2canon, meta


def load_documents():
    docs = yaml.safe_load((DATA / "documents.yaml").read_text()) or {}
    return {d["id"]: d for d in docs.get("documents", [])}


def placeholder(doc, reason, issue):
    """A machine-unreadable / gated document -> one human-review record (no fabricated scores)."""
    return {
        "benchmark_canonical": None, "benchmark_raw": reason,
        "source_doc": _src(doc), "citing_lab": doc["lab"], "citing_model": doc.get("model"),
        "weight_class": None, "weight": 0,
        "reported": {"value": None, "unit": None, "model_config": None},
        "type": None, "domain": None,
        "on_harbor": False, "harbor_status": "not_in_harbor", "harbor_name": None,
        "harbor_type": None, "harbor_adapter": None,
        "methodology_deviations": [], "score_pending": False,
        "needs_review": True, "review_reason": reason, "review_issue": issue,
    }


def _src(doc):
    return {"id": doc["id"], "lab": doc["lab"], "model": doc.get("model"),
            "container": doc.get("container"), "url": doc["url"],
            "pub_date": doc.get("pub_date"), "primary": True}


def main() -> int:
    alias2canon, meta = load_registry()
    docs = load_documents()
    records, unmatched = [], set()

    for path in sorted((DATA / "extractions").rglob("*.yaml")):
        ext = yaml.safe_load(path.read_text()) or {}
        did = ext.get("doc")
        doc = docs.get(did)
        if not doc:
            sys.exit(f"{path}: doc id {did!r} not found in documents.yaml")

        if ext.get("unreadable"):
            u = ext["unreadable"]
            records.append(placeholder(doc, u.get("reason", "machine-unreadable source"),
                                        u.get("review_issue")))
            continue

        default_wc = doc.get("default_weight_class")
        for m in ext.get("mentions", []):
            raw = m["raw"]
            wc = m.get("weight_class", default_wc)
            canon = alias2canon.get(norm(raw))
            if not canon:
                unmatched.add(raw)
            val = m.get("value")
            rec = {
                "benchmark_canonical": canon, "benchmark_raw": raw,
                "source_doc": _src(doc), "citing_lab": doc["lab"], "citing_model": doc.get("model"),
                "weight_class": wc if canon else None, "weight": points(wc) if canon else 0,
                "reported": {"value": val, "unit": m.get("unit"),
                             "model_config": m.get("model_config")},
                "type": meta.get(canon, {}).get("type") if canon else None,
                "domain": meta.get(canon, {}).get("domain") if canon else None,
                # harbor_* are placeholders; sync_harbor.py fills them from the live registry.
                "on_harbor": False, "harbor_status": "not_in_harbor", "harbor_name": None,
                "harbor_type": None, "harbor_adapter": None,
                "methodology_deviations": list(m.get("methodology") or []),
                "score_pending": canon is not None and val is None,
                "needs_review": canon is None,
                "review_reason": "unmatched benchmark name - register in registry.yaml" if not canon else None,
                "review_issue": 8 if not canon else None,
            }
            records.append(rec)

    # stable sort so diffs are meaningful (by doc id, then benchmark, then raw)
    records.sort(key=lambda r: (r["source_doc"]["id"], r["benchmark_canonical"] or "~",
                                r["benchmark_raw"]))
    with open(DATA / "citations.jsonl", "w") as fh:
        for r in records:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"build: {len(records)} records | "
          f"{len({r['benchmark_canonical'] for r in records if r['benchmark_canonical']})} benchmarks | "
          f"{len(docs)} docs | {sum(1 for r in records if r['needs_review'])} needs_review | "
          f"{sum(1 for r in records if r['reported']['value'] is not None)} with a score")
    if unmatched:
        print("UNMATCHED (register in registry.yaml):", sorted(unmatched))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
