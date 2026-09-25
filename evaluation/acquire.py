"""Run the full pipeline for every evaluation repo, one after another.

Each repo runs in its own subprocess with its own log, so one failure
doesn't stop the batch. Resumable: a repo whose validation report already
exists is skipped unless --force (GitHub acquisition also resumes from its
own checkpoints).

    python -m evaluation.acquire                     # all repos
    python -m evaluation.acquire --repos psf/black   # just one
"""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

from evaluation.datasets import repo_names

ROOT = Path(__file__).resolve().parent.parent
EVAL_DIR = ROOT / "data" / "processed" / "_evaluation"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--repos", nargs="*", help="owner/name (default: whole evaluation set)")
    p.add_argument("--force", action="store_true", help="re-run even if already processed")
    args = p.parse_args()

    repos = args.repos or repo_names()
    log_dir = EVAL_DIR / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    status_path = EVAL_DIR / "run_status.json"
    status = json.loads(status_path.read_text()) if status_path.exists() else {}

    for repo in repos:
        name = repo.split("/")[1]
        if not args.force and (ROOT / "data" / "processed" / name / "validation_report.json").exists():
            print(f"[eval] {repo}: already processed, skipping", flush=True)
            status.setdefault(repo, {"status": "ok", "note": "pre-existing"})
            continue

        print(f"[eval] {repo}: starting ...", flush=True)
        t0 = time.time()
        with (log_dir / f"{name}.log").open("w") as log:
            proc = subprocess.run(
                [sys.executable, "-u", "pipeline.py", "--repo", repo],
                cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
            )
        elapsed = round(time.time() - t0, 1)
        status[repo] = {"status": "ok" if proc.returncode == 0 else "failed", "returncode": proc.returncode, "seconds": elapsed}
        status_path.write_text(json.dumps(status, indent=2))
        print(f"[eval] {repo}: {status[repo]['status']} in {elapsed}s", flush=True)

    print("[eval] batch finished", flush=True)


if __name__ == "__main__":
    main()
