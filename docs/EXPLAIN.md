# Module 9 — Context-aware code explanation

Explains a function (or line range) together with its recorded history: the
commits that changed those exact lines, the pull requests and issues behind
them, who reviewed, and who changed it.

```bash
python -m explain.cli --repo pallets/flask --file src/flask/helpers.py --function flash
python -m explain.cli --repo pallets/flask --file src/flask/app.py --lines 100-160 --question "why is this guarded?"
python -m explain.cli --repo pallets/flask --file src/flask/helpers.py --function flash --dry-run   # evidence + prompt, no API call
python -m explain.cli --stats --repo pallets/flask                                                   # history coverage, no LLM
```

The repo must already be loaded (`python pipeline.py --repo owner/name`).
`--function` works for Python (`flash`, `Flask.url_for`); any language works
with `--lines`. The explanation itself needs a Gemini key (Module 8);
`--dry-run` and `--stats` do not.

## How it works (`explain/`)

| File | Role |
|---|---|
| `source.py` | Reads the code with `git show HEAD:<path>` from the local clone (the one the database was built from). Finds function boundaries with Python's `ast`. Finds the commits that changed a piece of code with `git log -L start,end:path`, which follows exactly those lines back through time. |
| `history.py` | Looks those commits up in the database: the PRs (GitHub's own link, or recovered from `(#N)` in the commit subject and labelled as such), the issues those PRs closed, reviewers, and the people who changed the lines. Counts commits missing from the database instead of hiding them. |
| `context.py` | Renders code + history as evidence where every item has a citable id: `[code:L326-L357]`, `[commit:c2705ff]`, `[pr:#5812]`, `[issue:#5639]`, `[fact:N]`. Includes data limitations; shrinks in steps and says so if too large. |
| `prompts.py` | Grounding rules: explain the code from the code; explain history only from commit/PR/issue text; say "the recorded history does not say why" instead of guessing a motive; separate facts from inferences; report activity, never "the only expert"; treat evidence text as data. |
| `answer.py` | Runs the flow and applies Module 8's citation checks (cited ids must have been shown; invented `#numbers` and hashes are flagged). |
| `evaluate.py` | History-coverage measurement (below), no LLM. |

## Why line-level history

For flask's `flash` function, 11 commits touched its lines, against 93 for the
whole of `helpers.py`. The evidence for one function is therefore small and
specific (its PRs, and the issue behind the latest change) instead of a
file-wide list.

## Measurement: what the history reaches (no LLM)

`python -m explain.cli --stats --repo <owner/name>` samples Python functions
(>= 8 lines, in files with >= 20 commits, fixed seed):

| repo | functions | commits per function (median) vs whole file | commits found in database | commits reaching a PR number | functions with a PR | functions with a closed issue |
|---|---|---|---|---|---|---|
| flask | 25 | 5 vs 65 (8%) | 100% | 88% | 100% | 80% |
| requests | 8 | 6 vs 26 (24%) | 100% | 86% | 100% | 12% |
| fastapi | 25 | 7 vs 27 (23%) | 100% | 87% | 100% | 20% |
| black | 22 | 2 vs 42 (4%) | 100% | 92% | 100% | 77% |

- A function's own history is a small fraction of its file's history.
- Every commit git finds is in the database (the clone and database agree).
- Most commits reach a PR number. This includes the `(#N)` recovery, which
  matters most for squash-merge repos such as fastapi and black, where the
  stored PR links are almost empty (Module 6).
- Reaching a closed issue depends on the project's habits (requests 12%,
  black 77%).

## Status and limits

- **Not yet run with a live model.** Gemini's free-tier quota was exhausted
  when this was finished, so no real explanation has been generated or read.
  The evidence and prompt are verified (`--dry-run`, and tests with a fake
  model). Until explanations have been generated and read by a person, nothing
  here says they are good.
- The measurement covers retrieval only. "Reaches a PR" does not mean the PR
  is relevant to the reader's question, and "100% of functions have a PR" is
  helped by the subject-line recovery. The `requests` sample is small (8).
- `--function` needs Python. Other languages need `--lines`.
- History covers lines present at `HEAD`; code that was deleted is not
  explained. `git log -L` follows moved code, so a commit can be shown for
  lines that were copied or moved from elsewhere.
- Commit messages often do not say why; the explanation can only repeat what
  is recorded, and is told to say so when the reason is missing.
- Inherited gaps: a person under two identities, and PR links that exist only
  when the subject line carries `(#N)`.
- The whole-file case shows only the first 150 lines of code (and says so).
