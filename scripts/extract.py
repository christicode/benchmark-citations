#!/usr/bin/env python3
"""Automated benchmark DISCOVERY over a source document.

This is the script that actually reads a doc and finds benchmark mentions. Given a
PDF (or extracted text), it detects candidate benchmark names, normalizes them
against the alias registry (data/aliases*.yaml), and reports:
  - matched benchmarks (known canonicals)
  - UNMATCHED candidates -> must be flagged for human review (never guessed)

Pipeline role: run on each promoted document during the forward watch. Reading exact
scores from tables remains a reviewed step that lands curated in data/citations.jsonl.

Usage:
  python scripts/extract.py path/to/doc.pdf
  python scripts/extract.py --text path/to/doc.txt
  python scripts/extract.py --emit path/to/doc.pdf   # print citation-record stubs (JSONL)
"""
from __future__ import annotations
import re, sys, json, subprocess, pathlib, argparse
try:
    import yaml
except ImportError:
    sys.exit("pip install pyyaml")

ROOT = pathlib.Path(__file__).resolve().parents[1]

# benchmark-name-shaped tokens (CamelCase/hyphenated ending in eval markers) + curated known list
DETECT = re.compile(r'\b([A-Z][A-Za-z0-9]*(?:[-\u2011\u2013\.][A-Za-z0-9\.]+)*'
                    r'(?:Bench|bench|Eval|QA|Arena|AGI|Gym))\b')
KNOWN = ["SWE-bench", "GPQA", "MMLU", "MMLU-Pro", "MMMU", "MMMU-Pro", "OSWorld", "HLE",
         "Humanity's Last Exam", "GDPval", "BrowseComp", "Cybench", "CyberGym", "ARC-AGI",
         "AIME", "HMMT", "MathArena", "SimpleQA", "LiveCodeBench", "Terminal-Bench",
         "Vending-Bench", "FrontierCode", "ProgramBench", "CharXiv", "LAB-Bench", "ProtocolQA",
         "WMDP", "AgentHarm", "OR-Bench", "StrongReject", "MASK", "SHADE", "Petri", "HealthBench",
         "Toolathlon", "tau2", "GDP.pdf", "GDPval-AA", "CVE-Bench", "USAMO", "CritPt"]


def load_aliases() -> dict:
    """alias(lowercased) -> canonical, from the curated + auto-generated registries."""
    a2c = {}
    for fn in ["data/aliases.yaml", "data/aliases_generated.yaml"]:
        p = ROOT / fn
        if not p.exists():
            continue
        y = yaml.safe_load(open(p)) or {}
        for b in y.get("benchmarks", []):
            a2c[b["canonical"].lower()] = b["canonical"]
            for al in b.get("aliases", []):
                a2c[str(al).strip().lower()] = b["canonical"]
    return a2c


def doc_text(path: str, is_text: bool) -> str:
    if is_text:
        return pathlib.Path(path).read_text(errors="ignore")
    return subprocess.run(["pdftotext", "-q", path, "-"], capture_output=True, text=True).stdout


def detect(text: str) -> set:
    cands = {m.group(1) for m in DETECT.finditer(text) if text.count(m.group(1)) >= 2}
    cands |= {k for k in KNOWN if k in text}
    return cands


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("doc")
    ap.add_argument("--text", action="store_true", help="input is already extracted text")
    ap.add_argument("--emit", action="store_true", help="print citation-record stubs as JSONL")
    args = ap.parse_args()

    a2c = load_aliases()
    cands = detect(doc_text(args.doc, args.text))
    matched, unmatched = [], []
    for c in sorted(cands):
        canon = a2c.get(c.strip().lower())
        (matched if canon else unmatched).append((c, canon))

    if args.emit:
        for raw, canon in matched:
            print(json.dumps({"benchmark_canonical": canon, "benchmark_raw": raw,
                              "source_doc": {"url": args.doc}, "score_pending": True,
                              "needs_review": False}))
        for raw, _ in unmatched:
            print(json.dumps({"benchmark_canonical": None, "benchmark_raw": raw,
                              "source_doc": {"url": args.doc}, "needs_review": True,
                              "review_reason": "unmatched benchmark name - register alias / open issue"}))
        return

    print(f"# {args.doc}: {len(cands)} candidates ({len(matched)} matched, {len(unmatched)} UNMATCHED)")
    for raw, canon in matched:
        print(f"  match   {raw:28} -> {canon}")
    for raw, _ in unmatched:
        print(f"  REVIEW  {raw:28} -> unmatched (open needs-human-review issue; never guess)")


if __name__ == "__main__":
    main()
