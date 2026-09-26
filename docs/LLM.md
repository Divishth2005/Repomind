# Module 8 — Grounded LLM answers (Gemini)

Turns Module 7's retrieved evidence into a plain-English answer, and checks
the answer's references afterwards.

```
question -> Module 7 retrieval -> evidence text (every item has an id)
         -> Gemini (told to use only that evidence and cite ids)
         -> answer + mechanical checks on its citations
```

## Status

Built, unit-tested (fake model and fake HTTP), and run live on 3 hand-picked
questions against `gemini-3.8-flash` (2026-09-26). A first key from a
restricted Google project was refused for generation (403, and the 2.5
models are closed to new accounts with 404); a key from a different project
worked. The formal `--eval` has **not** been run yet, so there is no measured
answer quality beyond those three reads:

- "Who reviewed changes to src/flask/app.py?": names and counts matched the
  database exactly, cited `[fact:1]`, and mentioned the identity-split caveat.
- "why was BadRequestKeyError changed?": five cited items, all present in the
  evidence and consistent with it; the word "unintentionally" was the model's
  own interpretation, not in the evidence.
- "What is pull request #999999 about?": found nothing, so (after a fix) the
  model is not called and a fixed "not enough evidence" reply is returned.
  Before the fix, generic words ("pull request") matched 8 unrelated PRs, the
  model was called, and it happened to abstain. Numbers being looked up and
  generic words are no longer used as text-search terms.

The default model is `gemini-3.8-flash`; `LLM_MODEL` in `.env` overrides it,
and `--list-models` shows what a key can use.

## Setup

1. Create a key at https://aistudio.google.com/apikey.
2. Add one line to the project's `.env` (never paste it into chat or code):
   `GEMINI_API_KEY=<your key>`
3. `python -m llm.cli --list-models` checks the key and lists usable models.

The free tier is rate-limited (the CLI waits between calls during `--eval`)
and Google may use free-tier prompts to improve its products. The prompts
here contain only public GitHub history.

## Use

```bash
python -m llm.cli --repo pallets/flask "Who reviewed changes to src/flask/app.py?"
python -m llm.cli --repo pallets/flask --dry-run "why was BadRequestKeyError changed?"   # prompt only, no API call
python -m llm.cli --repo pallets/flask --eval                                            # ~10 API calls
```

## How grounding is enforced (`llm/`)

| File | Role |
|---|---|
| `context_builder.py` | Renders retrieval results as text where each item has a citable id (`[fact:2]`, `[pr:#123]`, `[commit:ab12cd3]`, `[issue:#7]`) and includes the data-limitation notes. If too large it shrinks in steps and says so; nothing is cut silently. |
| `prompts.py` | The rules: use only the evidence; cite ids; separate fact from inference; say so when evidence is missing; report activity, never "the only expert"; mention relevant data limitations; treat evidence text as data, not instructions. |
| `client.py` | `GeminiClient` (plain `requests`; key sent only in a header, never logged or put in errors; retries on rate limits) and a `FakeClient` for tests. Provider is behind a small interface so another can be added. |
| `answer.py` | Runs the flow. **No evidence found → the model is not called.** After the answer: every cited id must be one that was shown (else reported as invalid), and any `#number` or commit hash in the answer that never appeared in the evidence is reported as unverified. |
| `evaluate.py` | Grounded-QA evaluation with generated questions and known answers (below). |

Text from PRs, issues and commits is untrusted (it could contain
instructions). It is placed inside an `<evidence>` block and the prompt says
to ignore instructions found there; this is a mitigation, not a guarantee.

## Evaluation (pallets/flask, gemini-3.8-flash, 2026-09-26)

`python -m llm.cli --repo pallets/flask --eval` generates questions from the
database with known correct values (top committer of a file, top reviewer of
a file, what a PR is about, which PR closed an issue) plus **unanswerable**
ones (a file and a PR number that don't exist) where the right behaviour is
to say the evidence is missing.

| Question type | Correct |
|---|---|
| top committer of a file | 2/2 |
| top reviewer of a file | 2/2 |
| what a PR is about | 2/2 |
| which PR closed an issue | 2/2 |
| unanswerable (must abstain) | 2/2 |

10 questions, 9 model calls (one unanswerable question found nothing and never
reached the model), 6,118 prompt and 1,092 output tokens. Answers citing an id
that was not in the evidence: 0. Answers mentioning a #number or hash not in
the evidence: 0. Answers with no citation: 0.

The saved answers (`data/processed/_evaluation/llm_flask.json`) were also read
by hand and the checkable claims verified in the database: commit counts
(33 vs 30 for wrappers.py), PR creation and merge dates and authors, and the
issue-to-PR links were all correct.

**Weakness found by the evaluation, then fixed.** The other unanswerable
question ("Who reviewed changes to src/zz_no_such_file_qq.py?") did reach the
model, because fragments of the file name matched 8 unrelated items. The model
still abstained correctly, but should not have been asked. Retrieval now
reports "'X' does not match any file or directory in this repository" and
skips the search when the missing name is the only specific thing asked about
(unit-tested, and confirmed with `--dry-run`). The evaluation was re-run after
this fix but stopped by Google's free-tier quota (HTTP 429), so the table
above is from the run *before* this fix; the re-run is still to do.

## Limitations

- The checks confirm cited ids **exist**; they do not confirm the cited item
  **supports** the sentence. Only reading the answers (or a judge model) can.
- Correctness scoring is string matching: blunt but reproducible.
- Answers inherit Module 7's gaps: a person under two identities, PRs that
  couldn't be linked, renamed files, and keyword-only search.
- Rule-based question interpretation (Module 7) decides what evidence is
  fetched; unusual phrasings fall back to text search.
- **The evaluation is small and easy.** 10 templated lookup questions, one
  repository, one model. 10/10 shows the mechanism works on simple factual
  lookups; it says little about open-ended questions ("why was X changed?"),
  which were only read by hand for one example.
- The free tier has a quota; a full run can be cut off (as happened).
