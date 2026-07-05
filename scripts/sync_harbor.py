#!/usr/bin/env python3
"""Derive every citation's Harbor fields from the ACTUAL Harbor repo (registry.json +
adapters/), automatically. No hand-curated status: a benchmark is "on Harbor" iff it
matches a live adapter or registry entry. New adapters are picked up on every run.

Pipeline position (regenerate Action):
    build.py  ->  sync_harbor.py  ->  build_dashboard.py  ->  check_reconciliation.py
build.py writes the citation graph; THIS script overwrites the harbor_* fields
(on_harbor / harbor_status / harbor_type / harbor_name / harbor_adapter) from the snapshot,
clears harbor-driven needs_review, and appends a run entry to data/changelog.jsonl.

Matching is deterministic:
  * normalized-exact (lowercase, alnum-only) against adapter name, adapter.registry_name,
    and registry name -- so aime/cybergym/osworld/hle/swe-bench-verified all match; AND
  * a tiny curated BRIDGE for genuine acronym drift that normalization can't catch (HLE->hle).
Anything that does NOT match is simply not_in_harbor (a real Harbor-conversion candidate) --
never a human gate. Truly human-blocking records (image/chart-only or gated docs, which have
benchmark_canonical == None) are left untouched so they remain review issues.

Harbor set is refreshed LIVE from main; on any network failure it falls back to the committed
data/harbor_adapters.json snapshot (build stays deterministic, never silently wrong).
"""
from __future__ import annotations
import datetime
import json
import os
import pathlib
import subprocess
import sys
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
SNAP = ROOT / "data" / "harbor_adapters.json"
CITES = ROOT / "data" / "citations.jsonl"
CHANGELOG = ROOT / "data" / "changelog.jsonl"

REGISTRY_RAW = "https://raw.githubusercontent.com/harbor-framework/harbor/main/registry.json"
ADAPTERS_API = "https://api.github.com/repos/harbor-framework/harbor/contents/adapters?ref=main"

# Curated name-drift bridge: canonical -> harbor identity, ONLY where normalization cannot
# connect them. Keep this tiny and obvious; everything else is matched automatically.
BRIDGE = {
    "humanitys-last-exam": "hle",   # HLE = Humanity's Last Exam
}


def norm(s):
    return "".join(ch for ch in (s or "").lower() if ch.isalnum())


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "benchmark-citations-sync"})
    tok = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if tok and url.startswith("https://api.github.com"):
        req.add_header("Authorization", f"Bearer {tok}")
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.load(r)


def fetch_live():
    """Return a snapshot dict {adapters, registry, ...} fetched live, or raise."""
    reg_raw = _get(REGISTRY_RAW)                       # flat list, duplicate names expected
    versions = {}
    for d in reg_raw:
        nm = d.get("name")
        if not nm:
            continue
        versions.setdefault(nm, set()).add(str(d.get("version")))
    registry = [{"name": n, "versions": sorted(v)} for n, v in sorted(versions.items())]
    reg_norm = {norm(n) for n in versions}

    entries = _get(ADAPTERS_API)                       # adapters/ dir listing
    adapters = []
    for e in entries:
        if e.get("type") != "dir":
            continue
        nm = e["name"]
        in_reg = norm(nm) in reg_norm
        adapters.append({"name": nm, "in_registry": in_reg,
                         "registry_name": nm if in_reg else None})
    adapters.sort(key=lambda a: a["name"])
    return {"_comment": "Live Harbor snapshot (registry.json + adapters/) fetched by sync_harbor.py.",
            "source": "harbor-framework/harbor @ main",
            "fetched_at": datetime.date.today().isoformat(),
            "n_adapters": len(adapters), "n_registry": len(registry),
            "n_in_registry": sum(1 for a in adapters if a["in_registry"]),
            "adapters": adapters, "registry": registry}


def load_snapshot():
    """Fetch live; fall back to the committed snapshot on any failure."""
    try:
        snap = fetch_live()
        print(f"harbor: live fetch OK -- {snap['n_adapters']} adapters, "
              f"{snap['n_registry']} registry names [main]", file=sys.stderr)
        SNAP.write_text(json.dumps(snap, indent=2) + "\n")
        return snap
    except Exception as e:
        snap = json.loads(SNAP.read_text())
        print(f"harbor: live fetch failed ({e}); using committed snapshot "
              f"fetched_at={snap.get('fetched_at')}", file=sys.stderr)
        return snap


def build_index(snap):
    reg_by_norm = {norm(r["name"]): r for r in snap.get("registry", [])}
    ad_by_norm = {}
    for a in snap.get("adapters", []):
        ad_by_norm[norm(a["name"])] = a
        if a.get("registry_name"):
            ad_by_norm[norm(a["registry_name"])] = a
    return reg_by_norm, ad_by_norm


def resolve(canonical, reg_by_norm, ad_by_norm):
    """(on_harbor, status, harbor_type, harbor_name, harbor_adapter) from the live set."""
    key = norm(BRIDGE.get(canonical, canonical))
    a = ad_by_norm.get(key)
    if a:  # an adapter exists => Harbor-format adapter (registry-backed or not-yet-registered)
        hname = a["registry_name"] if (a.get("in_registry") and a.get("registry_name")) else a["name"]
        return True, "confirmed", "adapter", hname, a["name"]
    r = reg_by_norm.get(key)
    if r:  # in registry, no adapter => native/registry
        return True, "confirmed", "native", r["name"], None
    return False, "not_in_harbor", "none", None, None


def committed_prev_status():
    """Previous (status, on_harbor) per canonical from the LAST COMMITTED citations.jsonl
    (git HEAD), so the change log records genuine Harbor flips - not the placeholder reset
    that build.py writes on every run. Falls back to {} if git/HEAD is unavailable."""
    prev = {}
    try:
        blob = subprocess.run(["git", "-C", str(ROOT), "show", "HEAD:data/citations.jsonl"],
                              capture_output=True, text=True, timeout=30)
        if blob.returncode != 0:
            return {}
        for line in blob.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            c = r.get("benchmark_canonical")
            if c and c not in prev:
                prev[c] = (r.get("harbor_status"), bool(r.get("on_harbor")))
    except Exception:
        return {}
    return prev


def main():
    snap = load_snapshot()
    reg_by_norm, ad_by_norm = build_index(snap)
    rows = [json.loads(l) for l in open(CITES) if l.strip()]

    # Compare against the committed state, not build.py's placeholder reset.
    prev = committed_prev_status()

    changes = []
    for r in rows:
        c = r.get("benchmark_canonical")
        if not c:
            continue  # image/chart-only or gated doc -> stays a human review issue; untouched
        on, status, htype, hname, hadapter = resolve(c, reg_by_norm, ad_by_norm)
        r["on_harbor"] = on
        r["harbor_status"] = status
        r["harbor_type"] = htype
        r["harbor_name"] = hname
        r["harbor_adapter"] = hadapter
        # harbor presence is now automatic -> clear any harbor-driven review flag on
        # matched records. (Non-canonical records above keep theirs.)
        if r.get("needs_review") and r.get("review_reason") in (
                "Harbor variant/version unconfirmed", "Harbor auto-match is false positive", None):
            r["needs_review"] = False
            r["review_reason"] = None
            r["review_issue"] = None

    # change log: per-benchmark status flips (dedupe to one line per canonical)
    seen = set()
    for r in rows:
        c = r.get("benchmark_canonical")
        if not c or c in seen:
            continue
        seen.add(c)
        old = prev.get(c, (None, None))
        new = (r["harbor_status"], r["on_harbor"])
        if old[0] != new[0] or old[1] != new[1]:
            matched = (f"adapter:{r['harbor_adapter']}" if r["harbor_type"] == "adapter"
                       else f"registry:{r['harbor_name']}" if r["harbor_type"] == "native"
                       else "none")
            changes.append({"benchmark": c, "from": old[0], "to": new[0], "matched": matched})

    with open(CITES, "w") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    on_n = sum(1 for r in rows if r.get("on_harbor"))
    print(f"sync_harbor: {len(rows)} records | on_harbor now True on "
          f"{on_n} | {len(changes)} benchmark status change(s)")

    if changes:
        entry = {"ts": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
                 "harbor_source": snap.get("source"), "harbor_fetched_at": snap.get("fetched_at"),
                 "n_adapters": snap.get("n_adapters"), "n_registry": snap.get("n_registry"),
                 "harbor_status_changes": sorted(changes, key=lambda x: x["benchmark"])}
        with open(CHANGELOG, "a") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        for ch in entry["harbor_status_changes"]:
            print(f"  {ch['benchmark']}: {ch['from']} -> {ch['to']}  ({ch['matched']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
