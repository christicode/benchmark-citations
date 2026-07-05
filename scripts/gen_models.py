#!/usr/bin/env python3
"""Generate models.yaml — the MODEL axis registry for the heatmap dashboard.

Models are DERIVED, not hand-curated: every distinct `citing_model` in
data/citations.jsonl becomes an entry, its company taken from `citing_lab`
(labelled via labs.yaml) and its `release_date` proxied by the EARLIEST source-doc
`pub_date` we've seen for that model. This means a newly-extracted model shows up on
the heatmap X-axis automatically on the next regen — no human curation step.

Anything we can't derive honestly (a model whose docs carry no pub_date) is written as
`release_date: null` with `release_date_source: unknown` and surfaced in the run summary
so it can be backfilled from the real source doc. We never guess a date.

Manual overrides: if data/models.overrides.yaml exists, its per-model keys
(display / release_date / company) win over the derived values — so a human OR an agent
can pin a clean label or a real release date without it being clobbered on regen.

Pipeline position (regenerate Action), after the harbor sync:
    build.py -> sync_harbor.py -> gen_models.py -> build_heatmap.py -> check_reconciliation.py
"""
from __future__ import annotations

import collections
import datetime
import json
import pathlib
import re
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
CITES = ROOT / "data" / "citations.jsonl"
LABS = ROOT / "labs.yaml"
OVERRIDES = ROOT / "data" / "models.overrides.yaml"
OUT = ROOT / "data" / "models.yaml"

# Leading vendor words that are redundant with the company column and are stripped from
# the short display label (the company is already a separate axis/filter). GPT / Gemini /
# Grok / Kimi / GLM / Qwen / Mistral / DeepSeek are kept because they ARE the model line.
STRIP_PREFIXES = ("Claude ",)


def slugify(s: str) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", (s or "").lower())).strip("-")


def short_label(model: str) -> str:
    """Human-facing short label. Combined release names (e.g. 'Claude Fable 5 / Mythos 5')
    collapse to the first alternative; a redundant vendor prefix is dropped."""
    label = model.split(" / ")[0].strip()
    for p in STRIP_PREFIXES:
        if label.startswith(p):
            label = label[len(p):]
            break
    return label


def load_lab_display() -> dict:
    labs = yaml.safe_load(LABS.read_text())
    return {l["id"]: {"display": l.get("display_name", l["id"]),
                      "category": l.get("category", "?")}
            for l in labs.get("labs", [])}


def main() -> int:
    lab_meta = load_lab_display()
    overrides = {}
    if OVERRIDES.exists():
        overrides = (yaml.safe_load(OVERRIDES.read_text()) or {}).get("models", {}) or {}

    rows = [json.loads(l) for l in open(CITES) if l.strip()]
    agg = collections.defaultdict(lambda: {"dates": set(), "docs": set(),
                                           "n": 0, "aliases": set()})
    for r in rows:
        m = r.get("citing_model")
        if not m:
            continue
        key = (r["citing_lab"], m)
        a = agg[key]
        a["n"] += 1
        a["aliases"].add(m)
        d = r["source_doc"].get("pub_date")
        if d:
            a["dates"].add(d)
        a["docs"].add(r["source_doc"]["url"])

    models = []
    undated = []
    for (lab, model), a in agg.items():
        mid = slugify(model.split(" / ")[0])
        ov = overrides.get(mid, {}) or overrides.get(model, {}) or {}
        release = ov.get("release_date") or (min(a["dates"]) if a["dates"] else None)
        src = ("override" if ov.get("release_date")
               else "derived:min_pub_date" if a["dates"] else "unknown")
        if release is None:
            undated.append(f"{lab}:{model}")
        entry = {
            "id": mid,
            "model": model,                                  # verbatim citing_model
            "display": ov.get("display") or short_label(model),
            "company": ov.get("company") or lab,
            "company_display": lab_meta.get(lab, {}).get("display", lab),
            "company_category": lab_meta.get(lab, {}).get("category", "?"),
            "release_date": release,                         # X-axis sort key (recent = left)
            "release_date_source": src,
            "citations": a["n"],
            "docs": sorted(a["docs"]),
        }
        models.append(entry)

    # Sort: most-recent first (heatmap places these left -> right). Undated sink to the end
    # (sorted by name) so they're visibly grouped rather than silently mis-dated.
    models.sort(key=lambda e: (e["release_date"] is None,
                               "" if e["release_date"] is None else "",
                               ),)
    dated = sorted([m for m in models if m["release_date"]],
                   key=lambda e: e["release_date"], reverse=True)
    nodate = sorted([m for m in models if not m["release_date"]],
                    key=lambda e: e["display"].lower())
    models = dated + nodate

    doc = {
        "_generated_by": "scripts/gen_models.py",
        "_generated_at": datetime.date.today().isoformat(),
        "_note": ("MODEL axis for the heatmap. Derived from data/citations.jsonl; release_date "
                  "is the earliest source-doc pub_date (proxy). Override display/release_date in "
                  "data/models.overrides.yaml. X-axis order: most recent on the LEFT; undated "
                  "models are grouped at the end until a real date is backfilled."),
        "schema_version": 1,
        "count": len(models),
        "undated_needs_backfill": sorted(undated),
        "models": models,
    }
    OUT.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=100))
    print(f"gen_models: wrote {OUT} | {len(models)} models "
          f"({len(dated)} dated, {len(nodate)} undated)", file=sys.stderr)
    if undated:
        print("  undated (release_date=null, backfill from source doc): "
              + ", ".join(undated), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
