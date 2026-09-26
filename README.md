# RepoMind

A repository-intelligence system: mines Git + GitHub history to understand
who worked on what, where knowledge is concentrated, and where maintenance
risk may exist -- laying the groundwork for repository-aware, LLM-grounded
Q&A.

```
Data -> Structured Knowledge -> Retrieval -> LLM -> Repository Intelligence
```

See [docs/PROJECT.md](docs/PROJECT.md) for full status, module breakdown,
and quickstart commands, and [docs/DATA_MODEL.md](docs/DATA_MODEL.md) for
the entity schema and identity-resolution rules.

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then edit .env with your GitHub token
```

## Web interface

```bash
python -m ui     # then open http://127.0.0.1:8765
```

## Run the pipeline

```bash
python -m ingest.cli --repo pallets/flask
python -m ingest.github_cli --repo pallets/flask
python -m normalization.cli --repo pallets/flask
python -m database.cli --repo pallets/flask
pytest tests/ -v
```
