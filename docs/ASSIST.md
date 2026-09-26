# Module 10 — Engineering assistance

A history-based briefing for a developer who is about to change a piece of
code: what went wrong here before, which files and tests usually change with
it, related issues, and who has worked on it. It does not write or suggest
code; it lists things to check, each with a citable source.

```bash
python -m assist.cli --repo pallets/flask --file src/flask/helpers.py --function url_for --dry-run   # evidence + prompt, no API call
python -m assist.cli --repo pallets/flask --file src/flask/app.py --lines 100-160 --plan "make X async"   # needs a Gemini key
python -m assist.cli --eval --repo pallets/flask --repo psf/black                                    # model-free checks
```

The repo must already be loaded (`python pipeline.py --repo owner/name`).

## What is in the briefing (`assist/`)

| Part | Where it comes from |
|---|---|
| Change history of the code | Module 9: commits that changed exactly those lines |
| Changes that **look like fixes** | `bugfix.py`: fix/bug/crash/regression wording in the commit subject or PR title, or a closed issue labelled as a bug. The reason is shown with each one. |
| Files and tests that usually change with it | `cochange.py`: from all past commits, how often another file changed in the same commit. Test files and housekeeping (changelog, lockfiles, CI config) are listed separately. |
| Open issues mentioning the file | text match of the path in open issues (may be unrelated) |
| People and signals | authors and reviewers of the related changes; Module 5's risk signals for the file |

`context.py` gives each item a citable id (`[commit:..]`, `[pr:#..]`, `[issue:#..]`,
`[cochange:N]`, `[fact:N]`) and lists the data limitations; `prompts.py` tells the
model to use only that evidence, label inferences, treat co-change as
association not dependency, say "looks like a fix" and never "is a fix", never
claim anyone is the only expert, and not to write code. Module 8's citation
checks are reused (cited ids must have been shown). The model is optional
input: an optional `--plan` is passed on but marked as unverified.

## Checks that need no LLM

**Does past co-change predict future co-change?** Commits are split by time
(first 70% to learn, last 30% to test). For each test commit and each file in it
with at least 3 earlier commits, the top-5 co-change partners are predicted
from the earlier data only and compared with what actually changed alongside.
Baseline: the 5 most frequently changed files overall. The second variant
removes changelogs, lockfiles, requirements files and CI config first.

| repo | hit@5 co-change | hit@5 popular files | co-change precision | popular precision |
|---|---|---|---|---|
| flask | 50% | 30% | 17% | 8% |
| requests | 73% | 53% | 31% | 23% |
| fastapi | 69% | 37% | 29% | 8% |
| ripgrep | 55% | 19% | 29% | 4% |
| black | 69% | 35% | 25% | 10% |
| express | **47%** | **49%** | 22% | 14% |
| cobra | 72% | 46% | 32% | 12% |

(Without-changelog/CI variant; the all-files variant is similar and is printed by
`--eval`. ora is too small to test.) Co-change beats the baseline in 6 of 7
repos, by 20 to 36 points of hit rate; **in express it does not** (47% vs 49%).
"hit@5" counts a hit if any of the five predicted files changed, so it is
lenient; precision shows that most individual predictions are still wrong
(17–32% right).

**Does "looks like a fix" wording agree with GitHub's bug labels?** Compared on
PRs that closed a labelled issue (positives: closed a bug-labelled issue):

| repo | bug-labelled PRs caught | non-bug PRs it wrongly fires on | precision |
|---|---|---|---|
| requests | 70% of 71 | 9% of 32 | 94% |
| fastapi | 69% of 68 | 29% of 146 | 52% |
| ripgrep | 48% of 67 | 15% of 71 | 74% |
| black | 35% of 414 | 6% of 266 | 91% |
| express | 86% of 50 | 53% of 92 | 47% |
| cobra | 42% of 36 | 8% of 63 | 75% |

(flask has too few labelled PRs to test.) The wording rule is a noisy hint: it
misses many labelled bugs and, in some repos, fires on about half of non-bug
PRs. Excluding text about docs, typos and CI lowered false alarms a little but
also lowered recall (black 46% to 35%); the rule was tuned looking at these same
labels, so there is no held-out check. That is why the briefing says "looks like
a fix", shows the reason, and also uses the issue label when there is one.

## Status and limits

- **The Gemini step has not been run live.** The free-tier quota was exhausted
  (HTTP 429). The evidence and prompt are verified with `--dry-run` and tests
  with a fake model. Until briefings are generated and read by a person, there
  is no evidence they are useful.
- Co-change is an association, not a dependency. The checks show it predicts
  what changes together better than a popularity guess, in most repos, not that
  changing one file requires changing another.
- One time split per repo, one baseline, no confidence intervals. Results in a
  different period or repo may differ (express already does).
- Fix detection is heuristic (above). Fix-like PRs are only found for the most
  recent ~8 PRs; older commits are judged by their subject alone.
- "Open issues that mention this file" is a plain text match.
- Renamed files split their co-change history. `--function` needs Python;
  other languages need `--lines`.
- Inherited gaps: a person under two identities, PR links recovered from
  `(#N)` in commit subjects.
