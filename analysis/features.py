"""Build per-component, per-developer feature rows from raw activity.

Every metric downstream is computed from these rows, and the rows are
written out unchanged in the JSON report, so each score can be traced to
the signals that produced it (plan Sec 30: "do not hide the assumptions").
"""
from collections import defaultdict

from analysis.continuity import active_years
from analysis.data import parse_ts
from analysis.recency import DEFAULT_HALF_LIFE_DAYS, recency_weight


def component_of(path: str, depth: int | None) -> str:
    """depth=None -> the file itself. depth=N -> first N path segments;
    files shallower than N map to their own directory, root files to '(root)'."""
    if depth is None:
        return path
    parts = path.split("/")
    if len(parts) == 1:
        return "(root)"
    if len(parts) <= depth:
        return "/".join(parts[:-1])
    return "/".join(parts[:depth])


def _new():
    return {"_commits": set(), "lines_changed": 0, "_prs": set(), "_reviews": set(), "_issues": set()}


def build_features(activity: dict, depth: int | None = None, half_life_days: float = DEFAULT_HALF_LIFE_DAYS):
    """Returns ({component: {developer_id: features}}, reference_date)."""
    times = {}
    for commit_id, _dev, ts, *_ in activity["commits"]:
        times[commit_id] = parse_ts(ts)
    if not times:
        return {}, None
    reference = max(times.values())

    comps = defaultdict(lambda: defaultdict(_new))
    for commit_id, dev, _ts, path, additions, deletions in activity["commits"]:
        f = comps[component_of(path, depth)][dev]
        f["_commits"].add(commit_id)
        f["lines_changed"] += (additions or 0) + (deletions or 0)

    for dev, pr_id, path in activity["pr_authored"]:
        comps[component_of(path, depth)][dev]["_prs"].add(pr_id)
    for dev, pr_id, path in activity["reviewed"]:
        comps[component_of(path, depth)][dev]["_reviews"].add(pr_id)
    for dev, issue_number, path in activity["issues_resolved"]:
        comps[component_of(path, depth)][dev]["_issues"].add(issue_number)

    result = {}
    for comp, devs in comps.items():
        rows = {}
        for dev, f in devs.items():
            commit_times = [times[c] for c in f["_commits"]]
            rows[dev] = {
                "commit_count": len(commit_times),
                "lines_changed": f["lines_changed"],
                "recency_weighted_commits": sum(
                    recency_weight(t, reference, half_life_days) for t in commit_times
                ),
                "active_years": active_years(commit_times),
                "first_active": min(commit_times).isoformat() if commit_times else None,
                "last_active": max(commit_times).isoformat() if commit_times else None,
                "pr_count": len(f["_prs"]),
                "review_count": len(f["_reviews"]),
                "issue_count": len(f["_issues"]),
            }
        if any(r["commit_count"] > 0 for r in rows.values()):
            result[comp] = rows
    return result, reference
