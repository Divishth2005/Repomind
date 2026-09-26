# Module 11 — Web interface

A local web page over everything built so far.

```bash
python -m ui            # then open http://127.0.0.1:8765  (Ctrl+C to stop)
```

Repositories must already be loaded; the **+ Add repository** button runs the
normal pipeline in the background for a new `owner/name` (one at a time, uses the
GitHub token in `.env`, has a "Git history only" option that needs no token).

## Screens

| Tab | What it shows |
|---|---|
| Overview | counts (commits, files, committers, bots, PRs, issues, reviews), top contributors, commits per year, and how concentrated the work is |
| Risk | Module 5's components with level, recent activity, bus factor, top active author, share of history from inactive authors, and the triggered signals; controls for component depth and the "active" window |
| Knowledge map | developers linked to the files they changed (interactive) |
| Ask | a question in plain English: shows how it was understood, the evidence found (with clickable `[commit]`, `[pr]`, `[issue]` references), and optionally an AI-written answer |
| Code | pick a file and function (or line range): the code with its history, or a briefing on what to check before changing it; optionally AI-written |
| History | search commits, PRs, issues and reviews; per-file history; a detail panel for any PR, issue or commit |

## Design choices

- **The AI is optional on every action** (a checkbox, off by default). Without
  it you still get the evidence that would have been sent. If the AI fails
  (no key, quota, network) the page says so in plain words and still shows the
  evidence.
- **AI answers carry their checks:** invalid citations and made-up numbers are
  shown as warnings, with a reminder that a citation only proves the source
  exists, not that it supports the sentence.
- **Risk wording is kept cautious** ("evidence shows risk signals", thresholds
  unvalidated), as in Module 5.
- **Local only:** the server binds to 127.0.0.1 with debug off, and API keys stay
  on the server and never reach the page. There is no login, so do not expose it
  to a network.
- **Untrusted text stays text.** GitHub content and model answers are inserted
  with text nodes only (no `innerHTML` anywhere).
- Names sent to `/api/jobs` are validated on the server (`owner/name` characters
  only) and the job is started without a shell.

## How it is built (`ui/`)

Plain HTML, hand-written CSS (light and dark themes) and plain JavaScript,
with no framework or build step; the interactive map uses vis-network loaded from
a CDN. Flask serves the page and a small JSON API. `services.py` holds all the
logic (no web code, so it is unit-tested directly), `app.py` the routes, `jobs.py`
the background repository job.

## What was checked

- 10 automated tests of the API (validation, error messages, the AI being optional,
  an AI failure becoming a message, job limits), plus the whole project suite
  (105 tests).
- A full pass in a browser on 2026-09-26, using the real controls:
  - **Overview** for all 9 repositories loaded at the time.
  - **Risk**: changing the component depth and active window changes the table
    (flask default matches Module 5: 5 high, 6 medium); the page says when only
    the top 60 of 87 components are shown.
  - **Knowledge map**: different developer counts; out-of-range values give a message.
  - **Ask**: 11 question types (contributors, reviewers, recent history, PR lookup,
    issue lookup, "why" search, bus factor, a person, a nonexistent file, a
    nonexistent PR, a meaningless word), the example buttons, and the AI switched
    on while Gemini was over quota (clear message, evidence still shown).
  - **Code**: explaining a function, the same with a question, a briefing with a
    stated plan, a line range, a non-Python file by lines, a whole file, and the
    error cases (missing file, backwards range, range past the end).
  - **History**: search (returns commits, PRs, issues and reviews), file history,
    the detail panel for commits, PRs and issues, navigating between a PR and its
    issue, Escape to close.
  - **Add repository**: an invalid name is rejected with no job started; adding
    `Divishth20/practice` ran in 3 seconds and the new repository appeared and
    loaded.
- Problems found and fixed during that pass: unclear messages for a backwards line
  range and a missing file, no notice when the Risk table was cut off, and a
  technical validation message on the map.

## Not checked, and limits

- **A successful AI answer has not been displayed in the browser** (the free
  quota was exhausted); that path is covered only by tests with a fake model.
- Not checked: small phone screens, the dark theme by eye, browsers other than
  the built-in one, keyboard-only use, or any accessibility audit.
- The knowledge map needs an internet connection (CDN).
- The first view of a large repository takes a few seconds while results are
  computed and cached; a "Loading" message is shown.
- The Risk tab and Overview cover Modules 4–5 in summary; the evaluation
  results (Module 6) are in the docs, not in the UI.
