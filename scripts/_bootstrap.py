#!/usr/bin/env python3
"""ONE-TIME server-side bootstrap: regenerate the flat-file data layer from the OLD committed
data (data/citations.jsonl + data/aliases.yaml) so we don't hand-transcribe large YAML.
Produces data/registry.yaml, data/documents.yaml, data/extractions/** and applies the blog
headliner re-categorization. Deterministic; delete after the one run."""
import json, re, pathlib, collections
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
ROWS = [json.loads(l) for l in open(DATA / "citations.jsonl") if l.strip()]
ALIASES = yaml.safe_load((DATA / "aliases.yaml").read_text())

def q(x):
    return json.dumps(x, ensure_ascii=False) if x is not None else "null"

def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")

def container_of(url):
    u = url.lower()
    if "arxiv.org" in u or u.endswith(".pdf"):
        return "pdf"
    if "huggingface.co" in u:
        return "hf_readme"
    return "blog"

def weight_class(r):
    if r["benchmark_canonical"] is None and r["prominence"]["type"] == "prose":
        return None
    if r["prominence"]["type"] == "headline":
        return "blog_headliner"
    dt = r["source_doc"]["doc_type"]
    return {"system_card": "system_card", "model_card": "model_card",
            "blog_headliner": "model_card"}[dt]

docs = collections.OrderedDict()
for r in ROWS:
    docs.setdefault(r["source_doc"]["url"], []).append(r)

doc_meta, id_for_url, seen = [], {}, set()
for url, rs in docs.items():
    sd = rs[0]["source_doc"]
    base = f"{slug(sd.get('model') or sd['lab'])}__{sd['doc_type']}"
    did = base if base not in seen else f"{base}__{sd.get('pub_date') or 'na'}"
    seen.add(did); id_for_url[url] = did
    default_wc = {"system_card": "system_card", "model_card": "model_card",
                  "blog_headliner": "model_card"}[sd["doc_type"]]
    doc_meta.append({"id": did, "lab": sd["lab"], "model": sd.get("model"),
                     "container": container_of(url), "default_weight_class": default_wc,
                     "url": url, "pub_date": sd.get("pub_date")})

docs_out = ["# documents.yaml - one entry per source document (DATA, not code).",
            "# container: pdf | hf_readme | blog. default_weight_class applies to every mention",
            "# unless the mention overrides it (e.g. a solo headline chart -> blog_headliner).",
            "schema_version: 1", "documents:"]
for d in doc_meta:
    docs_out += [f"  - id: {d['id']}", f"    lab: {d['lab']}", f"    model: {q(d['model'])}",
                 f"    container: {d['container']}", f"    default_weight_class: {d['default_weight_class']}",
                 f"    url: {q(d['url'])}", f"    pub_date: {q(d['pub_date'])}"]
(DATA / "documents.yaml").write_text("\n".join(docs_out) + "\n")

# blog headliner re-categorization sets (from reading each source blog)
HEADLINERS = {
 "anthropic/claude-fable-5-mythos-5__blog_headliner.yaml": {"FrontierCode"},
 "google_deepmind/gemini-3-5-pro__blog_headliner.yaml": set(),
 "google_deepmind/gemini-3-pro__blog_headliner.yaml": {
    "GPQA Diamond","HLE","ARC-AGI-2","MathArena","MMMU-Pro","Video-MMMU","SimpleQA",
    "Vending-Bench 2","SWE-bench Verified","Terminal-Bench 2.0","WebDev Arena"},
 "openai/gpt-5-4__blog_headliner.yaml": {
    "GDPval (wins or ties)","SWE-bench Pro","OSWorld-Verified","Toolathlon","BrowseComp",
    "WebArena-Verified","Online-Mind2Web","MMMU-Pro","OmniDocBench","MCP Atlas","tau2-bench"},
 "openai/gpt-5-5__blog_headliner.yaml": {
    "Terminal-Bench","SWE-bench Pro","GDPval (wins or ties)","OSWorld-Verified","tau2-bench",
    "GeneBench","Expert-SWE","BixBench"},
}

xroot = DATA / "extractions"
for url, rs in docs.items():
    did = id_for_url[url]; lab = rs[0]["source_doc"]["lab"]
    rel = f"{lab}/{did}.yaml"
    d_default = next(d["default_weight_class"] for d in doc_meta if d["id"] == did)
    heads = HEADLINERS.get(rel)     # None => keep migrated weight_class; set() or set => override
    lines = [f"# {did}", f"doc: {did}"]
    if len(rs) == 1 and rs[0]["benchmark_canonical"] is None and rs[0]["prominence"]["type"] == "prose":
        r = rs[0]
        lines += ["unreadable:", f"  reason: {q(r.get('review_reason') or r['benchmark_raw'])}",
                  f"  review_issue: {r.get('review_issue') if r.get('review_issue') else 'null'}"]
    else:
        lines.append("mentions:")
        for r in rs:
            raw = r["benchmark_raw"]; rep = r.get("reported") or {}
            wc = weight_class(r)
            if heads is not None:                         # re-categorized blog
                wc = "blog_headliner" if raw in heads else d_default
            lines.append(f"  - raw: {q(raw)}")
            if wc and wc != d_default:
                lines.append(f"    weight_class: {wc}")
            if rep.get("value") is not None:
                lines.append(f"    value: {rep['value']}")
                lines.append(f"    unit: {q(rep.get('unit'))}")
            if rep.get("model_config"):
                lines.append(f"    model_config: {q(rep['model_config'])}")
            if r.get("methodology_deviations"):
                lines.append("    methodology:")
                for m in r["methodology_deviations"]:
                    lines.append(f"      - {q(m)}")
    (xroot / lab).mkdir(parents=True, exist_ok=True)
    (xroot / lab / f"{did}.yaml").write_text("\n".join(lines) + "\n")

reg = collections.OrderedDict()
for r in ROWS:
    c = r["benchmark_canonical"]
    if not c:
        continue
    e = reg.setdefault(c, {"aliases": set(), "type": None, "domain": None})
    e["aliases"].add(r["benchmark_raw"]); e["type"] = r.get("type") or e["type"]; e["domain"] = r.get("domain") or e["domain"]
curated = {}
for b in ALIASES.get("benchmarks", []):
    c = b["canonical"]; curated[c] = b
    e = reg.setdefault(c, {"aliases": set(), "type": None, "domain": None})
    for a in b.get("aliases", []):
        e["aliases"].add(a)
    if not e["type"]:
        e["type"] = "agentic" if b.get("axis") == "agentic" else "chat"
reg_out = ["# registry.yaml - SINGLE source of truth for benchmark IDENTITY + classification.",
           "# raw -> canonical is deterministic exact/normalized alias lookup (never fuzzy).",
           "# type = agentic|chat; domain = subject. Harbor status is NOT here - it is derived",
           "# live by sync_harbor.py. 'notes'/'collision' are human documentation only.",
           "schema_version: 1", "benchmarks:"]
for c in sorted(reg):
    e = reg[c]; cu = curated.get(c, {})
    reg_out += [f"  - canonical: {c}", f"    type: {e['type'] or 'chat'}",
                f"    domain: {e['domain'] or 'knowledge'}",
                "    aliases: [" + ", ".join(q(a) for a in sorted(e["aliases"])) + "]"]
    if cu.get("vendor_proprietary"):
        reg_out.append("    vendor_proprietary: true")
    if cu.get("method_note"):
        reg_out.append(f"    notes: {q(cu['method_note'])}")
    if cu.get("review_reason"):
        reg_out.append(f"    collision: {q(cu['review_reason'])}")
(DATA / "registry.yaml").write_text("\n".join(reg_out) + "\n")
print("bootstrap: wrote registry.yaml, documents.yaml,", len(doc_meta), "extraction files")
