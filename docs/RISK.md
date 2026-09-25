# Module 5 — Bus-Factor / Maintenance-Risk Analysis

Question: where does the repository evidence suggest maintenance risk,
because work is concentrated in few active people or because much of the
history came from people who have stopped contributing?

This is a **derived risk indicator built from Module 4's activity data, not
a fact about any person**. The output never says someone "is the only
expert"; it says the available evidence shows certain risk signals. None of
the thresholds has been validated yet (Module 6).

Run (repo must already be loaded with `python pipeline.py --repo owner/name`):

```bash
python -m analysis.risk_cli --repo pallets/flask [--sensitivity] [--active-days 365] [--coverage 0.5]
```

Output: a ranked table plus `data/processed/<repo>/risk_depth2.json` with the
evidence and every signal per component.

## Definitions

- **Active developer**: committed within `--active-days` (default 365) of the
  repo's latest commit ("as of" date, not today, so results are reproducible).
- **Bus factor** (`bus_factor` in `analysis/bus_factor.py`): the smallest
  number of developers whose combined share of activity reaches `--coverage`
  (default 50%). Reported over *recent* commits (`bus_factor_active`) and over
  all history (`bus_factor_lifetime`). 1 = a single developer covers that
  share.
- **Departed share**: fraction of all-time commits in the component made by
  developers with no commits in the active window.

## Signals (independent, each recorded with its evidence)

| Signal | Kind | Triggers when |
|---|---|---|
| `single_active_maintainer` | concentration | active bus factor is 1 **and** the top active developer has >= `--dominant-share` (default 60%) of recent commits |
| `historical_knowledge_departed` | knowledge loss | departed share >= `--departed-threshold` (default 50%) |
| `low_reviewer_diversity` | concentration | <= 1 distinct reviewer, evaluated only when the component has >= 3 linked review events; otherwise listed under `not_evaluated` |

## Levels (a plain count of triggered signals, so the reasoning is visible)

| Level | Rule |
|---|---|
| `high` | 2 or more signals triggered |
| `medium` | exactly 1 |
| `low` | 0 |
| `dormant` | no commits in the active window (no ongoing maintenance activity — not the same as risky or safe) |
| `insufficient_evidence` | fewer than `--min-commits` (default 5) commits |

Ranking: level first, then most recent activity, so components that are both
risky and actively changing come first.

## Assumptions (guesses, not tuned)

Active window 365 days, coverage 50%, dominant share 60%, departed 50%,
equal weight per signal, level cut-offs at 1 and 2 signals.

## First results (pallets/flask, depth 2, as of 2026-09-08)

5 high, 6 medium, 0 low, 28 dormant, 6 insufficient evidence. In every
flagged component the top active developer is David Lord with 80–100% of
recent commits; the high-level ones (`tests`, `docs`, `docs/patterns`,
`docs/tutorial`, `docs/deploying`) also have 51–72% of their history from
developers no longer active.

Sensitivity (`--sensitivity`, number of high-risk components):

| active window | dominant >= 50% | >= 60% | >= 70% |
|---|---|---|---|
| 180 days | 4 | 4 | 4 |
| 365 days | 5 | 5 | 5 |
| 730 days | 5 | 5 | 5 |

The dominant-share threshold changes nothing on flask (the flagged
components are all >= 80%), so this sweep does not discriminate; the active
window matters slightly more. Different repositories are needed to say more.

## Known limitations

1. **Renames split history.** flask moved from `flask/` to `src/flask/`
   around 2019–2020. Renames aren't tracked (Module 0a), so the old path is
   counted as a separate, now-dormant component and `src/flask`'s departed
   share (23%) is understated. The old `flask/` path is one confirmed case; how many of the
   28 dormant components are similar old layouts has not been checked.
2. **All-or-nothing on one person.** No flask component is `low` while its
   activity window is a year; either the project really is maintainer-
   concentrated or the rules are too sensitive. That can't be resolved
   without other repositories and some independent judgement (Module 6).
3. **Identity.** Commit-based signals are unaffected by the "David Lord" /
   `davidism` split in flask (verified: all his commits are under one
   identity), but a project where one person commits under several
   identities would look less concentrated than it is. The reviewer signal
   uses GitHub logins.
4. **Review data is partial** (about half of PRs link to files), so
   `low_reviewer_diversity` is rarely evaluated.
5. **Default branch only; bots excluded; no ground truth** — "risk" means
   risk signals in activity data, not observed maintenance failures.
