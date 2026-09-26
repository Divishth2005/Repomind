"""Everything the UI needs, as plain functions returning JSON-ready dicts.

No web code here. A `Workspace` owns one database connection (guarded by a
lock, so the web server can be threaded) and caches the expensive things
(text-search indexes, activity data, co-change model) per repository.
AI-backed features never raise into the UI: they return {"ok": False,
"error": ...} so the evidence can still be shown.
"""
import re
import sqlite3
import threading
from pathlib import Path

from analysis.bus_factor import LEVEL_ORDER, assess_component
from analysis.data import load_activity
from analysis.features import build_features
from assist import answer as assist_answer
from assist.cochange import CoChange, load_commits
from database import queries as q
from database.connection import get_connection
from explain import answer as explain_answer
from explain.source import SourceError, python_symbols, read_file
from llm.answer import answer_question
from llm.client import LLMError
from llm.context_builder import build_context
from retrieval import structured as st
from retrieval.hybrid import Retriever
from visualization.knowledge_map import build_graph

REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
REF_RE = re.compile(r"^(commit|pr|issue):#?([0-9A-Za-z]+)$")


class ServiceError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def _in_range(name, value, lo, hi):
    try:
        v = int(value)
    except (TypeError, ValueError):
        raise ServiceError(f"{name} must be a number")
    if not lo <= v <= hi:
        raise ServiceError(f"{name} must be between {lo} and {hi}")
    return v


def parse_lines(text):
    if not text:
        return None
    m = re.fullmatch(r"\s*(\d+)\s*-\s*(\d+)\s*", str(text))
    if not m:
        raise ServiceError("Line range must look like 100-160")
    return int(m.group(1)), int(m.group(2))


class Workspace:
    def __init__(self, db_path, client_factory):
        self.db_path = str(db_path)
        self.client_factory = client_factory
        self.lock = threading.RLock()
        self.conn = get_connection(self.db_path)
        self.conn.close()
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self._retrievers, self._activity, self._features, self._cochange = {}, {}, {}, {}

    # ---- caches -----------------------------------------------------------
    def invalidate(self):
        self._retrievers.clear(); self._activity.clear(); self._features.clear(); self._cochange.clear()

    def require(self, repo: str):
        if not self.conn.execute("SELECT 1 FROM repository WHERE repository_id = ?", (repo,)).fetchone():
            raise ServiceError(f"'{repo}' is not loaded. Add it from the top bar or run: python pipeline.py --repo {repo}", 404)

    def retriever(self, repo) -> Retriever:
        if repo not in self._retrievers:
            self._retrievers[repo] = Retriever(self.conn, repo)
        return self._retrievers[repo]

    def features(self, repo, depth, active_days):
        key = (repo, depth, active_days)
        if key not in self._features:
            if repo not in self._activity:
                self._activity[repo] = load_activity(self.conn, repo)
            self._features[key] = build_features(self._activity[repo], depth, recent_days=active_days)
        return self._features[key]

    def _names(self, ids):
        out = {}
        for chunk in st._chunks(list({i for i in ids if i})):
            marks = ",".join("?" * len(chunk))
            for r in self.conn.execute(f"SELECT developer_id, COALESCE(display_name, github_login) AS n FROM developer WHERE developer_id IN ({marks})", chunk):
                out[r["developer_id"]] = r["n"]
        return out

    def _llm(self, fn):
        try:
            return {"ok": True, **fn(self.client_factory())}
        except LLMError as e:
            return {"ok": False, "error": str(e)}

    # ---- repositories -----------------------------------------------------
    def repos(self):
        with self.lock:
            return [dict(r) for r in self.conn.execute(
                """SELECT r.repository_id AS repo, (SELECT COUNT(*) FROM commit_ c WHERE c.repository_id = r.repository_id) AS commits
                   FROM repository r ORDER BY commits DESC""")]

    def overview(self, repo):
        with self.lock:
            self.require(repo)
            one = lambda sql: self.conn.execute(sql, (repo,)).fetchone()[0]
            span = self.conn.execute("SELECT MIN(timestamp), MAX(timestamp) FROM commit_ WHERE repository_id=?", (repo,)).fetchone()
            bots = self.conn.execute(
                "SELECT COUNT(DISTINCT c.author_developer_id) FROM commit_ c JOIN developer d ON d.developer_id=c.author_developer_id "
                "WHERE c.repository_id=? AND d.is_bot=1", (repo,)).fetchone()[0]
            humans = self.conn.execute(
                "SELECT COUNT(DISTINCT c.author_developer_id) FROM commit_ c JOIN developer d ON d.developer_id=c.author_developer_id "
                "WHERE c.repository_id=? AND d.is_bot=0", (repo,)).fetchone()[0]
            features, reference = self.features(repo, 2, 365)
            ranked = [f for f in features.values() if sum(d["commit_count"] for d in f.values()) >= 5]
            single = sum(1 for f in ranked if max(d["commit_count"] for d in f.values()) / sum(d["commit_count"] for d in f.values()) >= 0.8)
            levels = {}
            for c, devs in features.items():
                lv = assess_component(c, devs)["level"]
                levels[lv] = levels.get(lv, 0) + 1
            return {
                "repo": repo,
                "counts": {
                    "commits": one("SELECT COUNT(*) FROM commit_ WHERE repository_id=?"),
                    "files": one("SELECT COUNT(*) FROM file WHERE repository_id=?"),
                    "human_committers": humans, "bot_identities": bots,
                    "pull_requests": one("SELECT COUNT(*) FROM pull_request WHERE repository_id=?"),
                    "issues": one("SELECT COUNT(*) FROM issue WHERE repository_id=?"),
                    "reviews": one("SELECT COUNT(*) FROM review rv JOIN pull_request p ON p.pr_id=rv.pr_id WHERE p.repository_id=?"),
                },
                "first_commit": span[0], "last_commit": span[1],
                "commits_per_year": [dict(r) for r in self.conn.execute(
                    "SELECT substr(timestamp,1,4) AS year, COUNT(*) AS commits FROM commit_ WHERE repository_id=? GROUP BY year ORDER BY year", (repo,))],
                "top_contributors": [{"name": r["display_name"] or r["github_login"], "commits": r["commit_count"]}
                                     for r in q.top_contributors(self.conn, repo, limit=10)],
                "concentration": {"components_ranked": len(ranked), "components_with_one_author_at_80pct": single,
                                  "risk_levels": levels, "as_of": reference.isoformat() if reference else None},
            }

    # ---- risk / map -------------------------------------------------------
    def risk(self, repo, depth=2, active_days=365, limit=60):
        depth = _in_range("Component depth", depth, 1, 3)
        active_days = _in_range("Active window (days)", active_days, 30, 1825)
        with self.lock:
            self.require(repo)
            features, reference = self.features(repo, depth, active_days)
            assessed = sorted((assess_component(c, d) for c, d in features.items()),
                              key=lambda r: (LEVEL_ORDER[r["level"]], -r["recent_commits"]))
            names = self._names([r["evidence"].get("top_active_developer") for r in assessed if r["evidence"]])
            rows = []
            for r in assessed[:limit]:
                e = r["evidence"]
                rows.append({
                    "component": r["component"], "level": r["level"], "total_commits": r["total_commits"],
                    "recent_commits": r["recent_commits"],
                    "active_developers": e.get("active_developers"), "total_developers": e.get("total_developers"),
                    "bus_factor_active": e.get("bus_factor_active"),
                    "top_active_developer": names.get(e.get("top_active_developer")), "top_active_share": e.get("top_active_share"),
                    "departed_share": e.get("departed_share"),
                    "signals": [s["detail"] for s in r["signals"] if s["triggered"]],
                    "not_evaluated": r["not_evaluated"],
                })
            counts = {}
            for r in assessed:
                counts[r["level"]] = counts.get(r["level"], 0) + 1
            return {"repo": repo, "as_of": reference.isoformat() if reference else None, "active_days": active_days, "depth": depth,
                    "level_counts": counts, "components": rows, "components_total": len(assessed),
                    "note": "'high' means the available repository evidence shows several risk signals. It does not establish that any "
                            "individual is the only person who understands the component. Thresholds are unvalidated."}

    def graph(self, repo, top=15, files=6):
        top, files = _in_range("Developers shown", top, 3, 40), _in_range("Files per developer", files, 2, 12)
        with self.lock:
            self.require(repo)
            return build_graph(self.conn, repo, top, files)

    # ---- browsing ---------------------------------------------------------
    def files(self, repo, text, limit=15):
        with self.lock:
            self.require(repo)
            like = "%" + (text or "").replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            return [dict(r) for r in self.conn.execute(
                """SELECT f.path, COUNT(DISTINCT cf.commit_id) AS commits FROM file f JOIN commit_file cf ON cf.file_id=f.file_id
                   WHERE f.repository_id=? AND f.path LIKE ? ESCAPE '\\' GROUP BY f.file_id ORDER BY commits DESC LIMIT ?""",
                (repo, like, limit))]

    def symbols(self, repo, path):
        with self.lock:
            self.require(repo)
            if not path or not path.endswith(".py"):
                return {"symbols": [], "note": "Function names are listed for Python files only; use a line range for other languages."}
            try:
                syms = python_symbols(read_file(repo, path))
            except SourceError as e:
                return {"symbols": [], "note": str(e)}
            return {"symbols": [{"name": s.name, "kind": s.kind, "start": s.start, "end": s.end} for s in syms[:400]], "note": None}

    def search(self, repo, text, limit=15):
        if not (text or "").strip():
            raise ServiceError("Type something to search for")
        with self.lock:
            self.require(repo)
            hits = self.retriever(repo).search_text(text, kinds=("commit", "pr", "issue", "review"), limit=limit)
            return {"query": text, "results": [{k: e[k] for k in ("kind", "ref", "title", "snippet", "date", "author")}
                                               for e in (h.to_dict() for h in hits)]}

    def item(self, repo, ref):
        m = REF_RE.match(ref or "")
        if not m:
            raise ServiceError("Only commit, PR and issue references can be opened")
        kind, ident = m.groups()
        with self.lock:
            self.require(repo)
            if kind == "commit":
                found = st.commit_context(self.conn, repo, ident)
            elif not ident.isdigit():
                raise ServiceError("PR and issue references need a number")
            else:
                found = (st.pr_context if kind == "pr" else st.issue_context)(self.conn, repo, int(ident))
            if not found:
                raise ServiceError(f"{ref} was not found in {repo}", 404)
            return {"type": kind, **found}

    def file_summary(self, repo, path):
        with self.lock:
            self.require(repo)
            found = self.conn.execute("SELECT 1 FROM file WHERE repository_id=? AND path=?", (repo, path)).fetchone()
            if not found:
                raise ServiceError(f"'{path}' is not a file in {repo}", 404)
            scope = st.Scope("file", path)
            return {"path": path, "contributors": st.contributors(self.conn, repo, scope, limit=8),
                    "reviewers": st.reviewers(self.conn, repo, scope, limit=8),
                    "history": st.history(self.conn, repo, scope, limit=10), "prs": st.prs_touching(self.conn, repo, scope, limit=8)}

    # ---- questions and code -----------------------------------------------
    def ask(self, repo, question, use_llm):
        if not (question or "").strip():
            raise ServiceError("Type a question")
        with self.lock:
            self.require(repo)
            retriever = self.retriever(repo)
            retrieval = retriever.retrieve(question)
            ctx = build_context(retrieval, repo)
            out = {"question": question, "plan": retrieval["plan"], "notes": retrieval["notes"], "empty": ctx.empty,
                   "evidence_text": "" if ctx.empty else ctx.text, "refs": sorted(ctx.refs), "llm": None}
            if use_llm:
                out["llm"] = self._llm(lambda client: answer_question(self.conn, repo, question, client, retriever))
            return out

    def code(self, repo, mode, path, function, lines, text, use_llm):
        if mode not in ("explain", "brief"):
            raise ServiceError("mode must be explain or brief")
        if not path:
            raise ServiceError("Choose a file")
        function = (function or "").strip() or None
        rng = parse_lines(lines)
        with self.lock:
            self.require(repo)
            retriever = self.retriever(repo)
            try:
                if mode == "explain":
                    prep = explain_answer.prepare(self.conn, repo, path, function, rng, retriever=retriever)
                    ctx, label, span = prep["context"], prep["label"], [prep["start"], prep["end"]]
                    call = lambda c: explain_answer.explain(self.conn, repo, path, c, function, rng, text or None, retriever=retriever)
                else:
                    if repo not in self._cochange:
                        self._cochange[repo] = CoChange(load_commits(self.conn, repo))
                    kw = {"retriever": retriever, "cochange_model": self._cochange[repo]}
                    prep = assist_answer.prepare(self.conn, repo, path, function, rng, text or None, **kw)
                    b = prep["briefing"]
                    ctx, label, span = prep["context"], b["label"], [b["start"], b["end"]]
                    call = lambda c: assist_answer.brief(self.conn, repo, path, c, function, rng, text or None, **kw)
                out = {"mode": mode, "target": label, "lines": span, "evidence_text": ctx.text, "refs": sorted(ctx.refs), "llm": None}
                if use_llm:
                    out["llm"] = self._llm(call)
                return out
            except SourceError as e:
                raise ServiceError(str(e))
