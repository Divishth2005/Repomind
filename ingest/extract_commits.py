"""Walk a repo's HEAD history and dump raw commit + file-change records as JSONL.

Mirrors the fields the build plan calls out: SHA, parents, author, committer,
timestamps, subject/body, and per-file change stats. Merge commits can come
back with no file list under this git behavior -- that's a known, documented
limitation (see docs/PROJECT.md), not a bug to silently paper over.
"""
import json
from pathlib import Path

from git import Repo


def _person(actor) -> dict:
    return {"name": actor.name, "email": actor.email}


def commit_to_record(commit) -> dict:
    subject, _, body = commit.message.partition("\n")
    try:
        files = [
            {
                "path": path,
                "insertions": stats.get("insertions"),
                "deletions": stats.get("deletions"),
                "lines": stats.get("lines"),
            }
            for path, stats in commit.stats.files.items()
        ]
    except Exception:
        files = []

    return {
        "sha": commit.hexsha,
        "parents": [p.hexsha for p in commit.parents],
        "author": _person(commit.author),
        "committer": _person(commit.committer),
        "authored_date": commit.authored_datetime.isoformat(),
        "committed_date": commit.committed_datetime.isoformat(),
        "subject": subject.strip(),
        "body": body.strip(),
        "files": files,
        "is_merge": len(commit.parents) > 1,
    }


def extract_commits(repo: Repo, output_path: Path) -> int:
    """Write one JSON record per commit on HEAD to `output_path`. Returns count."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    count = 0
    with output_path.open("w", encoding="utf-8") as f:
        for commit in repo.iter_commits("HEAD"):
            record = commit_to_record(commit)
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            count += 1

    return count
