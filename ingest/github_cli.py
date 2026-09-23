"""CLI: acquire issues, PRs (with nested reviews), and labels via GitHub GraphQL.

Usage:
    python -m ingest.github_cli --repo pallets/flask
"""
import argparse
import json
import time
from pathlib import Path

from ingest.github_acquire import acquire_github_data

DATA_RAW = Path(__file__).resolve().parent.parent / "data" / "raw"


def main():
    parser = argparse.ArgumentParser(description="GitHub GraphQL acquisition")
    parser.add_argument("--repo", required=True, help="owner/name, e.g. pallets/flask")
    parser.add_argument("--data-dir", default=str(DATA_RAW), help="Output root for raw data")
    args = parser.parse_args()

    owner, name = args.repo.split("/")
    out_dir = Path(args.data_dir) / name / "github"

    t0 = time.time()
    results = acquire_github_data(owner, name, out_dir)
    elapsed = time.time() - t0

    meta = {
        "repo": args.repo,
        "counts": results,
        "acquired_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "elapsed_seconds": round(elapsed, 1),
    }
    (out_dir / "acquire_meta.json").write_text(json.dumps(meta, indent=2))

    print(f"[github] done in {elapsed:.1f}s: {results}")
    print(f"[github] wrote metadata to {out_dir / 'acquire_meta.json'}")


if __name__ == "__main__":
    main()
