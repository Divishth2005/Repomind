"""Compute the multi-repo evaluation and write comparison tables.

    python -m evaluation.cli

Reads every evaluation repo already loaded in the database (see
`python -m evaluation.acquire`), runs the data-quality statistics and
sensitivity experiments, writes raw results to
data/processed/_evaluation/results.json and generated tables to
docs/EVALUATION_RESULTS.md (a generated file -- edit docs/EVALUATION.md
for interpretation instead).
"""
import argparse
import json
from datetime import date
from pathlib import Path

from database.connection import get_connection
from evaluation.datasets import EVAL_REPOS
from evaluation.experiments import run_all
from evaluation.metrics import dataset_stats

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "repomind.sqlite"
EVAL_DIR = ROOT / "data" / "processed" / "_evaluation"
RESULTS_DOC = ROOT / "docs" / "EVALUATION_RESULTS.md"


def f(x, kind="num"):
    if x is None:
        return "n/a"
    if kind == "pct":
        return f"{x * 100:.0f}%"
    if kind == "rho":
        return f"{x:.2f}"
    if kind == "dec":
        return f"{x:.1f}"
    return f"{x:,}" if isinstance(x, int) else str(x)


def table(title, header, rows):
    out = [f"### {title}", "", "| " + " | ".join(header) + " |", "|" + "|".join(["---"] * len(header)) + "|"]
    out += ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(out) + "\n"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--db-path", default=str(DB_PATH))
    args = p.parse_args()

    conn = get_connection(args.db_path)
    results = {}
    for entry in EVAL_REPOS:
        repo = entry["repo"]
        if not conn.execute("SELECT 1 FROM repository WHERE repository_id=?", (repo,)).fetchone():
            print(f"[eval] {repo}: not in database, skipped")
            continue
        name = repo.split("/")[1]
        print(f"[eval] {repo}: computing ...", flush=True)
        results[repo] = {
            "note": entry["note"],
            "dataset": dataset_stats(conn, repo, ROOT / "data" / "processed" / name),
            "experiments": run_all(conn, repo),
        }

    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    (EVAL_DIR / "results.json").write_text(json.dumps(results, indent=2, default=str))

    short = lambda r: r.split("/")[1]
    parts = [
        "# Evaluation results (generated)\n",
        f"Generated {date.today().isoformat()} by `python -m evaluation.cli` from {len(results)} repositories. "
        "Do not edit; interpretation lives in EVALUATION.md.\n",
    ]

    parts.append(table(
        "1. Dataset and pipeline validity",
        ["repo", "commits", "span (years)", "files", "committer identities", "bot identities", "bot commit share", "issues", "PRs", "reviews", "validation"],
        [[short(r), f(v["dataset"]["commits"]),
          f"{v['dataset']['first_commit'][:4]}–{v['dataset']['last_commit'][:4]}",
          f(v["dataset"]["files"]), f(v["dataset"]["committer_identities"]), f(v["dataset"]["bot_identities"]),
          f(v["dataset"]["bot_commit_share"], "pct"), f(v["dataset"]["issues"]), f(v["dataset"]["pull_requests"]),
          f(v["dataset"]["reviews"]),
          "OK" if v["dataset"]["validation_ok"] else f"{v['dataset']['validation_issue_count']} issues"]
         for r, v in results.items()]))

    parts.append(table(
        "2. Identity resolution and Git↔GitHub linkage",
        ["repo", "human commits with GitHub-login-linked identity", "top-10 committers linked to a GitHub login", "PRs linked to file changes", "reviews linked to file changes", "merge commits", "commits with no file list"],
        [[short(r),
          f(v["dataset"]["human_commit_share_by_identity_confidence"].get("high", 0.0), "pct"),
          f"{v['dataset']['top10_committers_linked_to_github_login']}/10",
          f(v["dataset"]["pr_file_link_rate"], "pct"), f(v["dataset"]["review_file_link_rate"], "pct"),
          f(v["dataset"]["merge_commit_share"], "pct"), f(v["dataset"]["commits_without_files_share"], "pct")]
         for r, v in results.items()]))

    parts.append(table(
        "3. Concentration metric behaviour (files with >= 5 commits ranked; components = depth 2)",
        ["repo", "ranked files", "median effective contributors (files)", "files with top share >= 80%", "ρ commits vs recency", "ρ commits vs multi-signal", "ranked components", "components with top share >= 80%"],
        [[short(r), f(v["experiments"]["metric_behavior_file"].get("ranked_units")),
          f(v["experiments"]["metric_behavior_file"].get("median_effective_contributors"), "dec"),
          f(v["experiments"]["metric_behavior_file"].get("share_top_commit_share_ge_80"), "pct"),
          f(v["experiments"]["metric_behavior_file"].get("rho_A_vs_D"), "rho"),
          f(v["experiments"]["metric_behavior_file"].get("rho_A_vs_E"), "rho"),
          f(v["experiments"]["metric_behavior_component"].get("ranked_units")),
          f(v["experiments"]["metric_behavior_component"].get("share_top_commit_share_ge_80"), "pct")]
         for r, v in results.items()]))

    parts.append(table(
        "4. Sensitivity of file-level concentration rankings (Spearman ρ; 1.00 = identical ordering)",
        ["repo", "half-life 90d vs 365d", "365d vs 1095d", "with vs without bots", "files whose top committer changes when bots included", "conservative vs name-merged identities", "identities merged away"],
        [[short(r), f(v["experiments"]["recency_sensitivity_file"]["rho_halflife_90_vs_365"], "rho"),
          f(v["experiments"]["recency_sensitivity_file"]["rho_halflife_365_vs_1095"], "rho"),
          f(v["experiments"]["bot_sensitivity_file"]["rho_with_vs_without_bots"], "rho"),
          f"{v['experiments']['bot_sensitivity_file']['units_whose_top_committer_changes']}/{v['experiments']['bot_sensitivity_file']['units_compared']}",
          f(v["experiments"]["identity_sensitivity_file"]["rho_conservative_vs_name_merged"], "rho"),
          f(v["experiments"]["identity_sensitivity_file"]["identities_merged_away"])]
         for r, v in results.items()]))

    def lv(v, k):
        return v["experiments"]["risk_stability_component"]["level_counts_365"].get(k, 0)

    parts.append(table(
        "5. Risk signals (components, depth 2, 365-day active window) and threshold stability",
        ["repo", "high", "medium", "low", "dormant", "insufficient", "level agreement at 180d", "level agreement at 730d"],
        [[short(r), f(lv(v, "high")), f(lv(v, "medium")), f(lv(v, "low")), f(lv(v, "dormant")),
          f(lv(v, "insufficient_evidence")),
          f(v["experiments"]["risk_stability_component"]["agreement_with_180d"], "pct"),
          f(v["experiments"]["risk_stability_component"]["agreement_with_730d"], "pct")]
         for r, v in results.items()]))

    parts.append("Selection rationale per repo:\n\n" + "\n".join(f"- **{short(r)}**: {v['note']}" for r, v in results.items()) + "\n")
    text = "\n".join(parts)
    RESULTS_DOC.write_text(text)
    print(text)
    print(f"\nwritten: {RESULTS_DOC}\nraw results: {EVAL_DIR / 'results.json'}")


if __name__ == "__main__":
    main()
