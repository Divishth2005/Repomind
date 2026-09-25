# Module 7 — Structured + Text Retrieval

Finds the repository evidence needed to answer a question, and returns it
with citable identifiers. It does not call an LLM; Module 8 will build the
LLM context from what this returns.

```bash
python -m retrieval.cli --repo pallets/flask "Who reviewed changes to src/flask/app.py?"
python -m retrieval.cli --repo tiangolo/fastapi "Which PR changed fastapi/applications.py recently?"
python -m retrieval.cli --repo pallets/flask "what is #3272"
python -m retrieval.cli --repo pallets/flask "bus factor of docs/patterns"
python -m retrieval.cli --repo pallets/flask --json "why was BadRequestKeyError changed?"
python -m retrieval.cli --eval --repo pallets/flask --repo psf/black     # retrieval evaluation
```

(The repo must already be loaded with `python pipeline.py --repo owner/name`.)

## What was built (`retrieval/`)

| Part | Role |
|---|---|
| `query.py` | Rule-based interpretation: intent (contributors, reviewers, history, why/which PR, risk, issue links, lookup), files/directories mentioned, `#N` references, commit hashes, developer names. Anything else falls back to text search. |
| `structured.py` | Answers from the relational model: contributors, reviewers, history, PRs touching a file/directory, PR / issue / commit context, developer activity. Every item carries its SHA or PR/issue number. |
| `text_search.py` | BM25 over commit messages, PR and issue text, and review comments. |
| `ranking.py` | Reciprocal Rank Fusion to merge ranked lists whose raw scores aren't comparable. |
| `hybrid.py` | `Retriever.retrieve(question)`: runs the structured queries the intent needs, and text search restricted to items that touch the named file/directory (or the whole repo when none is named). Also pulls the Module 4/5 concentration and risk signals for a file or directory on demand. Returns `answers`, ranked `evidence` (each with a `ref` like `commit:ab12cd3`, `pr:#123`), and `notes` about data gaps. |
| `evaluate.py` | Retrieval evaluation (below). |

Two behaviours worth knowing:

- **Squash-merge recovery at query time.** Where PRs aren't linked to
  commits (Module 6 finding), PR numbers are recovered from `(#N)` at the end
  of commit subjects, and answers label these links `subject` rather than
  `linked`. The stored data is unchanged, so the Module 6 linkage figures
  still stand. Example: fastapi has 12 of 6,359 PRs linked to commits, yet
  questions about a fastapi file still return its PRs this way.
- **Honest notes.** Answers state when PR data is mostly unlinkable, when a
  file name matches several paths (renames such as `flask/app.py` →
  `src/flask/app.py`), and that a person may appear under a Git name and a
  separate GitHub login.

## Text-search evaluation

Task: given only an **issue title**, find the pull request that closed it.
Ground truth is GitHub's own "closes #N" links, so it doesn't depend on the
text search. Up to 400 issues per repo, sampled with a fixed seed.
Reproduce with `python -m retrieval.cli --eval --repo <owner/name> ...`.

| repo | queries | corpus (PRs) | R@1 | R@5 | R@10 | MRR | R@10 (PR title only) | chance R@10 |
|---|---|---|---|---|---|---|---|---|
| flask | 300 | 2,910 | 46% | 68% | 76% | 0.56 | 71% | 0.4% |
| requests | 242 | 3,095 | 33% | 52% | 59% | 0.42 | 54% | 0.4% |
| fastapi | 142 | 6,359 | 35% | 61% | 69% | 0.47 | 70% | 0.3% |
| ripgrep | 179 | 1,167 | 42% | 64% | 72% | 0.52 | 64% | 1.1% |
| black | 400 | 2,469 | 34% | 51% | 57% | 0.42 | 62% | 0.5% |
| express | 90 | 2,666 | 59% | 79% | 81% | 0.68 | 77% | 0.8% |
| cobra | 195 | 1,217 | 44% | 66% | 73% | 0.54 | 67% | 1.0% |

(ora has too few linked pairs to evaluate.)

- The true PR is in the top 10 for 57–81% of issues, against about 1% for
  chance, so the text search is doing real work.
- Adding PR body text to the title helps in five repos (+4 to +8 points at
  R@10) but **hurts in fastapi and black** (black R@10 62% → 57%; fastapi R@1
  47% → 35%). The cause is not established.

### Do we need embeddings?

Of the queries that missed the top 10, the share where the query and the true
PR text share **no words at all** (the only failure embeddings could clearly
fix) was 16% (flask), 32% (requests), 11% (fastapi), 22% (ripgrep), 18%
(black), 47% (express) and 21% (cobra). As a share of *all* queries that is
only 4–13%. Most misses share some words and are ranked lower than 10, which
is a ranking problem, not a vocabulary problem. On this evidence embeddings
are not the first thing to try, so **embedding-based retrieval was not
implemented**. This does not show embeddings wouldn't also improve ranking;
that wasn't tested.

## Limitations

- **Lexical only.** Text search cannot match a query and a document that
  share no words (black issue #711 "Python 3.8 — PEP 572 compatibility" and
  its PR #935 "Add support for walrus operator" have no words in common).
- **Ground truth is imperfect.** Only PRs that explicitly link an issue are
  covered, and some links are loose (requests issue #1 "Cookie support?" is
  linked to PR #1741, "Significantly reduce library footprint"). Such cases
  count as misses, so the numbers understate usefulness for them. The task
  (issue title → PR) is also only one kind of question.
- **Structured answers were checked by unit tests and by hand on flask,
  fastapi and ripgrep, not scored at scale.** Query interpretation is
  keyword rules; its accuracy on unseen phrasings has not been measured.
- **Identity split persists.** `what did BurntSushi work on?` reports 0
  commits, because his commits are under the Git name "Andrew Gallant" and
  his GitHub login has only PRs and reviews. The answer says so in a note but
  does not fix it (Module 6 next steps).
- **Renames and the default branch only.** A file's history before a rename
  is not followed; matching paths are listed separately.
- **`(#N)` recovery is a heuristic** and only works for repos that use
  GitHub's squash-merge subject format.
- The context builder (turning results into an LLM prompt) belongs to
  Module 8 and is not built here.
