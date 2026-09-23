"""Example relationship queries over the normalized database -- the first
concrete proof that Developer -> Commit -> File (and PR/Review/Issue
extensions) actually work as a queryable knowledge map (build plan, Phase 5).
"""
import sqlite3


def developer_files(conn: sqlite3.Connection, developer_id: str, limit: int = 20):
    """Files a developer has touched, most-touched first."""
    sql = """
        SELECT f.path, COUNT(*) AS touches
        FROM commit_file cf
        JOIN commit_ c ON c.commit_id = cf.commit_id
        JOIN file f ON f.file_id = cf.file_id
        WHERE c.author_developer_id = ?
        GROUP BY f.path
        ORDER BY touches DESC
        LIMIT ?
    """
    return conn.execute(sql, (developer_id, limit)).fetchall()


def file_developers(conn: sqlite3.Connection, file_path: str, repository_id: str, limit: int = 20):
    """Developers who have touched a file, most-active first."""
    sql = """
        SELECT d.developer_id, d.display_name, d.github_login, COUNT(*) AS touches
        FROM commit_file cf
        JOIN commit_ c ON c.commit_id = cf.commit_id
        JOIN file f ON f.file_id = cf.file_id
        JOIN developer d ON d.developer_id = c.author_developer_id
        WHERE f.path = ? AND f.repository_id = ?
        GROUP BY d.developer_id
        ORDER BY touches DESC
        LIMIT ?
    """
    return conn.execute(sql, (file_path, repository_id, limit)).fetchall()


def top_contributors(conn: sqlite3.Connection, repository_id: str, limit: int = 20, exclude_bots: bool = True):
    """Developers ranked by raw commit count -- a signal, not a final
    expertise score (the build plan is explicit that this alone is
    insufficient; see analysis/ once Module 4 lands)."""
    sql = """
        SELECT d.developer_id, d.display_name, d.github_login, d.is_bot, COUNT(*) AS commit_count
        FROM commit_ c
        JOIN developer d ON d.developer_id = c.author_developer_id
        WHERE c.repository_id = ?
        {bot_filter}
        GROUP BY d.developer_id
        ORDER BY commit_count DESC
        LIMIT ?
    """.format(bot_filter="AND d.is_bot = 0" if exclude_bots else "")
    return conn.execute(sql, (repository_id, limit)).fetchall()


def developer_pull_requests(conn: sqlite3.Connection, developer_id: str, limit: int = 20):
    sql = """
        SELECT github_number, title, state, created_at, merged_at
        FROM pull_request
        WHERE author_developer_id = ?
        ORDER BY created_at DESC
        LIMIT ?
    """
    return conn.execute(sql, (developer_id, limit)).fetchall()


def developer_reviews(conn: sqlite3.Connection, developer_id: str, limit: int = 20):
    sql = """
        SELECT r.review_id, p.github_number, p.title, r.state, r.submitted_at
        FROM review r
        JOIN pull_request p ON p.pr_id = r.pr_id
        WHERE r.reviewer_developer_id = ?
        ORDER BY r.submitted_at DESC
        LIMIT ?
    """
    return conn.execute(sql, (developer_id, limit)).fetchall()


def file_commits(conn: sqlite3.Connection, file_path: str, repository_id: str, limit: int = 20):
    sql = """
        SELECT c.commit_id, c.subject, c.timestamp, c.author_developer_id
        FROM commit_file cf
        JOIN commit_ c ON c.commit_id = cf.commit_id
        JOIN file f ON f.file_id = cf.file_id
        WHERE f.path = ? AND f.repository_id = ?
        ORDER BY c.timestamp DESC
        LIMIT ?
    """
    return conn.execute(sql, (file_path, repository_id, limit)).fetchall()


def pr_for_commit(conn: sqlite3.Connection, commit_sha: str):
    sql = """
        SELECT p.github_number, p.title, p.state
        FROM pr_commit pc
        JOIN pull_request p ON p.pr_id = pc.pr_id
        WHERE pc.commit_id = ?
    """
    return conn.execute(sql, (commit_sha,)).fetchall()


def component_contributors(conn: sqlite3.Connection, repository_id: str, path_prefix: str, limit: int = 20):
    """Developers active under a directory prefix -- the plan's suggested
    stand-in for a first-class Module entity: derive components from paths."""
    sql = """
        SELECT d.developer_id, d.display_name, d.github_login, COUNT(*) AS touches
        FROM commit_file cf
        JOIN commit_ c ON c.commit_id = cf.commit_id
        JOIN file f ON f.file_id = cf.file_id
        JOIN developer d ON d.developer_id = c.author_developer_id
        WHERE f.repository_id = ? AND f.path LIKE ? || '%'
        GROUP BY d.developer_id
        ORDER BY touches DESC
        LIMIT ?
    """
    return conn.execute(sql, (repository_id, path_prefix, limit)).fetchall()
