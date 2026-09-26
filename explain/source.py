"""Read code from the local clone and find the commits that touched a piece of it.

Code comes from `git show HEAD:<path>` in data/raw/_clones/<name>, the same
clone the database was built from, so commit ids match the database.
History of a *piece* of code uses `git log -L start,end:path`, which follows
those exact lines back through time (much narrower than the whole file's
history). Function boundaries are found with Python's `ast`; other languages
must be given as a line range.
"""
import ast
import subprocess
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLONES_DIR = ROOT / "data" / "raw" / "_clones"


class SourceError(RuntimeError):
    pass


@dataclass(frozen=True)
class Symbol:
    name: str  # qualified, e.g. "Flask.url_for"
    kind: str  # function | class
    start: int
    end: int


def clone_path(repo: str) -> Path:
    path = CLONES_DIR / repo.split("/")[1]
    if not (path / ".git").exists():
        raise SourceError(f"No local clone for {repo} at {path}. Run: python pipeline.py --repo {repo}")
    return path


def _git(clone: Path, *args: str) -> str:
    out = subprocess.run(["git", "-C", str(clone), *args], capture_output=True, text=True)
    if out.returncode != 0:
        raise SourceError(out.stderr.strip()[:300] or "git command failed")
    return out.stdout


def read_file(repo: str, path: str, ref: str = "HEAD") -> str:
    try:
        return _git(clone_path(repo), "show", f"{ref}:{path}")
    except SourceError as e:
        if "does not exist" in str(e) or "exists on disk, but not in" in str(e):
            raise SourceError(f"'{path}' does not exist in the latest version of {repo}. Check the file path.")
        raise SourceError(f"Could not read '{path}' in {repo}: {e}")


def python_symbols(source: str) -> list[Symbol]:
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        raise SourceError(f"Could not parse this file as Python ({e.msg}, line {e.lineno}); use --lines instead.")
    out: list[Symbol] = []

    def visit(node, prefix):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                start = min([d.lineno for d in child.decorator_list] + [child.lineno])
                q = f"{prefix}{child.name}"
                out.append(Symbol(q, "class" if isinstance(child, ast.ClassDef) else "function", start, child.end_lineno))
                visit(child, q + ".")
            else:
                visit(child, prefix)

    visit(tree, "")
    return out


def find_symbols(source: str, name: str) -> list[Symbol]:
    """Exact qualified match first ('Flask.url_for'), else any symbol whose last part matches ('url_for')."""
    symbols = python_symbols(source)
    exact = [s for s in symbols if s.name == name]
    return exact or [s for s in symbols if s.name.split(".")[-1] == name]


def line_history(repo: str, path: str, start: int, end: int, limit: int = 40) -> list[str]:
    """Commit ids (newest first) that changed lines start..end of path."""
    out = _git(clone_path(repo), "log", "-n", str(limit), f"-L{start},{end}:{path}", "--format=%H", "-s")
    return [t for t in out.split() if len(t) == 40]
