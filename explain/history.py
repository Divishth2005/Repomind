"""Gather the recorded history of a piece of code from the database:
the commits that changed it, the pull requests and issues behind them, who
reviewed, and who changed it. Nothing here calls an LLM."""
import sqlite3

from explain.source import line_history
from retrieval import structured as st
from retrieval.hybrid import Retriever


def _commit_rows(conn, repo, shas):
    rows = {}
    for chunk in st._chunks(shas):
        q = ",".join("?" * len(chunk))
        for r in conn.execute(
            f"""SELECT c.commit_id, c.subject, c.body, c.timestamp, COALESCE(d.display_name, d.github_login) AS author,
                       d.is_bot FROM commit_ c JOIN developer d ON d.developer_id = c.author_developer_id
                WHERE c.repository_id = ? AND c.commit_id IN ({q})""", (repo, *chunk)):
            rows[r["commit_id"]] = dict(r)
    return rows


def gather(conn: sqlite3.Connection, repo: str, path: str, start: int, end: int,
           max_commits: int = 40, max_prs: int = 8, max_issues: int = 8, retriever: Retriever | None = None) -> dict:
    shas = line_history(repo, path, start, end, max_commits)
    found = _commit_rows(conn, repo, shas)
    linked = st._linked_prs(conn, repo, list(found))

    commits, pr_order = [], []
    for sha in shas:
        row = found.get(sha)
        if not row:
            continue
        hint = st.SUBJECT_PR.search(row["subject"] or "")
        prs = sorted(set(linked.get(sha, [])))
        how = "linked" if prs else ("subject" if hint else None)
        if not prs and hint:
            prs = [int(hint.group(1))]
        commits.append({**row, "prs": prs, "pr_link": how})
        for n in prs:
            if n not in pr_order:
                pr_order.append(n)

    prs = [c for c in (st.pr_context(conn, repo, n) for n in pr_order[:max_prs]) if c]
    for p in prs:
        p["link"] = next((c["pr_link"] for c in commits if p["number"] in c["prs"]), None)
    issue_numbers = []
    for p in prs:
        for i in p["closes_issues"]:
            if i["number"] not in issue_numbers:
                issue_numbers.append(i["number"])
    issues = [c for c in (st.issue_context(conn, repo, n) for n in issue_numbers[:max_issues]) if c]

    authors: dict[str, dict] = {}
    for c in commits:
        a = authors.setdefault(c["author"], {"name": c["author"], "commits": 0, "is_bot": bool(c["is_bot"]),
                                             "first": c["timestamp"], "last": c["timestamp"]})
        a["commits"] += 1
        a["first"], a["last"] = min(a["first"], c["timestamp"]), max(a["last"], c["timestamp"])
    reviewers: dict[str, int] = {}
    for p in prs:
        for rv in {r["reviewer"] for r in p["reviews"] if r["reviewer"] and r["reviewer"] != p["author"]}:
            reviewers[rv] = reviewers.get(rv, 0) + 1

    retriever = retriever or Retriever(conn, repo)
    return {
        "range_commits_found_in_git": len(shas), "commits": commits, "prs": prs, "issues": issues,
        "authors": sorted(authors.values(), key=lambda a: -a["commits"]),
        "reviewers": sorted(reviewers.items(), key=lambda kv: -kv[1]),
        "file_assessment": retriever.assess(st.Scope("file", path)),
        "commits_missing_from_database": len(shas) - len(found),
        "prs_beyond_limit": max(0, len(pr_order) - max_prs),
        "pr_numbers": pr_order,
    }
