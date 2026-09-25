import pytest

from evaluation.experiments import _rho, bot_sensitivity, identity_sensitivity, risk_stability
from evaluation.metrics import dataset_stats
from analysis.data import load_activity
from tests.test_analysis import _fixture_db


def test_rho_needs_enough_common_units():
    a = {f"u{i}": float(i) for i in range(4)}
    assert _rho(a, a) is None
    b = {f"u{i}": float(i) for i in range(6)}
    assert _rho(b, b) == pytest.approx(1.0)
    assert _rho(b, {f"u{i}": float(-i) for i in range(6)}) == pytest.approx(-1.0)


def test_dataset_stats_counts_bots_and_links(tmp_path):
    conn, repo = _fixture_db(tmp_path)
    s = dataset_stats(conn, repo, tmp_path / "nonexistent")
    assert s["commits"] == 4
    assert s["bot_identities"] == 1
    assert s["bot_commit_share"] == pytest.approx(0.25)
    assert s["merge_commit_share"] == 0
    assert s["pull_requests"] == 1 and s["reviews"] == 2
    assert s["pr_file_link_rate"] == 1.0
    assert s["review_file_link_rate"] == 1.0
    assert s["validation_ok"] is None  # no validation report present
    assert s["top10_committers_linked_to_github_login"] == 2  # alice and bob have logins in the fixture


def test_identity_sensitivity_counts_name_merges(tmp_path):
    conn, repo = _fixture_db(tmp_path)
    conn.execute(
        "INSERT INTO developer VALUES ('alice2', NULL, 'Alice', NULL, 0, 'medium', '[]')"
    )
    conn.execute(
        "INSERT INTO commit_ VALUES ('c5', ?, 'alice2', 'alice2', '2023-06-01T00:00:00+00:00', 's', '', '[]', 0, 'c5')",
        (repo,),
    )
    conn.execute("INSERT INTO commit_file VALUES ('cf9', 'c5', 'f1', 1, 1)")
    conn.commit()
    r = identity_sensitivity(conn, repo, None)
    assert r["identities_merged_away"] == 1
    assert r["identities_name_merged"] == r["identities_conservative"] - 1


def test_bot_sensitivity_reports_unit_counts(tmp_path):
    conn, repo = _fixture_db(tmp_path)
    r = bot_sensitivity(conn, repo, None, min_commits=1)
    assert r["units_compared"] == 2
    assert r["units_whose_top_committer_changes"] == 0


def test_risk_stability_shape(tmp_path):
    conn, repo = _fixture_db(tmp_path)
    r = risk_stability(load_activity(conn, repo), depth=1)
    assert "level_counts_365" in r and "agreement_with_180d" in r and "agreement_with_730d" in r
