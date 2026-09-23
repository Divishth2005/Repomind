# Data Model

## Raw layer (`data/raw/<repo>/`)

- `commits.jsonl` — one record per commit on HEAD: sha, parents, author,
  committer, timestamps, subject/body, per-file insertions/deletions. Written
  by `ingest/extract_commits.py`.
- `github/issues.jsonl`, `github/pull_requests.jsonl` (with nested reviews),
  `github/labels.jsonl` — raw GraphQL response nodes, one per line, written
  by `ingest/github_acquire.py`. `github/checkpoint.json` tracks the last
  cursor consumed per resource so acquisition can resume after an
  interruption instead of restarting.

Known limitations, inherited from `git`'s own behavior rather than a bug in
this pipeline:
- Extraction follows the default branch / HEAD only.
- Merge commits frequently carry an empty file list.
- Renames appear in git's own raw form (a delete + an add, unless git's
  similarity heuristic reports it otherwise) rather than as an explicit
  `old_path -> new_path` mapping.

## Normalized layer (`data/processed/<repo>/`)

Entities (see `normalization/schema.py` for exact fields):

| Entity | Key | Notes |
|---|---|---|
| Repository | `repository_id` (`owner/name`) | |
| Developer | `developer_id` | See identity resolution below |
| File | `file_id` | Deduped by `(repository_id, path)` |
| Commit | `commit_id` (= sha) | `raw_source_reference` = the sha itself |
| CommitFile | `commit_file_id` | Commit <-> File edge with additions/deletions |
| Issue | `issue_id` | `raw_source_reference` = `issues.jsonl#<number>` |
| PullRequest | `pr_id` | carries `commit_shas` and `closing_issue_numbers` |
| Review | `review_id` | belongs to a `pr_id` |
| Label | `label_id` | |

## Identity resolution (`normalization/identity.py`)

The hard problem: the same human shows up as different strings in different
places (`"John Doe"`, `"john.doe"`, a GitHub login, different emails per
machine). Per the build plan, resolution here is **conservative** — an
identity is only merged when there's a concrete signal, not a guess:

1. **GitHub no-reply commit email** (e.g.
   `49699333+dependabot[bot]@users.noreply.github.com`) directly encodes the
   GitHub login. This is the *only* signal strong enough to link a Git
   identity to a GitHub identity in this pipeline, since GitHub itself
   generated the address — confidence `high`.
2. **Same email, case-insensitive**, clusters commits to one developer —
   confidence `medium`.
3. **No email at all** falls back to clustering by raw name string —
   confidence `low`, since two different people can share a display name.
4. **GitHub-only identities** (a PR/issue/review author with no matching
   commit email) get their own developer keyed by login — confidence
   `medium`, source `github_login_only`.

Every `Developer` record carries `identity_confidence` and
`identity_sources` so downstream analysis (and the final report) can be
honest about how solid each identity actually is, instead of presenting
resolved identities as ground truth.

**Bots** (`[bot]` suffix, `dependabot`, `github-actions`, etc.) are flagged
via `is_bot` rather than dropped, so knowledge-concentration metrics (Module
4) can exclude them without losing the record.

## Relational layer (`database/schema.sql`)

Direct translation of the normalized entities into SQLite tables, plus two
materialized edge tables (`pr_commit`, `pr_issue`) so the many-to-many
PR<->Commit and PR<->Issue relationships — stored as JSON arrays on
`pull_request` for provenance — are also directly joinable/indexable.

The database is a **derived artifact**: `python -m database.cli` rebuilds it
from `data/processed/` at any time. Nothing is hand-edited in SQLite.

## Provenance chain

```
raw commit JSONL record (keyed by sha)
        |
        v
normalized Commit.raw_source_reference = sha
        |
        v
commit_ table row (SQLite)
```

Every table in the relational layer can be traced back to the exact raw
record it came from.
