"""CLI: ask a repository question, or evaluate retrieval.

    python -m retrieval.cli --repo pallets/flask "Who reviewed changes to src/flask/app.py?"
    python -m retrieval.cli --repo pallets/flask --json "why was BadRequestKeyError changed?"
    python -m retrieval.cli --eval --repo pallets/flask --repo psf/black
"""
import argparse
import json
import time
from pathlib import Path

from database.connection import get_connection
from retrieval.evaluate import evaluate
from retrieval.hybrid import Retriever

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "repomind.sqlite"


def _d(s):
    return (s or "")[:10]


def print_answer(out: dict):
    plan = out["plan"]
    print(f"\nQuestion: {out['query']}")
    print(f"Interpreted as: {', '.join(plan['intents'])}"
          + (f" | scope: {', '.join(plan['scopes'])}" if plan["scopes"] else "")
          + (f" | refs: {plan['numbers']}" if plan["numbers"] else ""))
    for note in out["notes"]:
        print(f"  note: {note}")
    for scope, block in out["answers"].items():
        if scope == "lookups":
            for item in block:
                print(f"\n[{item['type']}] " + (f"#{item['number']} " if "number" in item else item["sha"][:7] + " ")
                      + f"{item.get('title') or item.get('subject')}  ({item.get('state', '')} {_d(item.get('created_at') or item.get('date'))} by {item.get('author')})")
                for k in ("reviews", "closes_issues", "closed_by_prs", "files", "prs_linked"):
                    v = item.get(k)
                    if v:
                        print(f"   {k}: " + "; ".join(str(x if not isinstance(x, dict) else x.get('reviewer') and f"{x['reviewer']} {x['state']}" or f"#{x.get('number')} {x.get('title')}" if 'number' in x else x.get('path', x)) for x in v[:6]))
            continue
        if scope == "developers":
            for d in block:
                print(f"\n[developer] {d['name']}: {d['commits']} commits ({_d(d['first_commit'])} to {_d(d['last_commit'])}), "
                      f"{d['prs_authored']} PRs, {d['reviews_given']} reviews; top files: "
                      + ", ".join(f"{f['path']} ({f['commits']})" for f in d["top_files"][:4]))
            continue
        print(f"\n== {scope} ==")
        if "contributors" in block:
            c = block["contributors"]
            print(f"  contributors (of {c['total_commits']} commits, bots excluded):")
            for x in c["contributors"][:6]:
                print(f"    {x['name']:26s} {x['commits']:5d} commits ({x['share']:.0%})  last {_d(x['last_commit'])}")
        if "reviewers" in block:
            print("  reviewers (PRs touching this scope):")
            for x in block["reviewers"][:6] or []:
                print(f"    {x['name']:26s} {x['prs_reviewed']:5d} PRs  last {_d(x['last_review'])}")
            if not block["reviewers"]:
                print("    none found")
        if "history" in block:
            print("  recent changes:")
            for h in block["history"][:6]:
                pr = h["prs_linked"] or ([h["pr_from_subject"]] if h["pr_from_subject"] else [])
                print(f"    {_d(h['date'])} {h['sha'][:7]} {h['author'][:18]:18s} {h['subject'][:60]}" + (f"  [PR {','.join(map(str, pr))}]" if pr else ""))
        if "prs" in block:
            print("  pull requests touching this scope:")
            for p in block["prs"][:6]:
                print(f"    #{p['number']} {p['title'][:60]} ({p['state']}, {p['link']})")
        if "assessment" in block:
            a = block["assessment"]
            if a["available"]:
                print(f"  assessment: risk level {a['risk_level']}; top contributor {a['top_contributor']} "
                      f"({a['top_commit_share']:.0%} of {a['total_commits']} commits); effective contributors {a['effective_contributors']}")
                for s in a["risk_signals"]:
                    print(f"    signal: {s['name']} -- {s['detail']}")
    if out["evidence"]:
        print("\nText evidence (best matches):")
        for e in out["evidence"]:
            print(f"  {e['ref']:16s} {_d(e['date'])} {(e['author'] or '')[:16]:16s} {e['title'][:70]}")


def print_eval(repo, r):
    if r is None:
        print(f"{repo}: too few linked issue->PR pairs to evaluate")
        return
    wb, to = r["with_body"], r["title_only"]
    print(f"\n{repo}: {r['queries']} issue titles vs {r['corpus_prs']} PRs (chance recall@10 ~ {r['chance_recall@10']:.1%})")
    print(f"  PR title+body : R@1 {wb['recall@1']:.0%}  R@5 {wb['recall@5']:.0%}  R@10 {wb['recall@10']:.0%}  MRR {wb['mrr']:.2f}")
    print(f"  PR title only : R@1 {to['recall@1']:.0%}  R@5 {to['recall@5']:.0%}  R@10 {to['recall@10']:.0%}  MRR {to['mrr']:.2f}")
    m = r["misses_at_10"]
    print(f"  misses at 10: {m}; of those {r['misses_with_zero_word_overlap']} share no words with the target PR")
    for e in r["miss_examples"]:
        print(f"    e.g. issue #{e['issue']} \"{e['query'][:60]}\" -> PR #{e['true_pr']} \"{(e['true_pr_title'] or '')[:50]}\" rank={e['rank']} shared_words={e['shared_words']}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("question", nargs="?")
    p.add_argument("--repo", action="append", required=True)
    p.add_argument("--db-path", default=str(DB_PATH))
    p.add_argument("--json", action="store_true")
    p.add_argument("--eval", action="store_true", help="run the issue->PR retrieval evaluation")
    args = p.parse_args()
    conn = get_connection(args.db_path)

    if args.eval:
        for repo in args.repo:
            print_eval(repo, evaluate(conn, repo))
        return
    if not args.question:
        raise SystemExit("give a question, or use --eval")
    t0 = time.time()
    out = Retriever(conn, args.repo[0]).retrieve(args.question)
    print(json.dumps(out, indent=2, default=str) if args.json else "", end="")
    if not args.json:
        print_answer(out)
        print(f"\n({time.time() - t0:.1f}s)")


if __name__ == "__main__":
    main()
