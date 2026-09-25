"""Per-component metrics: the candidate concentration formulations (A-D)
plus the experimental multi-signal score (E), all side by side.

Metric E is a HYPOTHESIS, not a measurement of expertise. It is the
weighted mean of each developer's *share* of several independent signals
(commits, lines changed, recency-weighted commits, years active, PRs,
reviews, issues resolved). A signal with no data at all in a component
(e.g. no linked reviews) is dropped rather than counted as zero, so
missing GitHub data does not skew the score. Weights default to equal and
are recorded in the output.
"""
from analysis.concentration import effective_contributors, herfindahl_index, top_share
from analysis.contribution import normalize_shares

SIGNAL_FIELDS = {
    "commits": "commit_count",
    "lines": "lines_changed",
    "recency": "recency_weighted_commits",
    "continuity": "active_years",
    "prs": "pr_count",
    "reviews": "review_count",
    "issues": "issue_count",
}
DEFAULT_WEIGHTS = {s: 1.0 for s in SIGNAL_FIELDS}


def multi_signal_scores(devs: dict, weights: dict | None = None):
    weights = weights or DEFAULT_WEIGHTS
    shares = {}
    for signal, field in SIGNAL_FIELDS.items():
        s = normalize_shares({d: f[field] for d, f in devs.items()})
        if s:
            shares[signal] = s
    if not shares:
        return {}, {}, []
    wsum = sum(weights[s] for s in shares)
    scores = {
        d: sum(weights[s] * shares[s].get(d, 0.0) for s in shares) / wsum for d in devs
    }
    return scores, shares, sorted(shares)


def component_metrics(component: str, devs: dict, min_commits: int = 5, weights: dict | None = None) -> dict:
    total_commits = sum(f["commit_count"] for f in devs.values())

    a = normalize_shares({d: f["commit_count"] for d, f in devs.items()})
    d_shares = normalize_shares({d: f["recency_weighted_commits"] for d, f in devs.items()})
    scores, shares_by_signal, signals_used = multi_signal_scores(devs, weights)
    e = normalize_shares(scores)

    developers = []
    for dev, f in devs.items():
        developers.append(
            {
                "developer_id": dev,
                **f,
                "commit_share": a.get(dev, 0.0),
                "recency_share": d_shares.get(dev, 0.0),
                "signal_shares": {s: shares_by_signal[s].get(dev, 0.0) for s in signals_used},
                "knowledge_score": e.get(dev, 0.0),
            }
        )
    developers.sort(key=lambda r: r["knowledge_score"], reverse=True)

    return {
        "component": component,
        "n_contributors": len(devs),
        "total_commits": total_commits,
        "sufficient_activity": total_commits >= min_commits,
        "signals_used": signals_used,
        "metrics": {
            "top_commit_share": top_share(a),
            "hhi_commits": herfindahl_index(a),
            "effective_contributors_commits": effective_contributors(a),
            "hhi_recency": herfindahl_index(d_shares),
            "effective_contributors_recency": effective_contributors(d_shares),
            "hhi_multisignal": herfindahl_index(e),
            "effective_contributors_multisignal": effective_contributors(e),
        },
        "developers": developers,
    }
