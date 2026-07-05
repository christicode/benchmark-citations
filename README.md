# PaperTrail
<https://autobenchmark.ai>

Tracks **benchmark citations** across the LLM ecosystem: for each benchmark we track how often
it's cited, where it's cited, by which labs/models, and with what methodology deviations.

## Scope
- Backfilled to 2025-09, then forward continuously.
- Labs: Big-5 (Anthropic, OpenAI, Google DeepMind, Meta, xAI) + open-weight leaders
  (DeepSeek, Qwen, Mistral, Moonshot, Z.ai). Onboard a lab by editing [`labs.yaml`](labs.yaml).
- Sources: primary sources only — release blogs, model cards, system cards. For open-weight
  models the Hugging Face README is accepted.

## Data model (flat files, no database, no data-in-code)
Everything is human/agent-editable flat data; the scripts are pure transforms.

- [`data/registry.yaml`](data/registry.yaml) — **single source of truth for benchmark identity**:
  `raw name -> canonical` aliases (deterministic, never fuzzy), plus `type` (agentic|chat),
  `domain`, and curated collision notes.
- [`data/documents.yaml`](data/documents.yaml) — one entry per source document (lab, model,
  container, url, pub_date, `default_weight_class`).
- `data/extractions/<lab>/<id>.yaml` — the benchmark **mentions** extracted from each document
  (raw name, optional `weight_class` override, score, model_config, methodology).
- [`data/citations.jsonl`](data/citations.jsonl) — **generated** by `scripts/build.py`; one record
  per (document, benchmark). Never hand-edited.
- `data/harbor_adapters.json` — generated live-Harbor snapshot (fallback cache).

## Source scoring — three distinct classes
Each mention is weighted by *how* it's cited, decoupled from the physical document (a single blog
can carry both a headliner chart **and** a model-card comparison table):

| class | points | what it is |
|---|---|---|
| `blog_headliner` | 3 | a chart or paragraph about a **single** benchmark in a release blog |
| `model_card` | 2 | a multi-benchmark comparison table (standalone card **or** a table in a blog) |
| `system_card` | 1 | a row in the long-form system-card paper (no table-size discount) |

Weight is taken as **max per (document, model)**, then summed across documents — so the same
benchmark headlined in 3 different blogs counts 3+3+3 = 9. (There is no composite priority score
yet — that's a deferred project.)

## Pipeline
1. **Discover** ([`scripts/discover.py`](scripts/discover.py)) — the searcher: crawls each
   `labs.yaml` feed + the Hugging Face org API, filters via each lab's `candidate_patterns`,
   diffs against tracked docs, and writes `data/candidates.jsonl` for **human promotion** (no
   extraction, no auto issue-opening). Runs on a schedule via the `watch` workflow.
2. **Extract** promoted docs → verbatim benchmark mentions + methodology into `data/extractions/`
   ([`scripts/extract.py`](scripts/extract.py) assists detection; unmatched names are flagged).
3. **Build** [`scripts/build.py`](scripts/build.py): extractions × registry → `citations.jsonl`.
4. **Sync Harbor** [`scripts/sync_harbor.py`](scripts/sync_harbor.py): fills `harbor_*` fields from
   `harbor-framework/harbor` `registry.json` + `adapters/`, fetched **live from main** each run.
5. **Dashboard** `scripts/build_dashboard.py` → `docs/` (out of current scope).

`scripts/rank.py` prints a per-benchmark citation summary (data-QA lens, no priority score).
`scripts/review_queue.py` lists the open `needs-human-review` issues (the review queue's source
of truth).

## Notes
- Unmatched benchmark names and unreadable/gated docs are **flagged for human review as GitHub
  issues** — never silently guessed.
- Raw source PDFs live in the companion private repo
  [`benchmark-citations-sources`](https://github.com/christicode/benchmark-citations-sources)
  (Git LFS) with an sha256 manifest.
- Guardrails: publishing (repo creation, push, dashboard, issues) always requires explicit human
  confirmation. Never fabricate a citation or methodology detail.
