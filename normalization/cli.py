"""CLI: normalize raw Git (+ GitHub, if acquired) data for a repo into
data/processed/<repo>/*.jsonl, with a validation report.

Usage:
    python -m normalization.cli --repo pallets/flask
"""
import argparse
import json
from pathlib import Path

from normalization.git_normalizer import normalize_git
from normalization.github_normalizer import normalize_github
from normalization.identity import IdentityResolver
from normalization.validator import validate

DATA_RAW = Path(__file__).resolve().parent.parent / "data" / "raw"
DATA_PROCESSED = Path(__file__).resolve().parent.parent / "data" / "processed"


def _write_jsonl(path: Path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in records:
            d = r.to_dict() if hasattr(r, "to_dict") else r
            f.write(json.dumps(d, ensure_ascii=False) + "\n")


def main():
    parser = argparse.ArgumentParser(description="Normalize raw Git/GitHub data")
    parser.add_argument("--repo", required=True, help="owner/name, e.g. pallets/flask")
    parser.add_argument("--data-dir", default=str(DATA_RAW))
    parser.add_argument("--out-dir", default=str(DATA_PROCESSED))
    args = parser.parse_args()

    owner, name = args.repo.split("/")
    raw_dir = Path(args.data_dir) / name
    out_dir = Path(args.out_dir) / name

    resolver = IdentityResolver()

    print(f"[normalize] reading raw git commits for {args.repo} ...")
    git_result = normalize_git(raw_dir / "commits.jsonl", owner, name, resolver)
    print(
        f"[normalize] git: {len(git_result['commits'])} commits, "
        f"{len(git_result['files'])} files, {len(git_result['commit_files'])} commit_files"
        + (f", {git_result['skipped_malformed']} malformed skipped" if git_result["skipped_malformed"] else "")
    )

    github_dir = raw_dir / "github"
    if github_dir.exists():
        print(f"[normalize] reading raw github data ...")
        github_result = normalize_github(github_dir, owner, name, resolver)
    else:
        print(f"[normalize] no raw github data found at {github_dir}, skipping (git-only normalization)")
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
    print(f"[normalize] validation: {'OK' if report['ok'] else report['issue_count']} issue(s)")
    print(f"[normalize] counts: {report['counts']}")

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
    print(f"[normalize] wrote normalized entities + validation report to {out_dir}")


if __name__ == "__main__":
    main()
