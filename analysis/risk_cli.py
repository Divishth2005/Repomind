"""CLI: bus-factor / maintenance-risk signals per component.

Usage:
    python -m analysis.risk_cli --repo pallets/flask
    python -m analysis.risk_cli --repo pallets/flask --active-days 180 --sensitivity
"""
import argparse
import json
from collections import Counter
from pathlib import Path

from analysis.bus_factor import LEVEL_ORDER, assess_component
from analysis.data import load_activity
from analysis.features import build_features
from database.connection import get_connection

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "repomind.sqlite"
DATA_PROCESSED = ROOT / "data" / "processed"

WORDING = (
    "Wording note: 'high' means the available repository evidence shows several risk signals "
    "for this component. It does not establish that any individual is the only person who "
    "understands it."
)


def assess_all(features: dict, args) -> list[dict]:
    results = [
        assess_component(
            c, devs, args.min_commits, args.coverage, args.dominant_share, args.departed_threshold
        )
        for c, devs in features.items()
    ]
    results.sort(key=lambda r: (LEVEL_ORDER[r["level"]], -r["recent_commits"]))
    return results


def main():
    p = argparse.ArgumentParser(description="Bus-factor / maintenance-risk signals")
    p.add_argument("--repo", required=True, help="owner/name")
    p.add_argument("--db-path", default=str(DB_PATH))
    p.add_argument("--level", choices=["component", "file"], default="component")
    p.add_argument("--depth", type=int, default=2)
    p.add_argument("--active-days", type=float, default=365, help="a developer is 'active' if they committed this recently")
    p.add_argument("--coverage", type=float, default=0.5, help="share of activity the bus-factor developers must cover")
    p.add_argument("--dominant-share", type=float, default=0.6, help="recent-commit share that counts as a single maintainer")
    p.add_argument("--departed-threshold", type=float, default=0.5, help="share of history from inactive developers that triggers knowledge-loss")
    p.add_argument("--min-commits", type=int, default=5)
    p.add_argument("--top", type=int, default=12)
    p.add_argument("--include-bots", action="store_true")
    p.add_argument("--sensitivity", action="store_true", help="show how high-risk counts change with thresholds")
    args = p.parse_args()

    owner, name = args.repo.split("/")
    repository_id = f"{owner}/{name}"
    depth = None if args.level == "file" else args.depth

    conn = get_connection(args.db_path)
    if not conn.execute("SELECT 1 FROM repository WHERE repository_id = ?", (repository_id,)).fetchone():
        raise SystemExit(f"{repository_id} is not in the database. Run: python pipeline.py --repo {repository_id}")
    names = {
        r["developer_id"]: r["display_name"] or r["github_login"]
        for r in conn.execute("SELECT developer_id, display_name, github_login FROM developer")
    }

    activity = load_activity(conn, repository_id, include_bots=args.include_bots)
    features, reference = build_features(activity, depth, recent_days=args.active_days)
    if not features:
        raise SystemExit("No commit activity found for this repository.")
    results = assess_all(features, args)

    counts = Counter(r["level"] for r in results)
    label = "file" if depth is None else f"component (depth {depth})"
    print(f"\n=== Maintenance-risk signals: {repository_id} — {label} ===")
    print(f"as of latest commit {reference.date()}; 'active' = committed within {args.active_days:g} days")
    print(f"bus factor coverage {args.coverage:.0%}; single-maintainer share >= {args.dominant_share:.0%}; departed-history threshold {args.departed_threshold:.0%}")
    print("levels: " + ", ".join(f"{lv}={counts.get(lv, 0)}" for lv in LEVEL_ORDER))

    flagged = [r for r in results if r["level"] in ("high", "medium")][: args.top]
    print(f"\n--- highest-risk components (highest level first, then most recent activity) ---")
    print(f"{'component':36s} {'level':7s} {'recent':>6s} {'active':>6s} {'BF':>3s} {'top active dev':20s} {'share':>5s} {'departed':>8s}")
    for r in flagged:
        e = r["evidence"]
        print(
            f"{r['component'][:36]:36s} {r['level']:7s} {r['recent_commits']:6d} "
            f"{e['active_developers']:>3d}/{e['total_developers']:<2d} {e['bus_factor_active']:3d} "
            f"{(names.get(e['top_active_developer']) or e['top_active_developer'][:8])[:20]:20s} "
            f"{e['top_active_share']:5.0%} {e['departed_share']:8.0%}"
        )
    if not flagged:
        print("(none)")
    print("\ncolumns: recent = commits in active window; active = active/total developers; BF = active bus factor; departed = share of history from now-inactive developers")

    if args.sensitivity:
        print("\n--- sensitivity: number of HIGH-risk components under different thresholds ---")
        header = f"{'active window (days)':22s}" + "".join(f"dominant>={d:.0%}".rjust(15) for d in (0.5, 0.6, 0.7))
        print(header)
        for days in (180, 365, 730):
            feats, _ = build_features(activity, depth, recent_days=days)
            row = f"{days:<22d}"
            for dom in (0.5, 0.6, 0.7):
                n = sum(
                    1
                    for c, devs in feats.items()
                    if assess_component(c, devs, args.min_commits, args.coverage, dom, args.departed_threshold)["level"] == "high"
                )
                row += f"{n:15d}"
            print(row)

    print(f"\n{WORDING}")

    out_dir = DATA_PROCESSED / name
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / ("risk_file.json" if depth is None else f"risk_depth{depth}.json")
    out_path.write_text(
        json.dumps(
            {
                "repository_id": repository_id,
                "reference_date": reference.isoformat(),
                "parameters": {
                    "active_days": args.active_days,
                    "coverage": args.coverage,
                    "dominant_share": args.dominant_share,
                    "departed_threshold": args.departed_threshold,
                    "min_commits": args.min_commits,
                    "include_bots": args.include_bots,
                },
                "note": WORDING,
                "level_counts": dict(counts),
                "components": results,
            },
            indent=2,
        )
    )
    print(f"full report with evidence per component: {out_path}")


if __name__ == "__main__":
    main()
