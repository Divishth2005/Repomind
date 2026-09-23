import json

from database import queries as q
from database.connection import get_connection, init_schema
from database.load import load_all


def _write_jsonl(path, records):
    with path.open("w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")


def _build_fixture_db(tmp_path):
    repo_id = "octo/demo"
    processed = tmp_path / "processed"
    processed.mkdir()

    _write_jsonl(processed / "repository.jsonl", [{
        "repository_id": repo_id, "owner": "octo", "name": "demo",
        "url": "https://github.com/octo/demo", "default_branch": None, "head_sha": "aaa111",
    }])
    _write_jsonl(processed / "developers.jsonl", [
        {"developer_id": "dev_alice", "github_login": "alice", "display_name": "Alice",
         "email_hash": None, "is_bot": False, "identity_confidence": "high", "identity_sources": ["git_noreply_email"]},
        {"developer_id": "dev_bob", "github_login": None, "display_name": "Bob",
         "email_hash": None, "is_bot": False, "identity_confidence": "medium", "identity_sources": ["git_email"]},
    ])
    _write_jsonl(processed / "files.jsonl", [
        {"file_id": "file_a", "repository_id": repo_id, "path": "src/a.py"},
    ])
    _write_jsonl(processed / "commits.jsonl", [
        {"commit_id": "aaa111", "repository_id": repo_id, "author_developer_id": "dev_alice",
         "committer_developer_id": "dev_alice", "timestamp": "2024-01-01T00:00:00+00:00",
         "subject": "Add feature", "body": "", "parent_shas": ["bbb222"], "is_merge": False,
         "raw_source_reference": "aaa111"},
        {"commit_id": "bbb222", "repository_id": repo_id, "author_developer_id": "dev_bob",
         "committer_developer_id": "dev_bob", "timestamp": "2023-12-01T00:00:00+00:00",
         "subject": "Fix bug", "body": "", "parent_shas": [], "is_merge": False,
         "raw_source_reference": "bbb222"},
    ])
    _write_jsonl(processed / "commit_files.jsonl", [
        {"commit_file_id": "cf1", "commit_id": "aaa111", "file_id": "file_a", "additions": 10, "deletions": 0},
        {"commit_file_id": "cf2", "commit_id": "bbb222", "file_id": "file_a", "additions": 1, "deletions": 1},
    ])
    for name in ("issues.jsonl", "pull_requests.jsonl", "reviews.jsonl", "labels.jsonl"):
        (processed / name).write_text("")

    conn = get_connection(":memory:")
    init_schema(conn)
    load_all(conn, processed)
    return conn, repo_id


def test_load_all_counts(tmp_path):
    conn, repo_id = _build_fixture_db(tmp_path)
    counts = {row["c"] for row in [conn.execute("SELECT COUNT(*) AS c FROM commit_").fetchone()]}
    assert counts == {2}


def test_developer_files_query(tmp_path):
    conn, repo_id = _build_fixture_db(tmp_path)
    rows = q.developer_files(conn, "dev_alice")
    assert len(rows) == 1
    assert rows[0]["path"] == "src/a.py"
    assert rows[0]["touches"] == 1


def test_file_developers_query(tmp_path):
    conn, repo_id = _build_fixture_db(tmp_path)
    rows = q.file_developers(conn, "src/a.py", repo_id)
    developer_ids = {r["developer_id"] for r in rows}
    assert developer_ids == {"dev_alice", "dev_bob"}


def test_top_contributors_query(tmp_path):
    conn, repo_id = _build_fixture_db(tmp_path)
    rows = q.top_contributors(conn, repo_id)
    assert len(rows) == 2
    assert rows[0]["commit_count"] == 1


def test_foreign_keys_enforced(tmp_path):
    conn, repo_id = _build_fixture_db(tmp_path)
    fk_ok = conn.execute("PRAGMA foreign_keys").fetchone()[0]
    assert fk_ok == 1
