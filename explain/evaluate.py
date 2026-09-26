"""History-coverage measurement for Module 9 (no LLM involved).

Samples Python functions and measures what the line-level history gives us:
how much narrower it is than the whole file's history, whether its commits
are in the database, and how often they reach a pull request and an issue.
This measures the retrieval half of code explanation; whether an LLM then
explains well is a separate question.
"""
import random
import statistics
import sqlite3

from explain.history import gather
from explain.source import SourceError, python_symbols, read_file
from retrieval import structured as st


def _median(xs):
    return statistics.median(xs) if xs else None


def sample_and_measure(conn: sqlite3.Connection, repo: str, n: int = 25, seed: int = 0, min_lines: int = 8) -> dict:
    rng = random.Random(seed)
    files = conn.execute(
        """SELECT f.path, COUNT(DISTINCT cf.commit_id) AS commits FROM file f JOIN commit_file cf ON cf.file_id = f.file_id
           WHERE f.repository_id = ? AND f.path LIKE '%.py' GROUP BY f.file_id HAVING commits >= 20""", (repo,)).fetchall()
    rng.shuffle(files)
    picks = []
    for row in files:
        if len(picks) >= n:
            break
        try:
            syms = [s for s in python_symbols(read_file(repo, row["path"])) if s.kind == "function" and s.end - s.start + 1 >= min_lines]
        except SourceError:
            continue  # file deleted at HEAD or not parseable
        if syms:
            picks.append((row["path"], row["commits"], rng.choice(syms)))

    rows = []
    for path, file_commits, sym in picks:
        h = gather(conn, repo, path, sym.start, sym.end)
        if not h["commits"] and not h["range_commits_found_in_git"]:
            continue
        with_pr = sum(1 for c in h["commits"] if c["prs"])
        existing_prs = len(st._prs_by_number(conn, repo, h["pr_numbers"])) if h["pr_numbers"] else 0
        rows.append({
            "path": path, "function": sym.name, "file_commits": file_commits,
            "function_commits": h["range_commits_found_in_git"],
            "share_in_database": (len(h["commits"]) / h["range_commits_found_in_git"]) if h["range_commits_found_in_git"] else None,
            "share_with_pr_number": (with_pr / len(h["commits"])) if h["commits"] else None,
            "distinct_prs": len(h["pr_numbers"]), "prs_found_in_database": existing_prs,
            "issues": len(h["issues"]),
        })
    have = lambda k: [r[k] for r in rows if r[k] is not None]
    return {
        "functions": len(rows),
        "median_file_commits": _median([r["file_commits"] for r in rows]),
        "median_function_commits": _median([r["function_commits"] for r in rows]),
        "median_function_share_of_file": _median([r["function_commits"] / r["file_commits"] for r in rows]),
        "commits_found_in_database": statistics.mean(have("share_in_database")) if have("share_in_database") else None,
        "commits_with_pr_number": statistics.mean(have("share_with_pr_number")) if have("share_with_pr_number") else None,
        "functions_with_a_pr": sum(1 for r in rows if r["prs_found_in_database"] > 0) / len(rows) if rows else None,
        "functions_with_an_issue": sum(1 for r in rows if r["issues"] > 0) / len(rows) if rows else None,
        "rows": rows,
    }


def print_stats(repo: str, r: dict):
    pct = lambda x: "n/a" if x is None else f"{x:.0%}"
    if not r["functions"]:
        print(f"{repo}: no Python functions could be sampled")
        return
    print(f"\n{repo}: {r['functions']} sampled Python functions (>= 8 lines, in files with >= 20 commits)")
    print(f"  commits per function (median) {r['median_function_commits']:.0f} vs {r['median_file_commits']:.0f} for its whole file "
          f"(function history is a median {r['median_function_share_of_file']:.0%} of the file's)")
    print(f"  function commits found in the database:      {pct(r['commits_found_in_database'])}")
    print(f"  function commits that reach a PR number:     {pct(r['commits_with_pr_number'])}")
    print(f"  functions with at least one PR in the data:  {pct(r['functions_with_a_pr'])}")
    print(f"  functions with at least one closed issue:    {pct(r['functions_with_an_issue'])}")
