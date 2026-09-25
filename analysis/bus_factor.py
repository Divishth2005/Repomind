"""Bus-factor / maintenance-risk signals (build plan Sec 16).

Bus factor is a DERIVED risk indicator, not a stored fact, and nothing here
says a particular person is "the only expert". Each component gets a set of
independent, individually-inspectable signals plus the numbers behind them;
the risk level is a simple count of triggered signals, so the reasoning is
always visible. Every threshold is a parameter recorded in the output --
none has been validated yet (that is Module 6).

Two different risks are kept apart on purpose:
  * concentration risk   -- the currently active work sits with very few people
  * knowledge-loss risk  -- much of the historical work came from people who
                            have since stopped contributing
"""
from analysis.contribution import normalize_shares

LEVEL_ORDER = {"high": 0, "medium": 1, "low": 2, "dormant": 3, "insufficient_evidence": 4}


def bus_factor(shares: dict, coverage: float = 0.5) -> int:
    """Smallest number of developers whose combined share reaches `coverage`.
    1 means a single developer accounts for at least that share of activity."""
    if not shares:
        return 0
    cumulative = 0.0
    for k, share in enumerate(sorted(shares.values(), reverse=True), start=1):
        cumulative += share
        if cumulative >= coverage - 1e-9:
            return k
    return len(shares)


def assess_component(
    component: str,
    devs: dict,
    min_commits: int = 5,
    coverage: float = 0.5,
    dominant_share: float = 0.6,
    departed_threshold: float = 0.5,
    min_reviews: int = 3,
) -> dict:
    total_commits = sum(f["commit_count"] for f in devs.values())
    recent_total = sum(f["recent_commits"] for f in devs.values())

    lifetime = normalize_shares({d: f["commit_count"] for d, f in devs.items()})
    recent = normalize_shares({d: f["recent_commits"] for d, f in devs.items()})

    result = {
        "component": component,
        "total_commits": total_commits,
        "recent_commits": recent_total,
        "level": None,
        "evidence": {},
        "signals": [],
        "not_evaluated": [],
    }

    if total_commits < min_commits:
        result["level"] = "insufficient_evidence"
        return result
    if recent_total == 0:
        result["level"] = "dormant"
        return result

    top_dev, top_share = max(recent.items(), key=lambda kv: kv[1])
    active_devs = [d for d, f in devs.items() if f["recent_commits"] > 0]
    departed = sum(s for d, s in lifetime.items() if devs[d]["recent_commits"] == 0)
    review_events = sum(f["review_count"] for f in devs.values())
    reviewers = sum(1 for f in devs.values() if f["review_count"] > 0)

    result["evidence"] = {
        "active_developers": len(active_devs),
        "total_developers": sum(1 for f in devs.values() if f["commit_count"] > 0),
        "bus_factor_active": bus_factor(recent, coverage),
        "bus_factor_lifetime": bus_factor(lifetime, coverage),
        "top_active_developer": top_dev,
        "top_active_share": top_share,
        "departed_share": departed,
        "linked_review_events": review_events,
        "distinct_reviewers": reviewers,
    }

    single = result["evidence"]["bus_factor_active"] == 1 and top_share >= dominant_share
    lost = departed >= departed_threshold
    result["signals"].append(
        {
            "name": "single_active_maintainer",
            "kind": "concentration",
            "triggered": single,
            "detail": f"top active developer accounts for {top_share:.0%} of recent commits "
            f"(bus factor {result['evidence']['bus_factor_active']} at {coverage:.0%} coverage)",
        }
    )
    result["signals"].append(
        {
            "name": "historical_knowledge_departed",
            "kind": "knowledge_loss",
            "triggered": lost,
            "detail": f"{departed:.0%} of all commits came from developers with no recent activity",
        }
    )
    if review_events >= min_reviews:
        result["signals"].append(
            {
                "name": "low_reviewer_diversity",
                "kind": "concentration",
                "triggered": reviewers <= 1,
                "detail": f"{reviewers} distinct reviewer(s) across {review_events} linked review events",
            }
        )
    else:
        result["not_evaluated"].append("low_reviewer_diversity (too few linked reviews)")

    triggered = sum(1 for s in result["signals"] if s["triggered"])
    result["level"] = "high" if triggered >= 2 else "medium" if triggered == 1 else "low"
    return result
