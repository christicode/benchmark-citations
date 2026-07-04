# PaperTrail <https://autobenchmark.ai> 

Tracks **benchmark citations** across the LLM ecosystem: for each benchmark we track how often it's cited, where it's cited, by which labs/models, and with what methodology deviations.

## Scope
- Backfilled to 2025-08, then forward continuously. 
- Labs: Big (Anthropic, OpenAI, Google DeepMind, Meta, xAI) + open-weight leaders
  (DeepSeek, Qwen, Mistral, Moonshot, Z.ai). Onboard a lab by editing [`labs.yaml`](labs.yaml)
- Sources: Primary sources (Headline release blogs > Model cards/System cards). For open-weight models the Hugging Face README is accepted. 

## How it works

1. **Discover** docs by crawling each lab's `source_index_urls` and checking against what's already been extracted. 
2. **Extract** verbatim benchmark mentions + methodology (scaffold, harness, n, effort, tools, model config) per [`schema/extraction_schema.json`](schema/extraction_schema.json).
3. **Normalize** names via [`data/aliases.yaml`](data/aliases.yaml). Anything unmatched is **flagged for human review as a GitHub issue**. 
4. **Rank** adapter candidates with [`scripts/rank.py`](scripts/rank.py):usage + saturation headroom. Benchmarks already in Harbor are excluded.

**Details:**

1. Cross-reference Harbor's `registry.json` from `main` each run (`harbor-framework/harbor`) for canonical view of Harbor-supported benchmarks. 
2. Issues are created for human review: E.g. Mistral publishes evals as chart-only cards; human review helps ensure accurate extraction from charts. 
3. Raw source archive: The raw source PDFs live in the companion private repo [`benchmark-citations-sources`](https://github.com/christicode/benchmark-citations-sources)(Git LFS). 
4. Guardrails: Publishing (repo creation, push, dashboard, issues) always requires explicit human confirmation. Never fabricate a citation or methodology detail.
