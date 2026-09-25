# RepoMind

A repository-intelligence system that mines Git + GitHub development history
to understand who worked on what, where knowledge is concentrated, where
maintenance risk may exist, and how an LLM can answer repository-specific
questions grounded in real evidence.

```
Data -> Structured Knowledge -> Retrieval -> LLM -> Repository Intelligence
```

The LLM is not the foundation. The repository-specific data and the
knowledge/retrieval layer come first.

## Status

| Module | Status |
|---|---|
| 0a — Local Git ingestion | Done |
| 0b — GitHub GraphQL acquisition | Done (pending a valid `GITHUB_TOKEN`) |
| 1 — Normalization & identity resolution | Done |
| 2 — Database & relationship construction | Done |
| 3 — Knowledge map visualization | Done |
| 4 — Knowledge concentration metrics | Done (see docs/METRICS.md) |
| 5 — Bus-factor / risk analysis | Not started |
| 6 — Multi-repo evaluation | Not started |
| 7 — Structured + semantic retrieval | Not started |
| 8 — RAG / LLM integration | Not started |
| 9 — Context-aware code explanation | Not started |
| 10 — Engineering assistance | Not started |
| 11 — UI | Not started |

## Demo repositories

- `pallets/flask` — rich, multi-year, multi-contributor open-source history
  (5,557 commits, 2,767 issues, 2,910 PRs).
- `Divishth20/DEVOPS-LAB-1` — one of the account's own repos, run to prove
  the pipeline is generic and not hardcoded to flask. The same SQLite
  database holds both repos side by side (rows are keyed by
  `repository_id`, so loading a second repo never overwrites the first).

The `GITHUB_TOKEN` in `.env` is only used to *authenticate* API calls (for a
5,000/hour rate limit instead of 60/hour unauthenticated) — it does not
restrict which repo can be analyzed. Any public `owner/name` works.

## One-command pipeline

```bash
python pipeline.py --repo <owner/name>            # full pipeline: ingest -> normalize -> db -> knowledge map
python pipeline.py --repo <owner/name> --skip-github  # git-only, no token needed
```

## Quickstart (individual stages)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Module 0a: clone + extract commit history
python -m ingest.cli --repo pallets/flask

# Module 0b: GitHub issues/PRs/reviews/labels (needs .env with GITHUB_TOKEN)
python -m ingest.github_cli --repo pallets/flask

# Module 1: normalize raw data into clean entities + identity resolution
python -m normalization.cli --repo pallets/flask

# Module 2: load into SQLite, run smoke-test relationship queries
python -m database.cli --repo pallets/flask

# Module 3: build the developer <-> file knowledge-map visualization
python -m visualization.cli --repo pallets/flask
open data/flask_knowledge_map.html

# Module 4: knowledge-concentration metrics (repo must be loaded first)
python -m analysis.cli --repo pallets/flask

# Tests
pytest tests/ -v
```

## Directory layout

```
ingest/            Module 0a/0b -- raw acquisition (Git + GitHub GraphQL)
normalization/      Module 1 -- raw JSONL -> normalized entities + identity resolution
database/            Module 2 -- SQLite schema, loader, relationship queries
visualization/        Module 3 -- developer <-> file knowledge map (HTML)
analysis/              Module 4 -- knowledge-concentration metrics
data/raw/             Raw, immutable acquisition output (JSONL)
data/processed/        Normalized entities (JSONL) -- regeneratable from raw
data/repomind.sqlite     Derived queryable database -- regeneratable from processed/
tests/                  pytest suite
docs/                    This file + DATA_MODEL.md + METRICS.md
```

## Design rules this project follows

1. **Raw data is immutable.** Nothing in `normalization/` or `database/`
   ever writes back into `data/raw/`.
2. **Every normalized record is traceable to a raw record** via
   `raw_source_reference` (a commit SHA, or `<file>.jsonl#<github_number>`).
3. **Identity resolution is conservative.** See `docs/DATA_MODEL.md` for the
   exact rules. An identity that can't be resolved with a concrete signal is
   kept separate, not guessed into a merge.
4. **Commit count is not expertise.** Raw contributor counts (see
   `database/queries.py::top_contributors`) are a signal only -- Module 4
   (`analysis/`) defines candidate concentration metrics, and its combined
   score is a hypothesis to be evaluated, not a measure of expertise.
5. **Bots are flagged, not deleted**, so they can be excluded from
   human-knowledge analysis without losing the record.
