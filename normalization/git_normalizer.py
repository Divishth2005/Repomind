"""Turn raw ingest/ commits.jsonl into normalized Repository, File, Commit,
and CommitFile records, resolving developer identities as it goes.

Every normalized Commit keeps `raw_source_reference` = its SHA, which is
the primary key in the raw JSONL -- so any normalized record can be traced
back to the exact raw line it came from.
"""
import json
from pathlib import Path

from normalization.identity import IdentityResolver, stable_id
from normalization.schema import Commit, CommitFile, File, Repository


def normalize_git(
    raw_commits_path: Path,
    owner: str,
    name: str,
    resolver: IdentityResolver,
) -> dict:
    raw_commits_path = Path(raw_commits_path)
    repository_id = f"{owner}/{name}"

    files_by_path: dict[str, File] = {}
    commits: list[Commit] = []
    commit_files: list[CommitFile] = []
    head_sha = None
    skipped_malformed = 0

    with raw_commits_path.open(encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                skipped_malformed += 1
                continue

            if head_sha is None:
                head_sha = raw["sha"]

            author_dev_id = resolver.resolve_git_identity(
                raw["author"]["name"], raw["author"]["email"]
            )
            committer_dev_id = resolver.resolve_git_identity(
                raw["committer"]["name"], raw["committer"]["email"]
            )

            commit = Commit(
                commit_id=raw["sha"],
                repository_id=repository_id,
                author_developer_id=author_dev_id,
                committer_developer_id=committer_dev_id,
                timestamp=raw["authored_date"],
                subject=raw["subject"],
                body=raw["body"],
                parent_shas=raw["parents"],
                is_merge=raw["is_merge"],
                raw_source_reference=raw["sha"],
            )
            commits.append(commit)

            for file_change in raw.get("files", []):
                path = file_change["path"]
                if path not in files_by_path:
                    files_by_path[path] = File(
                        file_id=stable_id("file", repository_id, path),
                        repository_id=repository_id,
                        path=path,
                    )
                file_id = files_by_path[path].file_id
                commit_files.append(
                    CommitFile(
                        commit_file_id=stable_id("cf", commit.commit_id, path),
                        commit_id=commit.commit_id,
                        file_id=file_id,
                        additions=file_change.get("insertions"),
                        deletions=file_change.get("deletions"),
                    )
                )

    repository = Repository(
        repository_id=repository_id,
        owner=owner,
        name=name,
        url=f"https://github.com/{owner}/{name}",
        head_sha=head_sha,
    )

    return {
        "repository": repository,
        "files": list(files_by_path.values()),
        "commits": commits,
        "commit_files": commit_files,
        "skipped_malformed": skipped_malformed,
    }
