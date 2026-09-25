import pytest

from analysis.bus_factor import assess_component, bus_factor
from analysis.data import load_activity
from analysis.features import build_features
from tests.test_analysis import _fixture_db


def dev(commits, recent, reviews=0):
    return {"commit_count": commits, "recent_commits": recent, "review_count": reviews}


def test_bus_factor_counts_developers_to_reach_coverage():
    assert bus_factor({"a": 1.0}) == 1
    assert bus_factor({"a": 0.6, "b": 0.4}, 0.5) == 1
    assert bus_factor({"a": 0.4, "b": 0.35, "c": 0.25}, 0.5) == 2
    assert bus_factor({"a": 0.4, "b": 0.35, "c": 0.25}, 0.9) == 3
    assert bus_factor({}) == 0
    even = {c: 0.25 for c in "abcd"}
    assert bus_factor(even, 0.5) == 2


def test_insufficient_evidence_below_min_commits():
    r = assess_component("x", {"a": dev(3, 3)}, min_commits=5)
    assert r["level"] == "insufficient_evidence"


def test_dormant_when_nobody_committed_recently():
    r = assess_component("x", {"a": dev(10, 0), "b": dev(10, 0)})
    assert r["level"] == "dormant"


def test_high_when_single_active_maintainer_and_history_departed():
    devs = {"active": dev(4, 4), "gone1": dev(10, 0), "gone2": dev(10, 0)}
    r = assess_component("x", devs)
    assert r["level"] == "high"
    e = r["evidence"]
    assert e["bus_factor_active"] == 1
    assert e["top_active_developer"] == "active"
    assert e["departed_share"] == pytest.approx(20 / 24)
    assert {s["name"] for s in r["signals"] if s["triggered"]} == {
        "single_active_maintainer",
        "historical_knowledge_departed",
    }


def test_medium_when_only_one_signal():
    devs = {"active": dev(30, 10), "other": dev(2, 0)}
    r = assess_component("x", devs)
    assert r["level"] == "medium"  # single active maintainer, little history departed


def test_low_when_activity_is_spread_among_active_developers():
    devs = {c: dev(10, 5) for c in "abcd"}
    r = assess_component("x", devs)
    assert r["level"] == "low"
    assert r["evidence"]["bus_factor_active"] == 2


def test_reviewer_diversity_only_evaluated_with_enough_reviews():
    spread = {c: dev(10, 5) for c in "abcd"}
    assert "low_reviewer_diversity" not in {s["name"] for s in assess_component("x", spread)["signals"]}
    assert assess_component("x", spread)["not_evaluated"]

    one_reviewer = {c: dev(10, 5) for c in "abcd"}
    one_reviewer["a"]["review_count"] = 4
    r = assess_component("x", one_reviewer)
    sig = {s["name"]: s for s in r["signals"]}
    assert sig["low_reviewer_diversity"]["triggered"]
    assert r["level"] == "medium"


def test_thresholds_are_parameters():
    devs = {"a": dev(10, 6), "b": dev(10, 4)}  # top recent share 0.6, bus factor 1
    assert assess_component("x", devs, dominant_share=0.5)["signals"][0]["triggered"] is True
    assert assess_component("x", devs, dominant_share=0.7)["signals"][0]["triggered"] is False
    devs = {"a": dev(10, 4), "b": dev(10, 3), "c": dev(10, 3)}  # bus factor 2 -> never "single"
    assert assess_component("x", devs, dominant_share=0.1)["signals"][0]["triggered"] is False


def test_recent_commits_window_in_features(tmp_path):
    conn, repo = _fixture_db(tmp_path)
    activity = load_activity(conn, repo)
    narrow, _ = build_features(activity, depth=None, recent_days=100)
    assert narrow["src/a.py"]["bob"]["recent_commits"] == 1
    assert narrow["src/a.py"]["alice"]["recent_commits"] == 0
    wide, _ = build_features(activity, depth=None, recent_days=800)
    assert wide["src/a.py"]["alice"]["recent_commits"] == 2
