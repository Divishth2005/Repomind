import json

from normalization.git_normalizer import normalize_git
from normalization.identity import IdentityResolver
from normalization.validator import validate

FIXTURE_COMMITS = [
    {
        "sha": "aaa111",
        "parents": ["bbb222"],
        "author": {"name": "Alice", "email": "alice@users.noreply.github.com"},
        "committer": {"name": "Alice", "email": "alice@users.noreply.github.com"},
        "authored_date": "2024-01-01T00:00:00+00:00",
        "committed_date": "2024-01-01T00:00:00+00:00",
        "subject": "Add feature",
        "body": "",
        "files": [{"path": "src/a.py", "insertions": 10, "deletions": 0, "lines": 10}],
        "is_merge": False,
    },
    {
        "sha": "bbb222",
        "parents": ["ccc333"],
        "author": {"name": "Bob", "email": "bob@example.com"},
        "committer": {"name": "Bob", "email": "bob@example.com"},
        "authored_date": "2023-12-01T00:00:00+00:00",
        "committed_date": "2023-12-01T00:00:00+00:00",
        "subject": "Fix bug",
        "body": "Details here",
        "files": [{"path": "src/a.py", "insertions": 1, "deletions": 1, "lines": 2}],
        "is_merge": False,
    },
    {
        # merge commit with no file list, per the plan's documented limitation
        "sha": "ccc333",
        "parents": ["ddd444", "eee555"],
        "author": {"name": "dependabot[bot]", "email": "dependabot[bot]@users.noreply.github.com"},
        "committer": {"name": "dependabot[bot]", "email": "dependabot[bot]@users.noreply.github.com"},
        "authored_date": "2023-11-01T00:00:00+00:00",
        "committed_date": "2023-11-01T00:00:00+00:00",
        "subject": "Merge pull request #1",
        "body": "",
        "files": [],
        "is_merge": True,
    },
]


def _write_fixture(tmp_path):
    path = tmp_path / "commits.jsonl"
    with path.open("w") as f:
        for record in FIXTURE_COMMITS:
            f.write(json.dumps(record) + "\n")
    return path


def test_normalize_git_produces_expected_counts(tmp_path):
    path = _write_fixture(tmp_path)
    resolver = IdentityResolver()
    result = normalize_git(path, "octo", "demo", resolver)

    assert len(result["commits"]) == 3
    assert len(result["files"]) == 1  # only src/a.py appears
    assert len(result["commit_files"]) == 2  # merge commit contributes none
    assert result["repository"].head_sha == "aaa111"


def test_normalize_git_resolves_bot_identity(tmp_path):
    path = _write_fixture(tmp_path)
    resolver = IdentityResolver()
    normalize_git(path, "octo", "demo", resolver)

    bot_devs = [d for d in resolver.developers.values() if d["is_bot"]]
    assert len(bot_devs) == 1
    assert bot_devs[0]["github_login"] == "dependabot[bot]"


def test_normalize_git_links_noreply_email_to_login(tmp_path):
    path = _write_fixture(tmp_path)
    resolver = IdentityResolver()
    normalize_git(path, "octo", "demo", resolver)

    alice = next(d for d in resolver.developers.values() if d["display_name"] == "Alice")
    assert alice["github_login"] == "alice"
    assert alice["identity_confidence"] == "high"


def test_normalized_output_passes_validation(tmp_path):
    path = _write_fixture(tmp_path)
    resolver = IdentityResolver()
    git_result = normalize_git(path, "octo", "demo", resolver)

    normalized = {
        "developers": list(resolver.developers.values()),
        "files": git_result["files"],
        "commits": git_result["commits"],
        "commit_files": git_result["commit_files"],
        "issues": [],
        "pull_requests": [],
        "reviews": [],
        "labels": [],
    }
    report = validate(normalized)
    assert report["ok"], report["issues"]


def test_malformed_line_is_skipped_not_fatal(tmp_path):
    path = tmp_path / "commits.jsonl"
    with path.open("w") as f:
        f.write(json.dumps(FIXTURE_COMMITS[0]) + "\n")
        f.write("{not valid json\n")
        f.write(json.dumps(FIXTURE_COMMITS[1]) + "\n")

    resolver = IdentityResolver()
    result = normalize_git(path, "octo", "demo", resolver)
    assert len(result["commits"]) == 2
    assert result["skipped_malformed"] == 1
