"""CLI for Module 9: explain a piece of code together with its history.

    python -m explain.cli --repo pallets/flask --file src/flask/helpers.py --function flash
    python -m explain.cli --repo pallets/flask --file src/flask/app.py --lines 100-160 --question "why is this guarded?"
    python -m explain.cli --repo pallets/flask --file src/flask/helpers.py --function flash --dry-run
    python -m explain.cli --stats --repo pallets/flask            # history coverage, no LLM

--dry-run shows the evidence and prompt without calling the model.
"""
import argparse
import json
from pathlib import Path

from database.connection import get_connection
from explain.answer import explain, prepare
from explain.prompts import DEFAULT_QUESTION, SYSTEM_PROMPT, build_user_prompt
from explain.source import SourceError
from llm.client import LLMError, make_client

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "repomind.sqlite"


def parse_lines(text):
    try:
        a, b = text.split("-")
        return int(a), int(b)
    except Exception:
        raise SystemExit("--lines must look like 100-160")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--repo", required=True, help="owner/name (must already be loaded)")
    p.add_argument("--file", help="path inside the repository")
    p.add_argument("--function", help="function or class name (Python), e.g. flash or Flask.url_for")
    p.add_argument("--lines", help="line range, e.g. 100-160 (any language)")
    p.add_argument("--question", help="optional question about the code")
    p.add_argument("--db-path", default=str(DB_PATH))
    p.add_argument("--model")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--json", action="store_true")
    p.add_argument("--stats", action="store_true", help="measure history coverage on sampled functions (no LLM)")
    p.add_argument("--n", type=int, default=25, help="functions to sample for --stats")
    args = p.parse_args()
    conn = get_connection(args.db_path)

    try:
        if args.stats:
            from explain.evaluate import print_stats, sample_and_measure
            print_stats(args.repo, sample_and_measure(conn, args.repo, args.n))
            return
        if not args.file:
            raise SystemExit("--file is required")
        lines = parse_lines(args.lines) if args.lines else None
        if args.dry_run:
            prep = prepare(conn, args.repo, args.file, args.function, lines)
            print("=== SYSTEM PROMPT ===\n" + SYSTEM_PROMPT + "\n\n=== USER PROMPT ===\n"
                  + build_user_prompt(args.question or DEFAULT_QUESTION, prep["context"].text))
            print(f"\n[{len(prep['context'].text):,} characters of evidence; would call the model]")
            return
        res = explain(conn, args.repo, args.file, make_client(model=args.model), args.function, lines, args.question)
        if args.json:
            print(json.dumps(res, indent=2, default=str))
            return
        h = res["history"]
        print(f"\n{res['target']} in {res['file']} (lines {res['lines'][0]}-{res['lines'][1]}): "
              f"{h['commits']} commits, {h['prs']} PRs, {h['issues']} issues in the evidence\n")
        print(res["answer"] + "\n")
        u = res["usage"]
        print(f"model {res['model']} | tokens in {u['prompt_tokens']}, out {u['output_tokens']}"
              + (" | context was trimmed" if res["context_truncated"] else ""))
        print(f"cited: {', '.join(res['citations']) or 'nothing'}")
        if res["invalid_citations"]:
            print(f"WARNING: cites ids that were not in the evidence: {res['invalid_citations']}")
        if res["unverified_identifiers"]:
            print(f"WARNING: mentions identifiers not found in the evidence: {res['unverified_identifiers']}")
    except (SourceError, LLMError) as e:
        raise SystemExit(f"Error: {e}")


if __name__ == "__main__":
    main()
