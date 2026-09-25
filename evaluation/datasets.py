"""The evaluation set: repositories chosen to differ in size, contributor
structure, language and workflow (build plan Sec 31). Kept small on purpose:
validate the pipeline on a handful before scaling to dozens.

All are public, non-fork repositories. `note` records why each was picked
-- it is a selection rationale, not a finding.
"""

EVAL_REPOS = [
    {"repo": "pallets/flask", "note": "baseline; Python; two long-time maintainers, hundreds of one-off contributors"},
    {"repo": "psf/requests", "note": "Python; mature project, few active maintainers"},
    {"repo": "tiangolo/fastapi", "note": "Python; one dominant maintainer, heavy bot and one-off contributor activity"},
    {"repo": "BurntSushi/ripgrep", "note": "Rust; essentially one maintainer, many direct pushes, fewer PRs"},
    {"repo": "psf/black", "note": "Python; community governance, bot-heavy"},
    {"repo": "expressjs/express", "note": "JavaScript; large team, long history"},
    {"repo": "spf13/cobra", "note": "Go; small, community-maintained"},
    {"repo": "sindresorhus/ora", "note": "JavaScript; tiny single-maintainer library"},
]


def repo_names() -> list[str]:
    return [r["repo"] for r in EVAL_REPOS]
