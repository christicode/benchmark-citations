#!/usr/bin/env python3
"""Automated benchmark DISCOVERY + inventory VERIFICATION over a source document.

Discovery : detect which benchmarks a doc's text actually contains.
Verify    : diff that against a doc's recorded inventory -> flag OMISSIONS (in doc, not on our
            list) and COMMISSIONS (on our list, not in the doc). Surfaces gaps for human review;
            it never edits data and never blocks a build.

Matching is deterministic and precise (no fuzzy guessing):
  * whole-phrase, punctuation-insensitive ("SWE-bench Verified" == "swe bench verified");
  * longest alias first, then consumed, so a short alias can't fire inside a longer one
    ("MMMU" won't match inside "MMMU-Pro"; bare "SWE-bench" won't match inside "SWE-bench Pro");
  * alias-aware ("HLE" is found via its alias "Humanity's Last Exam").

Usage:
  extract.py <file> [--text] [--emit]   # single-doc discovery (path; PDF via pdftotext)
  extract.py --audit                    # fetch every readable doc and verify its inventory vs text
"""
from __future__ import annotations
import re, sys, json, subprocess, pathlib, argparse, html, collections
try:
    import yaml
except ImportError:
    sys.exit("pip install pyyaml")

ROOT = pathlib.Path(__file__).resolve().parents[1]

# Heuristic for NEW/unregistered names (capitalized *Bench/*Eval/*QA/... seen >=2x).
NEW_NAME = re.compile(r'\b([A-Z][A-Za-z0-9]*(?:[-\u2011\u2013\.][A-Za-z0-9\.]+)*'
                      r'(?:Bench|bench|Eval|QA|Arena|AGI|Gym))\b')


def norm(s: str) -> str:
    """lowercase; collapse every run of non-alphanumerics to one space. Punctuation-insensitive
    whole-phrase matching key."""
    return re.sub(r'[^a-z0-9]+', ' ', s.lower()).strip()


def load_registry():
    """(alias2canon, canon2aliases) from the flat-file alias registry. Deterministic; never fuzzy."""
    a2c = {}
    for fn in ("data/aliases.yaml", "data/aliases_generated.yaml"):
        p = ROOT / fn
        if not p.exists():
            continue
        for b in (yaml.safe_load(open(p)) or {}).get("benchmarks", []):
            can = b["canonical"]
            for al in [can] + list(b.get("aliases", [])):
                na = norm(str(al))
                if na:
                    a2c[na] = can
    c2a = collections.defaultdict(list)
    for na, can in a2c.items():
        c2a[can].append(na)
    return a2c, c2a


def detected(text: str, a2c: dict) -> set:
    """Canonicals whose alias occurs as a whole phrase; longest-first with consumption."""
    pad = " " + norm(text) + " "
    found = set()
    for alias in sorted(a2c, key=len, reverse=True):
        needle = " " + alias + " "
        if needle in pad:
            found.add(a2c[alias])
            pad = pad.replace(needle, "  ")   # consume so shorter sub-aliases can't rematch
    return found


def new_names(text: str, a2c: dict) -> list:
    """Capitalized benchmark-shaped tokens seen >=2x that are NOT in the registry (candidates to add)."""
    known = set(a2c)
    out = set()
    for m in NEW_NAME.finditer(text):
        tok = m.group(1)
        if text.count(tok) >= 2 and norm(tok) not in known:
            out.add(tok)
    return sorted(out)


def verify(text: str, inventory: list, a2c: dict):
    """(omissions, commissions): omissions = detected canonicals not on the list; commissions =
    inventory items whose canonical no alias appears for in the text."""
    det = detected(text, a2c)
    inv_can = {a2c.get(norm(x)) for x in inventory}
    omissions = sorted(det - {c for c in inv_can if c})
    commissions = sorted({x for x in inventory
                          if a2c.get(norm(x)) and a2c[norm(x)] not in det})
    return omissions, commissions


def doc_text_from_path(path: str, is_text: bool) -> str:
    if is_text:
        return pathlib.Path(path).read_text(errors="ignore")
    return subprocess.run(["pdftotext", "-q", path, "-"], capture_output=True, text=True).stdout


def fetch(url: str):
    """Best-effort readable text for a URL (audit only; never called from the build).
    arXiv abstract -> PDF; PDF -> pdftotext; HTML -> stripped. None if gated/unreachable/empty."""
    if "arxiv.org/abs/" in url:
        url = url.replace("/abs/", "/pdf/")
    try:
        r = subprocess.run(["curl", "-sL", "-A", "Mozilla/5.0 (audit)", "--max-time", "45",
                            url, "-o", "/tmp/_extract_fetch.bin", "-w", "%{content_type}|%{http_code}"],
                           capture_output=True, text=True, timeout=60)
        ct, _, code = r.stdout.strip().partition("|")
        if code[:1] in ("4", "5"):
            return None
        data = open("/tmp/_extract_fetch.bin", "rb").read()
    except Exception:
        return None
    if data[:5] == b"%PDF-" or "pdf" in ct.lower():
        txt = subprocess.run(["pdftotext", "-q", "/tmp/_extract_fetch.bin", "-"],
                             capture_output=True, text=True).stdout
    else:
        t = data.decode("utf-8", "replace")
        t = re.sub(r"<script.*?</script>", " ", t, flags=re.S | re.I)
        t = re.sub(r"<style.*?</style>", " ", t, flags=re.S | re.I)
        txt = html.unescape(re.sub(r"<[^>]+>", " ", t))
    return txt if len(txt) >= 400 else None


def doc_inventories():
    """Reconstruct {url: {label, names}} from data/citations.jsonl WITHOUT importing the builder
    (no side effects). Drops image/gated placeholder rows (long 'unreadable' reason strings)."""
    inv = collections.defaultdict(lambda: {"label": "", "names": []})
    for line in open(ROOT / "data" / "citations.jsonl"):
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        url = r["source_doc"]["url"]
        inv[url]["label"] = (r["source_doc"].get("model") or r["citing_lab"])
        raw = r["benchmark_raw"]
        if r["benchmark_canonical"] is None and len(raw) > 45:   # unreadable-doc reason string
            continue
        inv[url]["names"].append(raw)
    return inv


def audit():
    a2c, _ = load_registry()
    n_read = n_skip = n_om = 0
    for url, rec in doc_inventories().items():
        if not rec["names"]:
            n_skip += 1
            continue
        text = fetch(url)
        if not text:
            print(f"[skip] {rec['label'][:34]:34} gated/image/unreachable -> human review")
            n_skip += 1
            continue
        n_read += 1
        om, com = verify(text, rec["names"], a2c)
        nn = new_names(text, a2c)
        n_om += len(om)
        if om or com or nn:
            print(f"=== {rec['label'][:40]}  ({url.rsplit('/', 2)[-1][:32]}) ===")
            if om:  print(f"   OMISSION  (in doc, not on our list): {om}")
            if com: print(f"   COMMISSION(on our list, not in doc): {com}")
            if nn:  print(f"   NEW?      (unregistered, seen>=2x)  : {nn}")
    print(f"\n# read {n_read}, skipped {n_skip} (unreadable), {n_om} omission-flags. "
          f"Flags are for human review; nothing is auto-changed.")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("doc", nargs="?")
    ap.add_argument("--text", action="store_true")
    ap.add_argument("--emit", action="store_true")
    ap.add_argument("--audit", action="store_true")
    args = ap.parse_args()

    if args.audit:
        audit()
        return
    if not args.doc:
        ap.error("provide a doc path or --audit")

    a2c, _ = load_registry()
    text = doc_text_from_path(args.doc, args.text)
    det = sorted(detected(text, a2c))
    nn = new_names(text, a2c)
    if args.emit:
        for c in det:
            print(json.dumps({"benchmark_canonical": c, "source_doc": {"url": args.doc},
                              "score_pending": True, "needs_review": False}))
        for raw in nn:
            print(json.dumps({"benchmark_canonical": None, "benchmark_raw": raw,
                              "source_doc": {"url": args.doc}, "needs_review": True,
                              "review_reason": "unmatched benchmark name - register alias / open issue"}))
        return
    print(f"# {args.doc}: {len(det)} registry benchmarks detected, {len(nn)} new-name candidate(s)")
    for c in det:
        print(f"  detected  {c}")
    for raw in nn:
        print(f"  REVIEW    {raw:28} -> unregistered (open needs-human-review issue; never guess)")


if __name__ == "__main__":
    main()
