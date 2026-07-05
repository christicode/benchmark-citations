#!/usr/bin/env python3
"""discover.py - the SEARCHER stage (feeds -> candidates). Wires in labs.yaml.

For every lab in labs.yaml it crawls each `source_index_urls` entry (release-blog / model-card
indexes) AND queries the Hugging Face API for the lab's org, collects candidate document URLs,
then DIFFS them against everything already tracked (data/documents.yaml + data/citations.jsonl).
What remains = NEW candidate documents a human should promote (feeds -> candidates -> human
promotes -> extract).

It intentionally does NOT:
  * extract benchmarks (that's extract.py, on a promoted doc), or
  * open GitHub issues / push (guardrail: publishing needs explicit human confirmation).

Output:
  * data/candidates.jsonl  - the current NEW-candidate set (durable, git-tracked review queue)
  * stdout summary grouped by lab

Usage:
  python scripts/discover.py            # crawl live, refresh data/candidates.jsonl
  python scripts/discover.py --print    # show current candidates.jsonl, no network
"""
from __future__ import annotations
import argparse, datetime, html, json, pathlib, re, sys, urllib.parse, urllib.request
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
UA = "benchmark-citations-discover (+https://github.com/christicode/benchmark-citations)"

# obvious non-document links to drop from crawled index pages
JUNK = re.compile(r"(/privacy|/terms|/careers|/about|/legal|/pricing|/contact|mailto:|/rss|"
                  r"/feed|mastodon|twitter\.com|x\.com|linkedin\.com|youtube\.com|facebook\.com|"
                  r"instagram\.com|tiktok\.com|discord|/login|/subscribe|\.xml|/cookie)", re.I)


def fetch(url: str) -> str | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=45) as r:
            return r.read().decode("utf-8", "replace")
    except Exception as e:
        print(f"  ! fetch failed {url} ({e})", file=sys.stderr)
        return None


def norm_url(u: str) -> str:
    """Canonical form for diffing: drop fragment/query, trailing slash, scheme-normalize."""
    u = urllib.parse.urldefrag(u)[0].split("?")[0]
    return u.rstrip("/")


def known_urls() -> set[str]:
    urls = set()
    docs = yaml.safe_load((DATA / "documents.yaml").read_text()) or {}
    for d in docs.get("documents", []):
        urls.add(norm_url(d["url"]))
    if (DATA / "citations.jsonl").exists():
        for line in open(DATA / "citations.jsonl"):
            if line.strip():
                urls.add(norm_url(json.loads(line)["source_doc"]["url"]))
    return urls


def links_from(page: str, base: str, index_url: str) -> set[str]:
    """Absolute, same-host links that look like documents (not nav/boilerplate).
    Heuristic: keep links that share a path segment with the index (e.g. /news/, /model-cards/)."""
    host = urllib.parse.urlparse(base).netloc
    hint = [seg for seg in urllib.parse.urlparse(index_url).path.split("/") if seg]
    hint = hint[0] if hint else ""
    out = set()
    for m in re.finditer(r'href=["\']([^"\']+)["\']', page, re.I):
        href = html.unescape(m.group(1))
        absu = urllib.parse.urljoin(base, href)
        p = urllib.parse.urlparse(absu)
        if p.scheme not in ("http", "https") or p.netloc != host:
            continue
        if JUNK.search(absu) or norm_url(absu) == norm_url(index_url):
            continue
        # must look like a leaf doc: hint segment present AND at least one path segment beyond it
        segs = [s for s in p.path.split("/") if s]
        if hint and hint in segs and segs[-1] != hint:
            out.add(norm_url(absu))
    return out


def hf_models(org: str) -> set[str]:
    """New model repos for an org via the HF API (catches open-weight cards proactively)."""
    api = f"https://huggingface.co/api/models?author={urllib.parse.quote(org)}&sort=createdAt&direction=-1&limit=50"
    txt = fetch(api)
    if not txt:
        return set()
    try:
        return {norm_url(f"https://huggingface.co/{m['id']}") for m in json.loads(txt) if m.get("id")}
    except Exception:
        return set()


def discover() -> int:
    labs = yaml.safe_load((ROOT / "labs.yaml").read_text())
    known = known_urls()
    deny = labs.get("hf_deny_suffixes", [])
    pat_by_lab = {lab["id"]: [re.compile(p, re.I) for p in lab.get("candidate_patterns", [])]
                  for lab in labs.get("labs", [])}

    def denied(url: str) -> bool:
        if "huggingface.co" not in url:
            return False
        leaf = url.rstrip("/").rsplit("/", 1)[-1]
        return any(leaf.endswith(s) for s in deny)

    def passes(lab_id: str, url: str) -> bool:
        if denied(url):
            return False
        pats = pat_by_lab.get(lab_id, [])
        return (not pats) or any(p.search(url) for p in pats)   # patterns defined => must match one

    candidates = {}   # url -> record
    for lab in labs.get("labs", []):
        if not lab.get("in_scope", True):
            continue
        lid = lab["id"]
        found = set()
        for idx in lab.get("source_index_urls", []):
            host = urllib.parse.urlparse(idx).netloc
            if host == "huggingface.co":
                org = [s for s in urllib.parse.urlparse(idx).path.split("/") if s]
                if org:
                    found |= {(u, f"hf:{org[0]}") for u in hf_models(org[0])}
            else:
                page = fetch(idx)
                if page:
                    found |= {(u, idx) for u in links_from(page, idx, idx)}
        for url, src in found:
            if url in known or url in candidates or not passes(lid, url):
                continue
            candidates[url] = {"lab": lid, "url": url, "discovered_from": src,
                               "first_seen": datetime.date.today().isoformat(),
                               "status": "candidate"}

    # carry forward previously-seen candidates that are still un-promoted AND still pass the
    # current filters (so tightening a lab's patterns also prunes the stale queue).
    if (DATA / "candidates.jsonl").exists():
        for line in open(DATA / "candidates.jsonl"):
            if not line.strip():
                continue
            r = json.loads(line)
            u = norm_url(r["url"])
            if u in known or u in candidates or not passes(r.get("lab", ""), u):
                continue
            candidates[u] = {**r, "url": u}

    rows = sorted(candidates.values(), key=lambda r: (r["lab"], r["url"]))
    with open(DATA / "candidates.jsonl", "w") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"discover: {len(rows)} open candidate doc(s) across "
          f"{len({r['lab'] for r in rows})} lab(s); {len(known)} docs already tracked.\n")
    cur = None
    for r in rows:
        if r["lab"] != cur:
            cur = r["lab"]; print(f"[{cur}]")
        print(f"  - {r['url']}")
    print("\nNext: a human promotes real docs; then run extract.py + add data/extractions/<lab>/<id>.yaml.")
    print("(discover.py never extracts or opens issues on its own.)")
    return 0


def show() -> int:
    p = DATA / "candidates.jsonl"
    if not p.exists():
        print("no candidates.jsonl yet; run: python scripts/discover.py")
        return 0
    rows = [json.loads(l) for l in open(p) if l.strip()]
    for r in rows:
        print(f"  [{r['lab']}] {r['url']}  (seen {r.get('first_seen')}, from {r.get('discovered_from')})")
    print(f"\n{len(rows)} open candidate(s).")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--print", action="store_true", help="show current candidates.jsonl (no network)")
    args = ap.parse_args()
    return show() if getattr(args, "print") else discover()


if __name__ == "__main__":
    raise SystemExit(main())
