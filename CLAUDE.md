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
   (`analysis/`, documented in `docs/METRICS.md`) holds the candidate
   concentration metrics; its multi-signal score is a hypothesis, not
   a measure of expertise.
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
python -m analysis.cli --repo <owner/name>            # Module 4 (repo must be loaded first)
python -m analysis.risk_cli --repo <owner/name>       # Module 5
python -m evaluation.acquire && python -m evaluation.cli   # Module 6 (long download)
python -m retrieval.cli --repo <owner/name> "<question>"  # Module 7
python -m llm.cli --repo <owner/name> "<question>"        # Module 8 (needs GEMINI_API_KEY in .env; --dry-run does not)
python -m explain.cli --repo <owner/name> --file <path> --function <name>   # Module 9 (--dry-run / --stats need no key)
python -m assist.cli --repo <owner/name> --file <path> --function <name>   # Module 10 (--dry-run / --eval need no key)
python -m ui                                          # Module 11: web interface at http://127.0.0.1:8765
python pipeline.py --repo <owner/name>                # Modules 0a-3 in one go
pytest tests/ -v
```

## Next module to build

All 11 modules are built. Remaining work is validation, not features: Modules 8-10 and the UI have not shown a successful live Gemini answer yet (quota); do that, read the answers, and consider the open issues below. Modules 9 and 10 (`explain/`, `assist/`) have not produced a live model answer yet (Gemini quota); read one of each when it allows. Module 9 (`explain/`) is built but no live model explanation has been generated yet; run one and read it when the Gemini quota allows. Module 8 (`llm/`) works with Gemini (key in `.env`); its evaluation is small, so read saved answers before trusting it, and re-run `--eval` after the free-tier quota resets (the last run was cut off after a fix).
Open issues from `docs/EVALUATION.md` worth fixing first if results matter: squash-merge PR linkage and Git↔GitHub identity linking.
