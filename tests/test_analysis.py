import json
from datetime import datetime, timedelta, timezone

import pytest

from analysis.compare import spearman
from analysis.concentration import effective_contributors, herfindahl_index, top_share
from analysis.data import load_activity
from analysis.features import build_features, component_of
from analysis.knowledge_score import component_metrics, multi_signal_scores
from analysis.recency import recency_weight
from database.connection import get_connection, init_schema
from database.load import load_all


def test_component_of():
    assert component_of("src/flask/app.py", None) == "src/flask/app.py"
    assert component_of("src/flask/app.py", 2) == "src/flask"
    assert component_of("src/flask/json/tag.py", 2) == "src/flask"
    assert component_of("tests/test_a.py", 2) == "tests"
    assert component_of("README.md", 2) == "(root)"


def test_recency_half_life_is_exact():
    ref = datetime(2024, 1, 1, tzinfo=timezone.utc)
    assert recency_weight(ref, ref, 100) == pytest.approx(1.0)
    assert recency_weight(ref - timedelta(days=100), ref, 100) == pytest.approx(0.5)
    assert recency_weight(ref - timedelta(days=200), ref, 100) == pytest.approx(0.25)


def test_concentration_extremes():
    assert herfindahl_index({"a": 1.0}) == 1.0
    even = {c: 0.25 for c in "abcd"}
    assert herfindahl_index(even) == pytest.approx(0.25)
    assert effective_contributors(even) == pytest.approx(4.0)
    assert effective_contributors({"a": 0.9, "b": 0.05, "c": 0.05}) < 1.25
    assert top_share({"a": 0.7, "b": 0.3}) == 0.7


def test_multi_signal_drops_absent_signals_and_sums_to_one():
    devs = {
        "a": {"commit_count": 3, "lines_changed": 30, "recency_weighted_commits": 3.0,
              "active_years": 1, "pr_count": 0, "review_count": 0, "issue_count": 0},
        "b": {"commit_count": 1, "lines_changed": 10, "recency_weighted_commits": 1.0,
              "active_years": 1, "pr_count": 0, "review_count": 0, "issue_count": 0},
    }
    scores, shares, used = multi_signal_scores(devs)
    assert used == ["commits", "continuity", "lines", "recency"]
    assert sum(scores.values()) == pytest.approx(1.0)
    assert scores["a"] > scores["b"]


def test_spearman():
    assert spearman([1, 2, 3, 4], [10, 20, 30, 40]) == pytest.approx(1.0)
    assert spearman([1, 2, 3, 4], [40, 30, 20, 10]) == pytest.approx(-1.0)
    assert spearman([1, 1, 1], [1, 2, 3]) is None
    assert spearman([1], [1]) is None


def _w(path, records):
    with path.open("w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")


def _fixture_db(tmp_path):
    repo = "o/r"
    p = tmp_path / "p"
    p.mkdir()
    _w(p / "repository.jsonl", [{"repository_id": repo, "owner": "o", "name": "r", "url": "u",
                                 "default_branch": None, "head_sha": "c3"}])
    dev = lambda i, bot=False: {"developer_id": i, "github_login": i, "display_name": i, "email_hash": None,
                                "is_bot": bot, "identity_confidence": "high", "identity_sources": []}
    _w(p / "developers.jsonl", [dev("alice"), dev("bob"), dev("robot", True)])
    _w(p / "files.jsonl", [{"file_id": "f1", "repository_id": repo, "path": "src/a.py"},
                           {"file_id": "f2", "repository_id": repo, "path": "src/b.py"}])
    commit = lambda cid, author, ts: {"commit_id": cid, "repository_id": repo, "author_developer_id": author,
                                      "committer_developer_id": author, "timestamp": ts, "subject": "s",
                                      "body": "", "parent_shas": [], "is_merge": False, "raw_source_reference": cid}
    _w(p / "commits.jsonl", [
        commit("c1", "alice", "2022-01-01T00:00:00+00:00"),
        commit("c2", "alice", "2023-01-01T00:00:00+00:00"),
        commit("c3", "bob", "2024-01-01T00:00:00+00:00"),
        commit("c4", "robot", "2024-06-01T00:00:00+00:00"),
    ])
    cf = lambda i, c, f, a, d: {"commit_file_id": i, "commit_id": c, "file_id": f, "additions": a, "deletions": d}
    _w(p / "commit_files.jsonl", [
        cf("1", "c1", "f1", 10, 0), cf("2", "c2", "f1", 5, 5), cf("3", "c2", "f2", 1, 1),
        cf("4", "c3", "f1", 2, 0), cf("5", "c4", "f1", 100, 0),
    ])
    _w(p / "pull_requests.jsonl", [{
        "pr_id": "pr1", "repository_id": repo, "github_number": 1, "title": "t", "body": "", "state": "MERGED",
        "author_developer_id": "bob", "created_at": None, "merged_at": None, "labels": [],
        "commit_shas": ["c3"], "closing_issue_numbers": [7], "raw_source_reference": "x"}])
    _w(p / "reviews.jsonl", [
        {"review_id": "r1", "pr_id": "pr1", "reviewer_developer_id": "alice", "state": "APPROVED",
         "submitted_at": None, "body": ""},
        {"review_id": "r2", "pr_id": "pr1", "reviewer_developer_id": "bob", "state": "COMMENTED",
         "submitted_at": None, "body": ""},
    ])
    for n in ("issues.jsonl", "labels.jsonl"):
        (p / n).write_text("")
    conn = get_connection(":memory:")
    init_schema(conn)
    load_all(conn, p)
    return conn, repo


def test_bots_are_excluded_by_default(tmp_path):
    conn, repo = _fixture_db(tmp_path)
    features, _ = build_features(load_activity(conn, repo), depth=None)
    assert "robot" not in features["src/a.py"]
    features_bots, _ = build_features(load_activity(conn, repo, include_bots=True), depth=None)
    assert "robot" in features_bots["src/a.py"]


def test_features_are_counted_per_distinct_commit(tmp_path):
    conn, repo = _fixture_db(tmp_path)
    features, ref = build_features(load_activity(conn, repo), depth=1)
    alice = features["src"]["alice"]
    assert alice["commit_count"] == 2  # c2 touches two files but counts once
    assert alice["lines_changed"] == 10 + 10 + 2
    assert alice["active_years"] == 2
    assert ref.year == 2024


def test_pr_review_issue_signals_and_self_review_excluded(tmp_path):
    conn, repo = _fixture_db(tmp_path)
    features, _ = build_features(load_activity(conn, repo), depth=None)
    a = features["src/a.py"]
    assert a["bob"]["pr_count"] == 1
    assert a["bob"]["issue_count"] == 1
    assert a["alice"]["review_count"] == 1
    assert a["bob"]["review_count"] == 0  # bob reviewing his own PR does not count


def test_component_metrics_record_underlying_signals(tmp_path):
    conn, repo = _fixture_db(tmp_path)
    features, _ = build_features(load_activity(conn, repo), depth=None)
    m = component_metrics("src/a.py", features["src/a.py"], min_commits=1)
    assert m["sufficient_activity"]
    assert m["total_commits"] == 3
    assert m["metrics"]["top_commit_share"] == pytest.approx(2 / 3)
    assert {d["developer_id"] for d in m["developers"]} == {"alice", "bob"}
    assert all("commit_count" in d and "signal_shares" in d for d in m["developers"])
    assert sum(d["knowledge_score"] for d in m["developers"]) == pytest.approx(1.0)
    assert component_metrics("src/a.py", features["src/a.py"], min_commits=10)["sufficient_activity"] is False
