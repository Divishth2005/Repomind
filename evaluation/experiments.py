"""Sensitivity experiments (build plan Sec 40.3): how much do the Module 4/5
results change when the choices behind them change?

Each experiment compares rankings across components with Spearman rank
correlation (1 = same ordering) over the units both variants rank. These are
sensitivity checks, not accuracy measures -- there is no ground truth.
"""
from collections import Counter

from analysis.bus_factor import assess_component
from analysis.compare import spearman
from analysis.concentration import herfindahl_index
from analysis.contribution import normalize_shares
from analysis.data import load_activity
from analysis.features import build_features
from analysis.knowledge_score import component_metrics

MIN_UNITS = 5  # fewer common ranked units than this -> correlation reported as None


def _hhi(features: dict, field: str, min_commits: int) -> dict:
    out = {}
    for comp, devs in features.items():
        if sum(f["commit_count"] for f in devs.values()) < min_commits:
            continue
        shares = normalize_shares({d: f[field] for d, f in devs.items()})
        if shares:
            out[comp] = herfindahl_index(shares)
    return out


def _rho(a: dict, b: dict):
    common = sorted(set(a) & set(b))
    if len(common) < MIN_UNITS:
        return None
    return spearman([a[k] for k in common], [b[k] for k in common])


def _top_dev(devs: dict) -> str:
    return max(devs.items(), key=lambda kv: kv[1]["commit_count"])[0]


def recency_sensitivity(activity, depth, min_commits=5, half_lives=(90, 365, 1095)) -> dict:
    hh = {}
    for h in half_lives:
        feats, _ = build_features(activity, depth, half_life_days=h)
        hh[h] = _hhi(feats, "recency_weighted_commits", min_commits)
    feats, _ = build_features(activity, depth)
    plain = _hhi(feats, "commit_count", min_commits)
    return {
        "units_ranked": len(plain),
        "rho_halflife_90_vs_365": _rho(hh[90], hh[365]),
        "rho_halflife_365_vs_1095": _rho(hh[365], hh[1095]),
        "rho_halflife_90_vs_1095": _rho(hh[90], hh[1095]),
        "rho_commits_vs_recency_365": _rho(plain, hh[365]),
    }


def bot_sensitivity(conn, repository_id, depth, min_commits=5) -> dict:
    no_bots, _ = build_features(load_activity(conn, repository_id, include_bots=False), depth)
    with_bots, _ = build_features(load_activity(conn, repository_id, include_bots=True), depth)
    a = _hhi(no_bots, "commit_count", min_commits)
    b = _hhi(with_bots, "commit_count", min_commits)
    common = [c for c in a if c in with_bots and c in no_bots]
    changed = sum(1 for c in common if _top_dev(no_bots[c]) != _top_dev(with_bots[c]))
    return {
        "units_ranked_without_bots": len(a),
        "units_ranked_with_bots": len(b),
        "rho_with_vs_without_bots": _rho(a, b),
        "units_whose_top_committer_changes": changed,
        "units_compared": len(common),
    }


def identity_sensitivity(conn, repository_id, depth, min_commits=5) -> dict:
    """Compare the conservative identity resolution against an aggressive
    alternative that merges developers sharing a case-insensitive display
    name. The alternative can wrongly merge different people; the point is
    to measure how much the results depend on the resolution rule (RQ3)."""
    names = {
        r["developer_id"]: (r["display_name"] or r["github_login"] or r["developer_id"]).strip().lower()
        for r in conn.execute("SELECT developer_id, display_name, github_login FROM developer")
    }
    activity = load_activity(conn, repository_id)

    def remap(rows, idx):
        return [tuple(names.get(v, v) if i == idx else v for i, v in enumerate(row)) for row in rows]

    merged = {
        "commits": remap(activity["commits"], 1),
        "pr_authored": remap(activity["pr_authored"], 0),
        "reviewed": remap(activity["reviewed"], 0),
        "issues_resolved": remap(activity["issues_resolved"], 0),
    }
    base, _ = build_features(activity, depth)
    alt, _ = build_features(merged, depth)
    a = _hhi(base, "commit_count", min_commits)
    b = _hhi(alt, "commit_count", min_commits)
    ids_before = {d for c in base.values() for d in c}
    ids_after = {d for c in alt.values() for d in c}
    return {
        "identities_conservative": len(ids_before),
        "identities_name_merged": len(ids_after),
        "identities_merged_away": len(ids_before) - len(ids_after),
        "rho_conservative_vs_name_merged": _rho(a, b),
    }


def risk_stability(activity, depth=2, windows=(180, 365, 730)) -> dict:
    levels = {}
    for w in windows:
        feats, _ = build_features(activity, depth, recent_days=w)
        levels[w] = {c: assess_component(c, devs)["level"] for c, devs in feats.items()}
    base = levels[365]
    assessable = [c for c, lv in base.items() if lv in ("high", "medium", "low")]
    out = {"level_counts_365": dict(Counter(base.values())), "assessable_components": len(assessable)}
    for w in (180, 730):
        same = sum(1 for c in assessable if levels[w].get(c) == base[c])
        out[f"agreement_with_{w}d"] = (same / len(assessable)) if assessable else None
        out[f"high_at_{w}d"] = sum(1 for lv in levels[w].values() if lv == "high")
    return out


def metric_behavior(activity, depth, min_commits=5) -> dict:
    feats, _ = build_features(activity, depth)
    comps = [component_metrics(c, devs, min_commits) for c, devs in feats.items()]
    ranked = [c for c in comps if c["sufficient_activity"]]
    if not ranked:
        return {"ranked_units": 0}
    effs = sorted(c["metrics"]["effective_contributors_commits"] for c in ranked)
    a = {c["component"]: c["metrics"]["hhi_commits"] for c in ranked}
    d = {c["component"]: c["metrics"]["hhi_recency"] for c in ranked}
    e = {c["component"]: c["metrics"]["hhi_multisignal"] for c in ranked}
    return {
        "ranked_units": len(ranked),
        "median_effective_contributors": effs[len(effs) // 2],
        "share_top_commit_share_ge_80": sum(1 for c in ranked if c["metrics"]["top_commit_share"] >= 0.8) / len(ranked),
        "rho_A_vs_D": _rho(a, d),
        "rho_A_vs_E": _rho(a, e),
    }


def run_all(conn, repository_id) -> dict:
    activity = load_activity(conn, repository_id)
    return {
        "metric_behavior_component": metric_behavior(activity, 2),
        "metric_behavior_file": metric_behavior(activity, None),
        "recency_sensitivity_file": recency_sensitivity(activity, None),
        "bot_sensitivity_file": bot_sensitivity(conn, repository_id, None),
        "identity_sensitivity_file": identity_sensitivity(conn, repository_id, None),
        "risk_stability_component": risk_stability(activity, 2),
    }
