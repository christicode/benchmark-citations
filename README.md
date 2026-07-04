# benchmark-citations

Tracks **benchmark citations** across the LLM ecosystem. The topline entity is the
**benchmark** (not the model): for each benchmark we track how often it's cited, of
what kind, by which labs/models, and with what methodology deviations.

## Scope
- Window: **2025-09** → present, then forward continuously. GPT-5 (2025-08-13) is
  included as a pre-window **comparison anchor**.
- Labs: Big-5 (Anthropic, OpenAI, Google DeepMind, Meta, xAI) + open-weight leaders
  (DeepSeek, Qwen, Mistral, Moonshot, Z.ai). **Labs are config, not code** — see
  [`labs.yaml`](labs.yaml). Onboard a lab by editing that file only.
- Sources: model cards, system cards, headline release blogs. For open-weight models
  the **Hugging Face README** is accepted as the card equivalent.

## How it works
```
feeds → candidates → human promotes → extract → normalize → rank → dashboard
```
1. **Discover** docs by crawling each lab's `source_index_urls` and diffing against
   what's already extracted. (We enumerate from indexes, never from guessed model
   names — that's how the Mythos/Fable line was originally missed.)
2. **Extract** verbatim benchmark mentions + methodology (scaffold, harness, n,
   effort, tools, model config) per [`schema/extraction_schema.json`](schema/extraction_schema.json).
3. **Normalize** names deterministically via [`data/aliases.yaml`](data/aliases.yaml).
   Anything unmatched is **flagged for human review as a GitHub issue** — never guessed.
4. **Rank** conversion candidates with [`scripts/rank.py`](scripts/rank.py):
   usage (prominence-weighted × lab diversity) + saturation headroom. Agentic-vs-static
   is a **separate surfaced axis**, not folded into the score. Benchmarks already in
   Harbor are excluded.
5. **Dashboard** (`docs/`) visualizes rising usage, rising saturation, and top
   conversion candidates with a one-line "why now".

## Harbor cross-reference
Harbor's `registry.json` is fetched **live from `main`** each run
(`harbor-framework/harbor`) — never cached in-repo. Dedupe by `(name, version)`;
names are **not** unique (`kumo`×4, `swe-lancer-diamond`×3).

## Human-review queue = GitHub Issues
Chart-only cards, unfetchable PDFs, alias collisions, and secondary-only numbers are
filed as issues labelled `needs-human-review`. See `data/review_queue.yaml`.

## Raw source archive
The raw source PDFs live in the companion private repo
[`benchmark-citations-sources`](https://github.com/christicode/benchmark-citations-sources)
(Git LFS), with provenance + sha256 in its `manifest.yaml`.

## Guardrails
Local commits are free; **publishing (repo creation, push, dashboard, issues) always
requires explicit human confirmation.** Never fabricate a citation or methodology detail.
