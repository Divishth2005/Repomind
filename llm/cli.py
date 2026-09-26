"""CLI for Module 8: grounded answers from an LLM (Gemini).

    python -m llm.cli --repo pallets/flask "Who reviewed changes to src/flask/app.py?"
    python -m llm.cli --repo pallets/flask --dry-run "why was BadRequestKeyError changed?"
    python -m llm.cli --repo pallets/flask --eval
    python -m llm.cli --list-models

Needs GEMINI_API_KEY in .env (not needed for --dry-run).
"""
import argparse
import json
from pathlib import Path

from database.connection import get_connection
from llm.answer import answer_question, prepare_prompt
from llm.client import LLMError, make_client
from llm.evaluate import run_eval

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "repomind.sqlite"
EVAL_DIR = ROOT / "data" / "processed" / "_evaluation"


def show(res: dict):
    print(f"\nQuestion: {res['question']}")
    if not res["llm_called"]:
        print("(no relevant evidence found, so the model was not called)")
    print(f"\n{res['answer']}\n")
    if res["llm_called"]:
        u = res["usage"]
        print(f"model {res['model']} | tokens in {u['prompt_tokens']}, out {u['output_tokens']} | "
              f"evidence items {len(res['context_refs'])}" + (" | context was trimmed" if res["context_truncated"] else ""))
        print(f"cited: {', '.join(res['citations']) or 'nothing'}")
    if res["invalid_citations"]:
        print(f"WARNING: cites ids that were not in the evidence: {res['invalid_citations']}")
    if res["unverified_identifiers"]:
        print(f"WARNING: mentions identifiers not found in the evidence: {res['unverified_identifiers']}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("question", nargs="?")
    p.add_argument("--repo", help="owner/name")
    p.add_argument("--db-path", default=str(DB_PATH))
    p.add_argument("--model", help="Gemini model id (default gemini-2.5-flash, or LLM_MODEL in .env)")
    p.add_argument("--dry-run", action="store_true", help="print the prompt that would be sent; no API call")
    p.add_argument("--json", action="store_true")
    p.add_argument("--eval", action="store_true", help="run the grounded-QA evaluation (makes ~10 API calls)")
    p.add_argument("--n-each", type=int, default=2, help="questions per type for --eval")
    p.add_argument("--delay", type=float, default=6.0, help="seconds between API calls (free-tier rate limits)")
    p.add_argument("--list-models", action="store_true")
    args = p.parse_args()

    try:
        if args.list_models:
            print("\n".join(make_client(model=args.model).list_models()))
            return
        if not args.repo:
            raise SystemExit("--repo is required")
        conn = get_connection(args.db_path)

        if args.dry_run:
            if not args.question:
                raise SystemExit("give a question")
            prep = prepare_prompt(conn, args.repo, args.question)
            print("=== SYSTEM PROMPT ===\n" + prep["system"] + "\n\n=== USER PROMPT ===\n" + prep["user"])
            print(f"\n[{len(prep['system']) + len(prep['user']):,} characters; "
                  + ("would call the model]" if prep["would_call_llm"] else "no evidence, so the model would NOT be called]"))
            return

        client = make_client(model=args.model, min_interval=args.delay if args.eval else 0.0)
        if args.eval:
            out = run_eval(conn, args.repo, client, args.n_each)
            EVAL_DIR.mkdir(parents=True, exist_ok=True)
            path = EVAL_DIR / f"llm_{args.repo.split('/')[1]}.json"
            path.write_text(json.dumps(out, indent=2, default=str))
            print(f"\n{out['repo']}: {out['questions']} questions, {out['llm_calls']} model calls, "
                  f"{out['prompt_tokens']} prompt / {out['output_tokens']} output tokens")
            for t, v in out["correct_by_type"].items():
                print(f"  {t:13s} {v['correct']}/{v['total']} correct")
            print(f"  answers citing an id not in the evidence: {out['answers_with_invalid_citation']}")
            print(f"  answers with an unverified #number/hash:   {out['answers_with_unverified_identifier']}")
            print(f"  answers with no citation at all:           {out['answers_without_any_citation']}")
            print(f"\nfull answers saved for manual review: {path}")
            return
        if not args.question:
            raise SystemExit("give a question, or use --eval / --dry-run / --list-models")
        res = answer_question(conn, args.repo, args.question, client)
        print(json.dumps(res, indent=2, default=str)) if args.json else show(res)
    except LLMError as e:
        raise SystemExit(f"LLM error: {e}")


if __name__ == "__main__":
    main()
