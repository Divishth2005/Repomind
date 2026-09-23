import json

from database.connection import get_connection, init_schema
from database.load import load_all
from visualization.knowledge_map import build_graph
from visualization.render import render_html


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
         "email_hash": None, "is_bot": False, "identity_confidence": "high", "identity_sources": []},
    ])
    _write_jsonl(processed / "files.jsonl", [
        {"file_id": "file_a", "repository_id": repo_id, "path": "src/a.py"},
    ])
    _write_jsonl(processed / "commits.jsonl", [
        {"commit_id": "aaa111", "repository_id": repo_id, "author_developer_id": "dev_alice",
         "committer_developer_id": "dev_alice", "timestamp": "2024-01-01T00:00:00+00:00",
         "subject": "Add feature", "body": "", "parent_shas": [], "is_merge": False,
         "raw_source_reference": "aaa111"},
    ])
    _write_jsonl(processed / "commit_files.jsonl", [
        {"commit_file_id": "cf1", "commit_id": "aaa111", "file_id": "file_a", "additions": 10, "deletions": 0},
    ])
    for name in ("issues.jsonl", "pull_requests.jsonl", "reviews.jsonl", "labels.jsonl"):
        (processed / name).write_text("")

    conn = get_connection(":memory:")
    init_schema(conn)
    load_all(conn, processed)
    return conn, repo_id


def test_build_graph_has_developer_and_file_nodes(tmp_path):
    conn, repo_id = _build_fixture_db(tmp_path)
    graph = build_graph(conn, repo_id, top_developers=5, files_per_dev=5)

    groups = {n["group"] for n in graph["nodes"]}
    assert groups == {"developer", "file"}
    assert len(graph["edges"]) == 1


def test_render_html_writes_valid_file(tmp_path):
    conn, repo_id = _build_fixture_db(tmp_path)
    graph = build_graph(conn, repo_id)
    out_path = tmp_path / "map.html"

    render_html(graph, out_path, "octo/demo", 5)

    content = out_path.read_text()
    assert "vis-network" in content
    assert "octo/demo" in content
    assert "dev_alice" in content or "Alice" in content
