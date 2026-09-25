"""Per-repository data-pipeline statistics (build plan Sec 40.1): dataset
size, validation, missing/duplicate fields, identity-resolution coverage,
bot detection, and how well GitHub data links to Git data."""
import json
import sqlite3
from pathlib import Path


def _scalar(conn, sql, params=()):
    return conn.execute(sql, params).fetchone()[0]


def dataset_stats(conn: sqlite3.Connection, repository_id: str, processed_dir: Path) -> dict:
    r = (repository_id,)
    commits = _scalar(conn, "SELECT COUNT(*) FROM commit_ WHERE repository_id=?", r)
    merges = _scalar(conn, "SELECT COUNT(*) FROM commit_ WHERE repository_id=? AND is_merge=1", r)
    no_files = _scalar(
        conn,
        """SELECT COUNT(*) FROM commit_ c WHERE c.repository_id=? AND NOT EXISTS
           (SELECT 1 FROM commit_file cf WHERE cf.commit_id=c.commit_id)""", r)
    span = conn.execute("SELECT MIN(timestamp), MAX(timestamp) FROM commit_ WHERE repository_id=?", r).fetchone()

    committers = conn.execute(
        """SELECT d.developer_id, d.is_bot, d.identity_confidence, d.github_login, COUNT(*) n
           FROM commit_ c JOIN developer d ON d.developer_id=c.author_developer_id
           WHERE c.repository_id=? GROUP BY d.developer_id""", r).fetchall()
    bot_devs = [x for x in committers if x["is_bot"]]
    human = [x for x in committers if not x["is_bot"]]
    human_commits = sum(x["n"] for x in human)
    by_conf = {}
    for x in human:
        by_conf[x["identity_confidence"]] = by_conf.get(x["identity_confidence"], 0) + x["n"]
    top10 = sorted(human, key=lambda x: -x["n"])[:10]

    prs = _scalar(conn, "SELECT COUNT(*) FROM pull_request WHERE repository_id=?", r)
    reviews = _scalar(conn, "SELECT COUNT(*) FROM review rv JOIN pull_request p ON p.pr_id=rv.pr_id WHERE p.repository_id=?", r)
    issues = _scalar(conn, "SELECT COUNT(*) FROM issue WHERE repository_id=?", r)
    prs_linked = _scalar(
        conn,
        """SELECT COUNT(DISTINCT p.pr_id) FROM pull_request p JOIN pr_commit pc ON pc.pr_id=p.pr_id
           JOIN commit_file cf ON cf.commit_id=pc.commit_id WHERE p.repository_id=?""", r)
    reviews_linked = _scalar(
        conn,
        """SELECT COUNT(*) FROM review rv JOIN pull_request p ON p.pr_id=rv.pr_id
           WHERE p.repository_id=? AND EXISTS (SELECT 1 FROM pr_commit pc JOIN commit_file cf
           ON cf.commit_id=pc.commit_id WHERE pc.pr_id=p.pr_id)""", r)

    validation = {}
    vp = Path(processed_dir) / "validation_report.json"
    if vp.exists():
        validation = json.loads(vp.read_text())

    frac = lambda a, b: (a / b) if b else None
    return {
        "commits": commits,
        "first_commit": span[0],
        "last_commit": span[1],
        "files": _scalar(conn, "SELECT COUNT(*) FROM file WHERE repository_id=?", r),
        "merge_commit_share": frac(merges, commits),
        "commits_without_files_share": frac(no_files, commits),
        "committer_identities": len(committers),
        "bot_identities": len(bot_devs),
        "bot_commit_share": frac(sum(x["n"] for x in bot_devs), commits),
        "human_commit_share_by_identity_confidence": {k: v / human_commits for k, v in by_conf.items()} if human_commits else {},
        "top10_committers_linked_to_github_login": sum(1 for x in top10 if x["github_login"]),
        "issues": issues,
        "pull_requests": prs,
        "reviews": reviews,
        "pr_file_link_rate": frac(prs_linked, prs),
        "review_file_link_rate": frac(reviews_linked, reviews),
        "validation_ok": validation.get("ok"),
        "validation_issue_count": validation.get("issue_count"),
    }
