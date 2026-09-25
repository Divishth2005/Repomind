"""Run the full RepoMind pipeline for any repo in one command:
Git ingestion -> GitHub acquisition -> normalization -> database -> knowledge map.

Usage:
    python pipeline.py --repo owner/name
    python pipeline.py --repo owner/name --skip-github   # git-only, no token needed
"""
import argparse
import json
import time
from pathlib import Path

from database.cli import DATA_PROCESSED as DB_PROCESSED_DEFAULT
from database.connection import get_connection, init_schema
from database.load import load_all
from database import queries as q
from ingest.acquire import clone_or_update
from ingest.extract_commits import extract_commits
from ingest.github_acquire import acquire_github_data
from normalization.git_normalizer import normalize_git
from normalization.github_normalizer import normalize_github
from normalization.identity import IdentityResolver
from normalization.validator import validate
from visualization.knowledge_map import build_graph
from visualization.render import render_html

ROOT = Path(__file__).resolve().parent
DATA_RAW = ROOT / "data" / "raw"
DATA_PROCESSED = ROOT / "data" / "processed"
DB_PATH = ROOT / "data" / "repomind.sqlite"


def _write_jsonl(path: Path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    import json
    with path.open("w", encoding="utf-8") as f:
        for r in records:
            d = r.to_dict() if hasattr(r, "to_dict") else r
            f.write(json.dumps(d, ensure_ascii=False) + "\n")


def run(repo: str, skip_github: bool = False):
    owner, name = repo.split("/")
    repository_id = f"{owner}/{name}"
    t_start = time.time()

    print(f"\n=== RepoMind pipeline: {repo} ===\n")

    # Stage 1: Git ingestion
    print("[1/5] Git ingestion ...")
    t0 = time.time()
    git_repo = clone_or_update(repo, DATA_RAW / "_clones")
    commits_path = DATA_RAW / name / "commits.jsonl"
    commit_count = extract_commits(git_repo, commits_path)
    print(f"      {commit_count} commits extracted ({time.time() - t0:.1f}s)")

    # Stage 2: GitHub acquisition
    if not skip_github:
        print("[2/5] GitHub acquisition (issues, PRs, reviews, labels) ...")
        t0 = time.time()
        github_dir = DATA_RAW / name / "github"
        results = acquire_github_data(owner, name, github_dir)
        print(f"      {results} ({time.time() - t0:.1f}s)")
    else:
        print("[2/5] GitHub acquisition skipped (--skip-github)")

    # Stage 3: Normalization
    print("[3/5] Normalization & identity resolution ...")
    t0 = time.time()
    resolver = IdentityResolver()
    git_result = normalize_git(commits_path, owner, name, resolver)

    github_dir = DATA_RAW / name / "github"
    if github_dir.exists():
        github_result = normalize_github(github_dir, owner, name, resolver)
    else:
        github_result = {"labels": [], "issues": [], "pull_requests": [], "reviews": []}

    normalized = {
        "repository": git_result["repository"],
        "developers": list(resolver.developers.values()),
        "files": git_result["files"],
        "commits": git_result["commits"],
        "commit_files": git_result["commit_files"],
        **github_result,
    }
    report = validate(normalized)
    print(f"      validation: {'OK' if report['ok'] else str(report['issue_count']) + ' issue(s)'}")
    print(f"      counts: {report['counts']} ({time.time() - t0:.1f}s)")

    out_dir = DATA_PROCESSED / name
    _write_jsonl(out_dir / "repository.jsonl", [normalized["repository"]])
    _write_jsonl(out_dir / "developers.jsonl", normalized["developers"])
    _write_jsonl(out_dir / "files.jsonl", normalized["files"])
    _write_jsonl(out_dir / "commits.jsonl", normalized["commits"])
    _write_jsonl(out_dir / "commit_files.jsonl", normalized["commit_files"])
    _write_jsonl(out_dir / "issues.jsonl", normalized["issues"])
    _write_jsonl(out_dir / "pull_requests.jsonl", normalized["pull_requests"])
    _write_jsonl(out_dir / "reviews.jsonl", normalized["reviews"])
    _write_jsonl(out_dir / "labels.jsonl", normalized["labels"])
    (out_dir / "validation_report.json").write_text(json.dumps(report, indent=2))

    # Stage 4: Database
    print("[4/5] Building SQLite database ...")
    t0 = time.time()
    conn = get_connection(DB_PATH)
    init_schema(conn)
    load_all(conn, out_dir)
    print(f"      done ({time.time() - t0:.1f}s)")

    top = q.top_contributors(conn, repository_id, limit=5)
    if top:
        print("      top contributors:")
        for row in top:
            print(f"        {row['display_name'] or row['github_login']:30s} {row['commit_count']} commits")
    else:
        print("      (no non-bot contributors found)")

    # Stage 5: Knowledge map
    print("[5/5] Building knowledge map visualization ...")
    t0 = time.time()
    graph = build_graph(conn, repository_id)
    out_html = DB_PATH.parent / f"{name}_knowledge_map.html"
    render_html(graph, out_html, repo, 15)
    print(f"      {len(graph['nodes'])} nodes, {len(graph['edges'])} edges -> {out_html} ({time.time() - t0:.1f}s)")

    conn.close()
    print(f"\n=== Done in {time.time() - t_start:.1f}s ===")
    print(f"Database: {DB_PATH}")
    print(f"Knowledge map: {out_html}")


def main():
    parser = argparse.ArgumentParser(description="Run the full RepoMind pipeline for a repo")
    parser.add_argument("--repo", required=True, help="owner/name, e.g. Divishth20/Notes-5")
    parser.add_argument("--skip-github", action="store_true", help="Skip GitHub API acquisition (git-only)")
    args = parser.parse_args()
    run(args.repo, args.skip_github)


if __name__ == "__main__":
    main()
