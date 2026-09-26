"""CLI for Module 10: a history-based briefing before changing code.

    python -m assist.cli --repo pallets/flask --file src/flask/helpers.py --function flash --dry-run
    python -m assist.cli --repo pallets/flask --file src/flask/app.py --lines 100-160 --plan "make X async"
    python -m assist.cli --eval --repo pallets/flask --repo psf/black      # co-change + fix-wording checks, no LLM

--dry-run shows the evidence and prompt without calling the model.
"""
import argparse
import json
from pathlib import Path

from assist.answer import brief, prepare
from assist.evaluate import bugfix_eval, cochange_eval
from assist.prompts import DEFAULT_REQUEST, SYSTEM_PROMPT, build_user_prompt
from database.connection import get_connection
from explain.cli import parse_lines
from explain.source import SourceError
from llm.client import LLMError, make_client

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "repomind.sqlite"


def run_eval(conn, repos):
    print("Co-change: does past co-change predict future co-change? (time split 70/30, top-5 partners)")
    print(f"{'repo':10s} {'variant':22s} {'cases':>6s} {'hit@5 co-change':>16s} {'hit@5 popular files':>20s} {'precision co':>13s} {'precision pop':>14s}")
    for r in repos:
        for name, skip in (("all files", False), ("without changelog/CI", True)):
            e = cochange_eval(conn, r, skip_boilerplate=skip)
            if not e["cases"]:
                print(f"{r.split('/')[1]:10s} {name:22s} too little history")
                continue
            print(f"{r.split('/')[1]:10s} {name:22s} {e['cases']:6d} {e['hit@5_cochange']:16.0%} {e['hit@5_popularity']:20.0%} "
                  f"{e['precision_cochange']:13.0%} {e['precision_popularity']:14.0%}")
    print("\n'Looks like a fix' wording vs GitHub bug labels (labels are imperfect ground truth)")
    for r in repos:
        e = bugfix_eval(conn, r)
        if not e["enough"]:
            print(f"{r.split('/')[1]:10s} too few labelled PRs (bug {e['positives']}, other {e['negatives']})")
        else:
            print(f"{r.split('/')[1]:10s} catches {e['recall_on_bug_labelled']:.0%} of {e['positives']} bug-labelled PRs | "
                  f"fires on {e['fires_on_non_bug']:.0%} of {e['negatives']} non-bug PRs | precision {e['precision']:.0%}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--repo", action="append", required=True)
    p.add_argument("--file")
    p.add_argument("--function")
    p.add_argument("--lines")
    p.add_argument("--plan", help="what you intend to change (optional)")
    p.add_argument("--db-path", default=str(DB_PATH))
    p.add_argument("--model")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--json", action="store_true")
    p.add_argument("--eval", action="store_true")
    args = p.parse_args()
    conn = get_connection(args.db_path)
    try:
        if args.eval:
            return run_eval(conn, args.repo)
        if not args.file:
            raise SystemExit("--file is required")
        repo, lines = args.repo[0], (parse_lines(args.lines) if args.lines else None)
        if args.dry_run:
            prep = prepare(conn, repo, args.file, args.function, lines, args.plan)
            print("=== SYSTEM PROMPT ===\n" + SYSTEM_PROMPT + "\n\n=== USER PROMPT ===\n"
                  + build_user_prompt(DEFAULT_REQUEST, prep["context"].text))
            print(f"\n[{len(prep['context'].text):,} characters of evidence; would call the model]")
            return
        res = brief(conn, repo, args.file, make_client(model=args.model), args.function, lines, args.plan)
        if args.json:
            print(json.dumps(res, indent=2, default=str))
            return
        e = res["evidence"]
        print(f"\nBriefing for {res['target']} in {res['file']} (lines {res['lines'][0]}-{res['lines'][1]}): "
              f"{e['commits_changing_lines']} commits, {e['fix_like']} look like fixes, {e['cochange_files']} co-changing files\n")
        print(res["answer"] + "\n")
        print(f"model {res['model']} | tokens in {res['usage']['prompt_tokens']}, out {res['usage']['output_tokens']}")
        print(f"cited: {', '.join(res['citations']) or 'nothing'}")
        if res["invalid_citations"]:
            print(f"WARNING: cites ids that were not in the evidence: {res['invalid_citations']}")
        if res["unverified_identifiers"]:
            print(f"WARNING: mentions identifiers not found in the evidence: {res['unverified_identifiers']}")
    except (SourceError, LLMError) as e:
        raise SystemExit(f"Error: {e}")


if __name__ == "__main__":
    main()
