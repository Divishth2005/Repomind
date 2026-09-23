"""CLI: clone/update a repo and extract its commit history to raw JSONL.

Usage:
    python -m ingest.cli --repo pallets/flask
"""
import argparse
import json
import time
from pathlib import Path

from ingest.acquire import clone_or_update
from ingest.extract_commits import extract_commits

DATA_RAW = Path(__file__).resolve().parent.parent / "data" / "raw"


def main():
    parser = argparse.ArgumentParser(description="Local Git ingestion")
    parser.add_argument("--repo", required=True, help="owner/name, e.g. pallets/flask")
    parser.add_argument("--data-dir", default=str(DATA_RAW), help="Output root for raw data")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    clones_dir = data_dir / "_clones"
    repo_name = args.repo.rstrip("/").split("/")[-1]

    print(f"[ingest] cloning/updating {args.repo} ...")
    t0 = time.time()
    repo = clone_or_update(args.repo, clones_dir)
    print(f"[ingest] clone/update done in {time.time() - t0:.1f}s")

    out_dir = data_dir / repo_name
    commits_path = out_dir / "commits.jsonl"

    print(f"[ingest] extracting commit history to {commits_path} ...")
    t0 = time.time()
    count = extract_commits(repo, commits_path)
    elapsed = time.time() - t0
    print(f"[ingest] extracted {count} commits in {elapsed:.1f}s")

    meta = {
        "repo": args.repo,
        "commit_count": count,
        "head_sha": repo.head.commit.hexsha,
        "extracted_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    (out_dir / "ingest_meta.json").write_text(json.dumps(meta, indent=2))
    print(f"[ingest] wrote metadata to {out_dir / 'ingest_meta.json'}")


if __name__ == "__main__":
    main()
