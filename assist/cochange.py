"""Co-change: which files tend to change in the same commit as a given file.

A statistical association mined from history, NOT a dependency graph: two
files can change together because of one big refactor, a habit, or a real
coupling. Very large commits (default > 30 files) are ignored because they
create spurious pairs; bot commits and merge commits (no file list) are
excluded. `skip_boilerplate` also drops changelogs, lockfiles, requirements files and
CI/pre-commit config, which change with almost everything and make co-change look
better than it is.
"""
import re
import sqlite3
from collections import Counter
from datetime import datetime, timezone

BOILERPLATE_RE = re.compile(
    r"(^|/)(changes|changelog|history|news|releases?|authors|contributors)(\.[a-z]+)?$|\.lock$|package-lock\.json$|"
    r"(^|/)requirements([^/]*\.(txt|in)$|/)|(^|/)\.github/|\.pre-commit|(^|/)\.gitignore$", re.IGNORECASE)
TEST_HINT = ("test", "tests", "spec", "specs", "__tests__")


def is_test_path(path: str) -> bool:
    p = path.lower()
    parts = p.split("/")
    name = parts[-1]
    return (any(part in TEST_HINT for part in parts[:-1]) or name.startswith("test_") or name.startswith("tests.")
            or "_test." in name or ".test." in name or ".spec." in name or name.endswith("_test.go"))


def load_commits(conn: sqlite3.Connection, repo: str, max_files: int = 30, include_bots: bool = False,
                 skip_boilerplate: bool = False):
    """[(datetime, frozenset(paths))] oldest first, one entry per commit that changed 1..max_files files."""
    bot = "" if include_bots else "AND d.is_bot = 0"
    files: dict[str, tuple] = {}
    for r in conn.execute(
        f"""SELECT c.commit_id, c.timestamp, f.path FROM commit_file cf
            JOIN commit_ c ON c.commit_id = cf.commit_id JOIN file f ON f.file_id = cf.file_id
            JOIN developer d ON d.developer_id = c.author_developer_id
            WHERE c.repository_id = ? {bot}""", (repo,)):
        if skip_boilerplate and BOILERPLATE_RE.search(r["path"]):
            continue
        entry = files.setdefault(r["commit_id"], (r["timestamp"], set()))
        entry[1].add(r["path"])
    out = []
    for ts, paths in files.values():
        if 1 <= len(paths) <= max_files:
            dt = datetime.fromisoformat(ts)
            out.append((dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc), frozenset(paths)))
    out.sort(key=lambda x: x[0])
    return out


class CoChange:
    def __init__(self, commits):
        self.file_count: Counter = Counter()
        self.pairs: dict[str, Counter] = {}
        for _, paths in commits:
            self.file_count.update(paths)
            if len(paths) > 1:
                for a in paths:
                    c = self.pairs.setdefault(a, Counter())
                    for b in paths:
                        if a != b:
                            c[b] += 1

    def partners(self, path: str, k: int = 5, min_support: int = 2) -> list[dict]:
        """Files that changed with `path`, by confidence = P(partner changes | path changes)."""
        n = self.file_count.get(path, 0)
        rows = [
            {"path": other, "cochanges": c, "confidence": c / n, "reverse_confidence": c / self.file_count[other]}
            for other, c in self.pairs.get(path, {}).items() if c >= min_support
        ]
        rows.sort(key=lambda r: (-r["confidence"], -r["cochanges"], r["path"]))
        return rows[:k]
