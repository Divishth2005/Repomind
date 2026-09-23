# RepoMind — working notes for Claude

Full spec: the original build plan PDF this project was scaffolded from.
Living status + module list: `docs/PROJECT.md`. Entity/identity details:
`docs/DATA_MODEL.md`.

## Rules for this repo

1. **Inspect before modifying.** Raw data in `data/raw/` and the normalized
   output in `data/processed/` are both regeneratable — check
   `docs/PROJECT.md`'s status table before redoing a module that's already
   marked done.
2. **Never mutate raw data.** `data/raw/` is written once by `ingest/` and
   read-only after that.
3. **Never commit or print `GITHUB_TOKEN`.** It lives in `.env` (gitignored)
   and is loaded via `python-dotenv` in `ingest/github_client.py` only.
4. **Don't define expertise as commit count.** `database/queries.py::top_contributors`
   is explicitly labeled a signal, not a score — Module 4
   (`analysis/`, not yet built) is where real knowledge/concentration
   metrics get designed and evaluated.
5. **Build one module at a time, run `pytest tests/ -v` after each.**
6. **Preserve provenance.** Every normalized record needs a
   `raw_source_reference` back to its raw JSONL origin.

## Commands

```bash
source .venv/bin/activate
python -m ingest.cli --repo <owner/name>          # Module 0a
python -m ingest.github_cli --repo <owner/name>     # Module 0b (needs .env)
python -m normalization.cli --repo <owner/name>      # Module 1
python -m database.cli --repo <owner/name>            # Module 2
pytest tests/ -v
```

## Next module to build

Module 4 — Knowledge Concentration Metrics (see `docs/PROJECT.md` status table).
