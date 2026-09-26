"""Grounded-QA evaluation (build plan Sec 40.5).

Questions are generated from the database, so each has a known correct value:
  contributors  "Who has made the most commits to <file>?"     -> top author's name
  reviewers     "Who reviewed changes to <file>?"               -> top reviewer's name
  pr            "What is pull request #N about?"                -> words from its title
  issue_pr      "Which pull request closed issue #N?"           -> that PR's number
  unanswerable  a file / PR number that does not exist          -> must abstain
Scoring is deliberate string matching: blunt, but automatic and reproducible.
It does not judge fluency or whether a cited item truly supports a sentence,
so saved answers should still be read by a person.
"""
import random
import re
import sqlite3

from llm.answer import answer_question
from retrieval import structured as st
from retrieval.hybrid import Retriever
from retrieval.text_search import tokenize


def make_questions(conn: sqlite3.Connection, repo: str, n_each: int = 3, seed: int = 0) -> list[dict]:
    rng = random.Random(seed)
    qs: list[dict] = []
    files = [r[0] for r in conn.execute(
        """SELECT f.path FROM file f JOIN commit_file cf ON cf.file_id = f.file_id
           WHERE f.repository_id = ? GROUP BY f.file_id HAVING COUNT(DISTINCT cf.commit_id) >= 8
           ORDER BY COUNT(DISTINCT cf.commit_id) DESC LIMIT 40""", (repo,))]
    rng.shuffle(files)

    for path in files:
        if sum(1 for q in qs if q["type"] == "contributors") >= n_each:
            break
        c = st.contributors(conn, repo, st.Scope("file", path), limit=2)["contributors"]
        if c and (len(c) == 1 or c[0]["commits"] > c[1]["commits"]):
            qs.append({"type": "contributors", "question": f"Who has made the most commits to {path}?", "expected": c[0]["name"]})
    for path in files:
        if sum(1 for q in qs if q["type"] == "reviewers") >= n_each:
            break
        r = st.reviewers(conn, repo, st.Scope("file", path), limit=2)
        if len(r) >= 2 and r[0]["prs_reviewed"] > r[1]["prs_reviewed"]:
            qs.append({"type": "reviewers", "question": f"Who reviewed changes to {path}?", "expected": r[0]["name"]})

    prs = conn.execute("SELECT github_number, title FROM pull_request WHERE repository_id=? AND length(title) > 20 "
                       "AND merged_at IS NOT NULL", (repo,)).fetchall()
    for r in rng.sample(prs, min(n_each, len(prs))):
        qs.append({"type": "pr", "question": f"What is pull request #{r['github_number']} about?", "expected": r["title"]})

    pairs = conn.execute(
        """SELECT pi.issue_number AS issue_no, MIN(p.github_number) AS pr_no FROM pr_issue pi
           JOIN pull_request p ON p.pr_id = pi.pr_id JOIN issue i ON i.github_number = pi.issue_number AND i.repository_id = p.repository_id
           WHERE p.repository_id = ? GROUP BY pi.issue_number HAVING COUNT(DISTINCT p.pr_id) = 1""", (repo,)).fetchall()
    for r in rng.sample(pairs, min(n_each, len(pairs))):
        qs.append({"type": "issue_pr", "question": f"Which pull request closed issue #{r['issue_no']}?", "expected": str(r["pr_no"])})

    top = conn.execute("SELECT MAX(github_number) FROM pull_request WHERE repository_id=?", (repo,)).fetchone()[0] or 0
    qs.append({"type": "unanswerable", "question": "Who reviewed changes to src/zz_no_such_file_qq.py?", "expected": None})
    qs.append({"type": "unanswerable", "question": f"What is pull request #{top + 9000} about?", "expected": None})
    return qs


def is_correct(item: dict, result: dict) -> bool:
    ans, exp = result["answer"], item["expected"]
    if item["type"] in ("contributors", "reviewers"):
        return exp.lower() in ans.lower()
    if item["type"] == "issue_pr":
        return re.search(rf"\b{re.escape(exp)}\b", ans) is not None
    if item["type"] == "pr":
        words = set(tokenize(exp))
        return bool(words) and len(words & set(tokenize(ans))) / len(words) >= 0.5
    return result["abstained"]


def run_eval(conn, repo: str, client, n_each: int = 3, seed: int = 0) -> dict:
    retriever = Retriever(conn, repo)
    rows = []
    for item in make_questions(conn, repo, n_each, seed):
        res = answer_question(conn, repo, item["question"], client, retriever)
        rows.append({**item, "correct": is_correct(item, res), "result": res})

    by_type: dict[str, list] = {}
    for r in rows:
        by_type.setdefault(r["type"], []).append(r["correct"])
    called = [r["result"] for r in rows if r["result"]["llm_called"]]
    answerable = [r for r in called if not r["abstained"]]
    tok = lambda k: sum((r["usage"] or {}).get(k) or 0 for r in called)
    return {
        "repo": repo, "questions": len(rows),
        "correct_by_type": {t: {"correct": sum(v), "total": len(v)} for t, v in by_type.items()},
        "llm_calls": len(called),
        "answers_with_invalid_citation": sum(1 for r in called if r["invalid_citations"]),
        "answers_with_unverified_identifier": sum(1 for r in called if r["unverified_identifiers"]),
        "answers_without_any_citation": sum(1 for r in answerable if not r["citations"]),
        "prompt_tokens": tok("prompt_tokens"), "output_tokens": tok("output_tokens"),
        "rows": rows,
    }
