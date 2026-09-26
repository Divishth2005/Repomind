"""Gather everything for a 'before you change this' briefing (no LLM):
the change history of the code, which past changes look like fixes, the files
and tests that usually change with it, open issues that mention it, and the
file's risk signals."""
import sqlite3

from assist.bugfix import classify_change
from assist.cochange import BOILERPLATE_RE, CoChange, is_test_path, load_commits
from explain.answer import resolve_target
from explain.history import gather
from explain.source import read_file
from retrieval import structured as st
from retrieval.hybrid import Retriever


def _issue_labels(conn, repo, numbers):
    out = {}
    for chunk in st._chunks(numbers):
        q = ",".join("?" * len(chunk))
        for r in conn.execute(f"SELECT github_number, labels FROM issue WHERE repository_id=? AND github_number IN ({q})", (repo, *chunk)):
            out[r["github_number"]] = r["labels"]
    return out


def open_issues_mentioning(conn, repo, path, limit=5):
    name = path.split("/")[-1]
    terms = [path] + ([name] if len(name) >= 10 else [])
    seen, rows = set(), []
    for t in terms:
        for r in conn.execute(
            """SELECT github_number, title, created_at, substr(body, 1, 400) AS body FROM issue
               WHERE repository_id = ? AND state = 'OPEN' AND (body LIKE ? OR title LIKE ?)
               ORDER BY datetime(created_at) DESC LIMIT ?""", (repo, f"%{t}%", f"%{t}%", limit)):
            if r["github_number"] not in seen:
                seen.add(r["github_number"])
                rows.append(dict(r))
    return rows[:limit]


def cochange_for(conn, repo, path, k=6, model=None):
    model = model or CoChange(load_commits(conn, repo))
    partners = model.partners(path, k=30, min_support=2)
    code, tests, housekeeping = [], [], []
    for r in partners:
        (housekeeping if BOILERPLATE_RE.search(r["path"]) else tests if is_test_path(r["path"]) else code).append(r)
    return {"file_commits": model.file_count.get(path, 0), "code": code[:k], "tests": tests[:3], "housekeeping": housekeeping[:2]}


def gather_briefing(conn: sqlite3.Connection, repo: str, path: str, function=None, lines=None,
                    retriever: Retriever | None = None, cochange_model: CoChange | None = None) -> dict:
    source = read_file(repo, path)
    start, end, label = resolve_target(source, function, lines)
    history = gather(conn, repo, path, start, end, retriever=retriever)
    prs = {p["number"]: p for p in history["prs"]}
    issue_numbers = sorted({i["number"] for p in history["prs"] for i in p["closes_issues"]})
    labels = _issue_labels(conn, repo, issue_numbers)

    fixes = []
    for c in history["commits"]:
        pr = next((prs[n] for n in c["prs"] if n in prs), None)
        label_sets = [labels.get(i["number"]) for i in (pr["closes_issues"] if pr else [])]
        reasons = classify_change(c["subject"], pr["title"] if pr else None, label_sets)
        if reasons:
            fixes.append({"commit_id": c["commit_id"], "timestamp": c["timestamp"], "author": c["author"],
                          "subject": c["subject"], "pr": pr["number"] if pr else None, "reasons": reasons})
    return {
        "label": label, "start": start, "end": end, "history": history, "fixes": fixes,
        "cochange": cochange_for(conn, repo, path, model=cochange_model),
        "open_issues": open_issues_mentioning(conn, repo, path),
    }
