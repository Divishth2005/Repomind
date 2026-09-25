"""Structured retrieval: answers to concrete repository questions straight
from the relational model (build plan Sec 19A). Everything returns plain
dicts that carry citable identifiers (commit SHAs, PR/issue numbers).

PR<->commit links come from two places and are labelled as such:
  * "linked"  -- GitHub's own PR commit list (exact)
  * "subject" -- a "(#123)" suffix on a commit subject, GitHub's default for
                 squash merges, used when the PR's own commits are missing
                 from history. This is a heuristic recovered at query time;
                 the stored data is unchanged.
"""
import re
import sqlite3
from dataclasses import dataclass

SUBJECT_PR = re.compile(r"\(#(\d+)\)\s*$")


@dataclass(frozen=True)
class Scope:
    kind: str  # "file" | "dir"
    path: str  # dirs always end with "/"

    @property
    def label(self) -> str:
        return self.path


def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _scope_clause(scope: Scope) -> tuple[str, str]:
    if scope.kind == "file":
        return "f.path = ?", scope.path
    return "f.path LIKE ? ESCAPE '\\'", _esc(scope.path) + "%"


def _chunks(seq, n=500):
    seq = list(seq)
    for i in range(0, len(seq), n):
        yield seq[i : i + n]


def _bot(include_bots: bool) -> str:
    return "" if include_bots else "AND d.is_bot = 0"


def resolve_scope(conn: sqlite3.Connection, repo: str, mention: str) -> list[Scope]:
    """Turn 'src/flask/app.py', 'app.py', 'docs/patterns' into files/directories."""
    m = mention.strip().strip("?.,;:()\"'`")
    if not m:
        return []
    if conn.execute("SELECT 1 FROM file WHERE repository_id=? AND path=?", (repo, m)).fetchone():
        return [Scope("file", m)]
    prefix = m.rstrip("/") + "/"
    if conn.execute(
        "SELECT 1 FROM file WHERE repository_id=? AND path LIKE ? ESCAPE '\\' LIMIT 1", (repo, _esc(prefix) + "%")
    ).fetchone():
        return [Scope("dir", prefix)]
    rows = conn.execute(
        """SELECT f.path, COUNT(cf.commit_file_id) n FROM file f
           LEFT JOIN commit_file cf ON cf.file_id = f.file_id
           WHERE f.repository_id = ? AND f.path LIKE ? ESCAPE '\\'
           GROUP BY f.file_id ORDER BY n DESC LIMIT 3""",
        (repo, "%/" + _esc(m)),
    ).fetchall()
    return [Scope("file", r["path"]) for r in rows]


def contributors(conn, repo, scope: Scope, limit=10, include_bots=False) -> dict:
    clause, arg = _scope_clause(scope)
    where = f"f.repository_id = ? AND {clause} {_bot(include_bots)}"
    base = """FROM commit_file cf JOIN file f ON f.file_id = cf.file_id
              JOIN commit_ c ON c.commit_id = cf.commit_id
              JOIN developer d ON d.developer_id = c.author_developer_id"""
    total = conn.execute(f"SELECT COUNT(DISTINCT c.commit_id) {base} WHERE {where}", (repo, arg)).fetchone()[0]
    rows = conn.execute(
        f"""SELECT d.developer_id, COALESCE(d.display_name, d.github_login) AS name, d.github_login,
                   COUNT(DISTINCT c.commit_id) AS commits,
                   MIN(datetime(c.timestamp)) AS first_commit, MAX(datetime(c.timestamp)) AS last_commit
            {base} WHERE {where} GROUP BY d.developer_id ORDER BY commits DESC LIMIT ?""",
        (repo, arg, limit),
    ).fetchall()
    return {
        "scope": scope.label,
        "total_commits": total,
        "contributors": [dict(r, share=(r["commits"] / total if total else 0.0)) for r in rows],
    }


def _linked_prs(conn, repo, commit_ids) -> dict[str, list[int]]:
    out: dict[str, list[int]] = {}
    for chunk in _chunks(commit_ids):
        q = ",".join("?" * len(chunk))
        for r in conn.execute(
            f"""SELECT pc.commit_id, p.github_number FROM pr_commit pc
                JOIN pull_request p ON p.pr_id = pc.pr_id
                WHERE p.repository_id = ? AND pc.commit_id IN ({q})""",
            (repo, *chunk),
        ):
            out.setdefault(r["commit_id"], []).append(r["github_number"])
    return out


def history(conn, repo, scope: Scope, limit=15, include_bots=True) -> list[dict]:
    """Most recent commits touching the scope, newest first, with the PRs they belong to."""
    clause, arg = _scope_clause(scope)
    rows = conn.execute(
        f"""SELECT c.commit_id, c.subject, c.timestamp, COALESCE(d.display_name, d.github_login) AS author, d.is_bot
            FROM commit_ c JOIN developer d ON d.developer_id = c.author_developer_id
            WHERE c.repository_id = ? {_bot(include_bots)} AND c.commit_id IN
              (SELECT cf.commit_id FROM commit_file cf JOIN file f ON f.file_id = cf.file_id
               WHERE f.repository_id = ? AND {clause})
            ORDER BY datetime(c.timestamp) DESC LIMIT ?""",
        (repo, repo, arg, limit),
    ).fetchall()
    linked = _linked_prs(conn, repo, [r["commit_id"] for r in rows])
    out = []
    for r in rows:
        hint = SUBJECT_PR.search(r["subject"] or "")
        out.append(
            {
                "sha": r["commit_id"],
                "subject": r["subject"],
                "date": r["timestamp"],
                "author": r["author"],
                "is_bot": bool(r["is_bot"]),
                "prs_linked": sorted(set(linked.get(r["commit_id"], []))),
                "pr_from_subject": int(hint.group(1)) if hint else None,
            }
        )
    return out


def scope_commit_ids(conn, repo, scope: Scope) -> list[str]:
    clause, arg = _scope_clause(scope)
    return [
        r[0]
        for r in conn.execute(
            f"""SELECT DISTINCT cf.commit_id FROM commit_file cf JOIN file f ON f.file_id = cf.file_id
                WHERE f.repository_id = ? AND {clause}""",
            (repo, arg),
        )
    ]


def scope_pr_numbers(conn, repo, scope: Scope) -> dict[int, str]:
    """PR number -> how it was linked ('linked' or 'subject') for PRs touching the scope."""
    commit_ids = scope_commit_ids(conn, repo, scope)
    found: dict[int, str] = {}
    for cid, nums in _linked_prs(conn, repo, commit_ids).items():
        for n in nums:
            found[n] = "linked"
    for chunk in _chunks(commit_ids):
        q = ",".join("?" * len(chunk))
        for r in conn.execute(f"SELECT subject FROM commit_ WHERE commit_id IN ({q})", chunk):
            m = SUBJECT_PR.search(r["subject"] or "")
            if m:
                found.setdefault(int(m.group(1)), "subject")
    return found


def _prs_by_number(conn, repo, numbers) -> list[sqlite3.Row]:
    rows = []
    for chunk in _chunks(numbers):
        q = ",".join("?" * len(chunk))
        rows += conn.execute(
            f"""SELECT p.pr_id, p.github_number, p.title, p.state, p.created_at, p.merged_at,
                       COALESCE(d.display_name, d.github_login) AS author
                FROM pull_request p LEFT JOIN developer d ON d.developer_id = p.author_developer_id
                WHERE p.repository_id = ? AND p.github_number IN ({q})""",
            (repo, *chunk),
        ).fetchall()
    return rows


def prs_touching(conn, repo, scope: Scope, limit=10) -> list[dict]:
    found = scope_pr_numbers(conn, repo, scope)
    rows = sorted(_prs_by_number(conn, repo, found), key=lambda r: r["merged_at"] or r["created_at"] or "", reverse=True)
    return [
        {"number": r["github_number"], "title": r["title"], "state": r["state"], "author": r["author"],
         "created_at": r["created_at"], "merged_at": r["merged_at"], "link": found[r["github_number"]]}
        for r in rows[:limit]
    ]


def reviewers(conn, repo, scope: Scope, limit=10, include_bots=False) -> list[dict]:
    """People who reviewed PRs touching the scope (not their own PRs)."""
    numbers = list(scope_pr_numbers(conn, repo, scope))
    tally: dict[str, dict] = {}
    for chunk in _chunks(numbers):
        q = ",".join("?" * len(chunk))
        for r in conn.execute(
            f"""SELECT d.developer_id, COALESCE(d.display_name, d.github_login) AS name, d.github_login,
                       COUNT(DISTINCT p.pr_id) AS prs_reviewed, MAX(rv.submitted_at) AS last_review
                FROM review rv JOIN pull_request p ON p.pr_id = rv.pr_id
                JOIN developer d ON d.developer_id = rv.reviewer_developer_id
                WHERE p.repository_id = ? AND p.github_number IN ({q})
                  AND rv.reviewer_developer_id IS NOT p.author_developer_id {_bot(include_bots)}
                GROUP BY d.developer_id""",
            (repo, *chunk),
        ):
            t = tally.setdefault(r["developer_id"], dict(r, prs_reviewed=0))
            t["prs_reviewed"] += r["prs_reviewed"]
            t["last_review"] = max(t["last_review"] or "", r["last_review"] or "")
    return sorted(tally.values(), key=lambda t: -t["prs_reviewed"])[:limit]


def pr_link_coverage(conn, repo) -> dict:
    """How much of this repo's PR data can be tied to code, so answers can
    say when 'no PRs found' means 'not linkable' rather than 'none exist'."""
    prs = conn.execute("SELECT COUNT(*) FROM pull_request WHERE repository_id=?", (repo,)).fetchone()[0]
    linked = conn.execute(
        """SELECT COUNT(DISTINCT p.pr_id) FROM pull_request p JOIN pr_commit pc ON pc.pr_id = p.pr_id
           JOIN commit_file cf ON cf.commit_id = pc.commit_id WHERE p.repository_id = ?""", (repo,)).fetchone()[0]
    hinted = conn.execute(
        "SELECT COUNT(*) FROM commit_ WHERE repository_id=? AND subject GLOB '*(#[0-9]*)'", (repo,)).fetchone()[0]
    return {"pull_requests": prs, "linked_via_commits": linked, "commits_with_pr_number_in_subject": hinted}


def _issues_for_prs(conn, repo, pr_ids) -> list[dict]:
    out = []
    for chunk in _chunks(pr_ids):
        q = ",".join("?" * len(chunk))
        out += [
            dict(r)
            for r in conn.execute(
                f"""SELECT DISTINCT i.github_number AS number, i.title, i.state FROM pr_issue pi
                    JOIN issue i ON i.github_number = pi.issue_number AND i.repository_id = ?
                    WHERE pi.pr_id IN ({q})""",
                (repo, *chunk),
            )
        ]
    return out


def pr_context(conn, repo, number: int) -> dict | None:
    pr = conn.execute(
        """SELECT p.pr_id, p.github_number, p.title, p.body, p.state, p.created_at, p.merged_at,
                  COALESCE(d.display_name, d.github_login) AS author
           FROM pull_request p LEFT JOIN developer d ON d.developer_id = p.author_developer_id
           WHERE p.repository_id = ? AND p.github_number = ?""", (repo, number)).fetchone()
    if not pr:
        return None
    reviews = [
        dict(r)
        for r in conn.execute(
            """SELECT COALESCE(d.display_name, d.github_login) AS reviewer, rv.state, rv.submitted_at, rv.body
               FROM review rv LEFT JOIN developer d ON d.developer_id = rv.reviewer_developer_id
               WHERE rv.pr_id = ? ORDER BY rv.submitted_at""", (pr["pr_id"],))
    ]
    commits = [
        dict(r)
        for r in conn.execute(
            """SELECT c.commit_id AS sha, c.subject, c.timestamp FROM pr_commit pc
               JOIN commit_ c ON c.commit_id = pc.commit_id WHERE pc.pr_id = ? ORDER BY c.timestamp""", (pr["pr_id"],))
    ]
    files = [
        r[0]
        for r in conn.execute(
            """SELECT DISTINCT f.path FROM pr_commit pc JOIN commit_file cf ON cf.commit_id = pc.commit_id
               JOIN file f ON f.file_id = cf.file_id WHERE pc.pr_id = ? ORDER BY f.path LIMIT 25""", (pr["pr_id"],))
    ]
    subject_commits = [
        dict(r)
        for r in conn.execute(
            "SELECT commit_id AS sha, subject, timestamp FROM commit_ WHERE repository_id = ? AND subject LIKE ?",
            (repo, f"%(#{number})"),
        )
    ]
    return {
        "number": pr["github_number"], "title": pr["title"], "body": (pr["body"] or "")[:1200],
        "state": pr["state"], "author": pr["author"], "created_at": pr["created_at"], "merged_at": pr["merged_at"],
        "reviews": reviews, "commits": commits, "commits_from_subject": subject_commits,
        "files": files, "closes_issues": _issues_for_prs(conn, repo, [pr["pr_id"]]),
    }


def issue_context(conn, repo, number: int) -> dict | None:
    issue = conn.execute(
        """SELECT i.github_number, i.title, i.body, i.state, i.created_at, i.closed_at, i.labels,
                  COALESCE(d.display_name, d.github_login) AS author
           FROM issue i LEFT JOIN developer d ON d.developer_id = i.author_developer_id
           WHERE i.repository_id = ? AND i.github_number = ?""", (repo, number)).fetchone()
    if not issue:
        return None
    prs = [
        dict(r)
        for r in conn.execute(
            """SELECT p.github_number AS number, p.title, p.state, p.merged_at FROM pr_issue pi
               JOIN pull_request p ON p.pr_id = pi.pr_id WHERE p.repository_id = ? AND pi.issue_number = ?""",
            (repo, number))
    ]
    return {
        "number": issue["github_number"], "title": issue["title"], "body": (issue["body"] or "")[:1200],
        "state": issue["state"], "author": issue["author"], "created_at": issue["created_at"],
        "closed_at": issue["closed_at"], "labels": issue["labels"], "closed_by_prs": prs,
    }


def commit_context(conn, repo, sha_prefix: str) -> dict | None:
    row = conn.execute(
        """SELECT c.commit_id, c.subject, c.body, c.timestamp, COALESCE(d.display_name, d.github_login) AS author
           FROM commit_ c JOIN developer d ON d.developer_id = c.author_developer_id
           WHERE c.repository_id = ? AND c.commit_id LIKE ? LIMIT 1""", (repo, sha_prefix + "%")).fetchone()
    if not row:
        return None
    files = [
        dict(r)
        for r in conn.execute(
            """SELECT f.path, cf.additions, cf.deletions FROM commit_file cf JOIN file f ON f.file_id = cf.file_id
               WHERE cf.commit_id = ? ORDER BY f.path LIMIT 30""", (row["commit_id"],))
    ]
    linked = _linked_prs(conn, repo, [row["commit_id"]]).get(row["commit_id"], [])
    hint = SUBJECT_PR.search(row["subject"] or "")
    return {
        "sha": row["commit_id"], "subject": row["subject"], "body": (row["body"] or "")[:1200],
        "date": row["timestamp"], "author": row["author"], "files": files,
        "prs_linked": sorted(set(linked)), "pr_from_subject": int(hint.group(1)) if hint else None,
    }


def find_developers(conn, repo, name: str, limit=3) -> list[dict]:
    """Developers whose display name or login equals `name` (case-insensitive), most active first."""
    rows = conn.execute(
        """SELECT d.developer_id, COALESCE(d.display_name, d.github_login) AS name, d.github_login, d.is_bot,
                  (SELECT COUNT(*) FROM commit_ c WHERE c.author_developer_id = d.developer_id AND c.repository_id = ?) AS commits,
                  (SELECT COUNT(*) FROM pull_request p WHERE p.author_developer_id = d.developer_id AND p.repository_id = ?) AS prs
           FROM developer d WHERE lower(d.display_name) = lower(?) OR lower(d.github_login) = lower(?)
           ORDER BY commits + prs DESC LIMIT ?""", (repo, repo, name, name, limit)).fetchall()
    return [dict(r) for r in rows if r["commits"] + r["prs"] > 0]


def developer_activity(conn, repo, developer_id: str) -> dict:
    r = (developer_id, repo)
    commits = conn.execute(
        """SELECT COUNT(*) n, MIN(datetime(timestamp)) first, MAX(datetime(timestamp)) last
           FROM commit_ WHERE author_developer_id = ? AND repository_id = ?""", r).fetchone()
    top_files = [
        dict(x)
        for x in conn.execute(
            """SELECT f.path, COUNT(DISTINCT c.commit_id) commits FROM commit_ c
               JOIN commit_file cf ON cf.commit_id = c.commit_id JOIN file f ON f.file_id = cf.file_id
               WHERE c.author_developer_id = ? AND c.repository_id = ? GROUP BY f.path
               ORDER BY commits DESC LIMIT 8""", r)
    ]
    prs = conn.execute("SELECT COUNT(*) FROM pull_request WHERE author_developer_id = ? AND repository_id = ?", r).fetchone()[0]
    reviews = conn.execute(
        """SELECT COUNT(*) FROM review rv JOIN pull_request p ON p.pr_id = rv.pr_id
           WHERE rv.reviewer_developer_id = ? AND p.repository_id = ?""", r).fetchone()[0]
    return {"commits": commits["n"], "first_commit": commits["first"], "last_commit": commits["last"],
            "top_files": top_files, "prs_authored": prs, "reviews_given": reviews}
