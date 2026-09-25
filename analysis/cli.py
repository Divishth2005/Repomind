"""CLI: compute knowledge-concentration metrics for a repo already loaded
into the database (run `python pipeline.py --repo ...` first).

Usage:
    python -m analysis.cli --repo pallets/flask                # directory components, depth 2
    python -m analysis.cli --repo pallets/flask --level file   # per-file
    python -m analysis.cli --repo pallets/flask --half-life 180
"""
import argparse
import json
from pathlib import Path

from analysis.compare import spearman
from analysis.data import load_activity
from analysis.features import build_features
from analysis.knowledge_score import DEFAULT_WEIGHTS, component_metrics
from analysis.recency import DEFAULT_HALF_LIFE_DAYS
from database.connection import get_connection

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "repomind.sqlite"
DATA_PROCESSED = ROOT / "data" / "processed"


def _name(names: dict, dev_id: str) -> str:
    return names.get(dev_id) or dev_id[:8]


def main():
    p = argparse.ArgumentParser(description="Knowledge-concentration metrics")
    p.add_argument("--repo", required=True, help="owner/name")
    p.add_argument("--db-path", default=str(DB_PATH))
    p.add_argument("--level", choices=["component", "file"], default="component")
    p.add_argument("--depth", type=int, default=2, help="path segments per component (component level)")
    p.add_argument("--half-life", type=float, default=DEFAULT_HALF_LIFE_DAYS, help="recency half-life, days")
    p.add_argument("--min-commits", type=int, default=5, help="ignore components with fewer commits when ranking")
    p.add_argument("--top", type=int, default=10)
    p.add_argument("--include-bots", action="store_true")
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
    features, reference = build_features(activity, depth, args.half_life)
    if not features:
        raise SystemExit("No commit activity found for this repository.")

    results = [component_metrics(c, devs, args.min_commits) for c, devs in features.items()]
    ranked = [r for r in results if r["sufficient_activity"]]

    label = "file" if depth is None else f"component (depth {depth})"
    print(f"\n=== Knowledge concentration: {repository_id} — {label} ===")
    print(f"reference date (latest commit): {reference.date()}   half-life: {args.half_life:g} days   bots: {'included' if args.include_bots else 'excluded'}")
    print(f"{len(results)} {label}s with activity, {len(ranked)} with >= {args.min_commits} commits (ranked)")
    signals = sorted({s for r in ranked for s in r["signals_used"]})
    print(f"signals present in data: {', '.join(signals)}")

    def show(title, rows):
        print(f"\n--- {title} ---")
        print(f"{'component':42s} {'commits':>7s} {'devs':>4s} {'top dev':22s} {'top%':>5s} {'effN(A)':>7s} {'effN(D)':>7s} {'effN(E)':>7s}")
        for r in rows:
            m = r["metrics"]
            top = r["developers"][0]
            print(
                f"{r['component'][:42]:42s} {r['total_commits']:7d} {r['n_contributors']:4d} "
                f"{_name(names, top['developer_id'])[:22]:22s} {m['top_commit_share'] * 100:4.0f}% "
                f"{m['effective_contributors_commits']:7.2f} {m['effective_contributors_recency']:7.2f} "
                f"{m['effective_contributors_multisignal']:7.2f}"
            )

    by_conc = sorted(ranked, key=lambda r: r["metrics"]["hhi_multisignal"], reverse=True)
    show(f"most concentrated (top {args.top} by multi-signal HHI)", by_conc[: args.top])
    show(f"most distributed (top {args.top})", by_conc[::-1][: args.top])

    if len(ranked) >= 3:
        hhi_a = [r["metrics"]["hhi_commits"] for r in ranked]
        hhi_d = [r["metrics"]["hhi_recency"] for r in ranked]
        hhi_e = [r["metrics"]["hhi_multisignal"] for r in ranked]
        print("\n--- agreement between formulations (Spearman rank correlation of HHI across components) ---")
        print(f"commits (A/B)   vs recency (D):      {spearman(hhi_a, hhi_d):.3f}")
        print(f"commits (A/B)   vs multi-signal (E):  {spearman(hhi_a, hhi_e):.3f}")
        print(f"recency (D)     vs multi-signal (E):  {spearman(hhi_d, hhi_e):.3f}")

    out_dir = DATA_PROCESSED / name
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / ("metrics_file.json" if depth is None else f"metrics_depth{depth}.json")
    report = {
        "repository_id": repository_id,
        "level": args.level,
        "depth": depth,
        "reference_date": reference.isoformat(),
        "parameters": {
            "half_life_days": args.half_life,
            "min_commits": args.min_commits,
            "include_bots": args.include_bots,
            "signal_weights": DEFAULT_WEIGHTS,
        },
        "note": "knowledge_score and metric E are research hypotheses, not measurements of expertise; see docs/METRICS.md",
        "components": results,
    }
    out_path.write_text(json.dumps(report, indent=2))
    print(f"\nfull report (all signals per developer): {out_path}")


if __name__ == "__main__":
    main()
