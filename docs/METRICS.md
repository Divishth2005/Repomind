# Module 4 — Knowledge Concentration Metrics

Question: how can repository activity be turned into evidence about where
development knowledge is concentrated among few people?

Nothing here measures "expertise". Every number is a *signal* derived from
repository activity, and the combined score is a **research hypothesis** to
be evaluated (Module 6), not a fact about people.

Run: `python -m analysis.cli --repo owner/name [--level file|component] [--depth N] [--half-life DAYS]`
(the repo must already be loaded via `python pipeline.py --repo owner/name`).
Output: a printed summary plus `data/processed/<repo>/metrics_depth<N>.json`
(or `metrics_file.json`) containing every underlying signal per developer.

## Units

- **Component**: first `N` path segments (default 2, e.g. `src/flask`,
  `docs/patterns`). Files shallower than `N` map to their directory; root
  files to `(root)`. `--level file` uses the file itself. Directory
  grouping is the plan's stand-in for a first-class Module entity.
- **Activity** is counted per *distinct commit* per component, so one commit
  touching ten files in a component counts once.
- **Bots** are excluded everywhere by default (`--include-bots` to override).
- **Reference date** for recency is the repo's latest commit, not "today",
  so results are reproducible.

## Signals (per developer, per component)

| Signal | Definition |
|---|---|
| commits | distinct commits authored |
| lines | additions + deletions across those commits (change magnitude) |
| recency | sum of `0.5 ** (age_days / half_life)` over those commits |
| continuity | number of distinct calendar years with a commit |
| prs | distinct PRs authored whose commits touch the component |
| reviews | distinct PRs reviewed (not self-reviews) touching the component |
| issues | distinct issues closed by PRs the developer authored that touch the component |

## Candidate metrics

For each, first turn a per-developer quantity into a share `s_i` (sums to 1).

- **A — contribution share**: `s_i` from commits; reported as `top_commit_share`.
- **B — concentration index**: Herfindahl–Hirschman `HHI = Σ s_i²` (1 = one
  contributor, 1/n = perfectly even).
- **C — effective contributor count**: `1 / HHI` — the number of
  equally-active contributors that would give the same concentration. A
  component with one dominant and many trivial contributors stays near 1.
- **D — recency-weighted concentration**: A/B/C computed from recency
  weights instead of raw commits.
- **E — multi-signal score (hypothesis)**: each developer's score is the
  weighted mean of their share of every signal above; then HHI / effective
  count are computed over the scores. A signal with no data in a component
  is dropped, not treated as zero, so missing GitHub data doesn't skew it.
  Weights default to equal and are recorded in the JSON (`signal_weights`).

Components with fewer than `--min-commits` (default 5) commits are reported
but not ranked: with one commit HHI is trivially 1.

## Assumptions and design choices (all changeable, none tuned)

- Half-life default 365 days: a guess. Change with `--half-life` and re-run;
  the value is written to the report.
- Equal signal weights: a guess; no weight fitting has been done.
- Authorship is by commit *author*, not committer.

## Known limitations

1. **Identity splitting.** A developer whose commit email is not a GitHub
   noreply address is *not* linked to their GitHub login (conservative
   resolution, see DATA_MODEL.md). In flask, commits appear under
   "David Lord" while PRs/reviews appear under `davidism`. Their signals
   are split across two identities, which understates concentration
   (especially metric E, which leans on PR/review shares). This is direct
   evidence for research question 3 and the main reason to improve identity
   resolution (e.g. use GitHub's per-commit `author.user.login`) before
   trusting E.
2. **PR/review/issue signals are partial.** PR→file links come from the PR's
   own commit SHAs, which don't exist in history for squash/rebase merges.
   On flask only 1,405 of 2,910 PRs (48%) and 425 of 840 reviews link to
   any file, so those signals under-count and favour repos/periods that
   merge with merge commits.
3. **Default branch only**, renames not tracked (a renamed file's history
   splits) — inherited from Module 0a.
4. **Many one-off contributors** (flask has several hundred in its busiest components) mean
   raw contributor counts are large; effective counts (C) are the readable
   number.
5. No ground truth exists yet. "Concentrated" means concentrated *activity*
   in the data, not confirmed knowledge concentration.

## First observations (pallets/flask, depth 2, half-life 365d)

- Metrics A, D, E broadly agree on which components are concentrated
  (Spearman of HHI across 39 components: A vs E 0.92, A vs D 0.69, D vs E
  0.65), but recency (D) changes the ranking noticeably — old contributors
  fade, so busy components look far more concentrated (e.g. `docs/patterns`:
  effective contributors 7.0 by commits, 1.6 recency-weighted).
- Most concentrated: small single-maintainer areas (`docs/_themes`,
  `website`, `extreview`) — plausible. Most distributed: `flask`, `docs`,
  `tests`.
- E reads as *more* distributed than A. Limitation 1 (identity splitting) and the
  many one-off PR authors are plausible causes; the size of each effect has
  not been measured yet.

These are observations to test, not conclusions. Sensitivity to half-life,
bots, and identity resolution is the planned evaluation.
