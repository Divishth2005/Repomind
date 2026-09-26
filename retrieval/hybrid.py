"""The retriever: interpret a question, run the structured queries it needs,
run text search (scoped to the file/directory when one is named), and fuse
the ranked text evidence.

Returns structured answers and ranked evidence separately so a later stage
(Module 8) can build an LLM context from exactly what was retrieved, and so
every item can be cited by its `ref`.
"""
import re
import sqlite3

from analysis.bus_factor import assess_component
from analysis.data import load_activity
from analysis.features import build_features
from analysis.knowledge_score import component_metrics
from retrieval import structured as st
from retrieval.evidence import Evidence
from retrieval.query import QueryPlan, interpret
from retrieval.ranking import rrf
from retrieval.text_search import BM25Index, build_documents, tokenize

KINDS = ("commit", "pr", "issue", "review")
GENERIC_WORDS = set(tokenize(
    "who what changed change changes history recent recently file files component directory worked work "
    "reviewed review reviewers maintain contributor contributors author main most code "
    "pull request pr issue issues commit commits number about"))


def _snippet(text: str, n=220) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= n else text[: n - 1] + "…"


class Retriever:
    def __init__(self, conn: sqlite3.Connection, repository_id: str):
        self.conn, self.repo = conn, repository_id
        self._indexes: dict[str, BM25Index] = {}
        self._activity = None
        self._dev_names = None

    def index(self, kind: str) -> BM25Index:
        if kind not in self._indexes:
            self._indexes[kind] = BM25Index(build_documents(self.conn, self.repo, kind))
        return self._indexes[kind]

    def developer_names(self) -> list[str]:
        if self._dev_names is None:
            rows = self.conn.execute(
                """SELECT DISTINCT n FROM (
                     SELECT d.display_name n FROM developer d JOIN commit_ c ON c.author_developer_id=d.developer_id
                       WHERE c.repository_id=? AND d.is_bot=0
                     UNION SELECT d.github_login FROM developer d JOIN pull_request p ON p.author_developer_id=d.developer_id
                       WHERE p.repository_id=? AND d.is_bot=0) WHERE n IS NOT NULL""",
                (self.repo, self.repo)).fetchall()
            self._dev_names = [r[0] for r in rows]
        return self._dev_names

    def search_text(self, query, kinds=("commit", "pr", "issue"), limit=10, allowed: dict | None = None) -> list[Evidence]:
        """BM25 per kind, fused by rank (scores from different corpora aren't comparable)."""
        per_kind, docs, scores = [], {}, {}
        for kind in kinds:
            keys = allowed.get(kind) if allowed is not None else None
            if allowed is not None and not keys:
                continue
            hits = self.index(kind).search(query, limit=limit * 2, allowed=keys)
            per_kind.append([d.ref for d, _ in hits])
            for d, s in hits:
                docs[d.ref], scores[d.ref] = d, s
        fused = rrf(per_kind)[:limit]
        return [self._to_evidence(docs[ref], scores[ref], rank_score) for ref, rank_score in fused]

    @staticmethod
    def _to_evidence(doc, bm25, fused) -> Evidence:
        return Evidence(doc.kind, doc.ref, doc.title, _snippet(doc.text), doc.date, doc.author, round(fused, 5),
                        "text", dict(doc.meta, bm25=round(bm25, 3)))

    def assess(self, scope: st.Scope) -> dict:
        """Module 4/5 numbers for an arbitrary file or directory, computed on demand."""
        if self._activity is None:
            self._activity = load_activity(self.conn, self.repo)
        match = (lambda p: p == scope.path) if scope.kind == "file" else (lambda p: p.startswith(scope.path))
        rows = {}
        for key, items in self._activity.items():
            path_idx = 3 if key == "commits" else 2
            rows[key] = [tuple(scope.path if i == path_idx else v for i, v in enumerate(r)) for r in items if match(r[path_idx])]
        features, _ = build_features(rows, depth=None)
        devs = features.get(scope.path)
        if not devs:
            return {"scope": scope.label, "available": False}
        names = {r[0]: r[1] for r in self.conn.execute(
            "SELECT developer_id, COALESCE(display_name, github_login) FROM developer")}
        m = component_metrics(scope.path, devs)
        risk = assess_component(scope.path, devs)
        top = m["developers"][0]
        return {
            "scope": scope.label, "available": True, "total_commits": m["total_commits"],
            "contributors": m["n_contributors"], "top_contributor": names.get(top["developer_id"]),
            "top_commit_share": round(m["metrics"]["top_commit_share"], 3),
            "effective_contributors": round(m["metrics"]["effective_contributors_commits"], 2),
            "risk_level": risk["level"],
            "risk_signals": [s for s in risk["signals"] if s["triggered"]],
            "risk_evidence": risk["evidence"] and {k: (round(v, 3) if isinstance(v, float) else v)
                                                   for k, v in risk["evidence"].items() if k != "top_active_developer"},
            "note": "risk fields are heuristic signals from Module 5, not a finding about any individual",
        }

    def retrieve(self, query: str, limit: int = 8) -> dict:
        plan: QueryPlan = interpret(self.conn, self.repo, query, self.developer_names())
        answers: dict = {}
        notes: list[str] = []
        intents = set(plan.intents)
        coverage = st.pr_link_coverage(self.conn, self.repo)
        if coverage["pull_requests"] and coverage["linked_via_commits"] / coverage["pull_requests"] < 0.2:
            notes.append(
                f"Only {coverage['linked_via_commits']} of {coverage['pull_requests']} PRs link to commits in history "
                "(likely squash merges); PRs are recovered from '(#N)' in commit subjects where possible.")
        if len(plan.scopes) > 1:
            notes.append("Several files match the name given; results are listed for each: "
                         + ", ".join(s.label for s in plan.scopes))

        for scope in plan.scopes:
            block = {}
            if intents & {"contributors", "overview", "why"}:
                block["contributors"] = st.contributors(self.conn, self.repo, scope)
            if intents & {"reviewers", "overview"}:
                block["reviewers"] = st.reviewers(self.conn, self.repo, scope)
            if intents & {"history", "overview", "why"}:
                block["history"] = st.history(self.conn, self.repo, scope)
            if intents & {"why", "issues", "overview"}:
                block["prs"] = st.prs_touching(self.conn, self.repo, scope)
            if "risk" in intents or "overview" in intents:
                block["assessment"] = self.assess(scope)
            answers[scope.label] = block

        if any("reviewers" in b and "contributors" in b for b in answers.values()) or any(
                "reviewers" in b for b in answers.values()):
            notes.append("Reviewers are GitHub logins while commit authors are Git names; the same person can "
                         "appear under both (the two are not always linked).")
        lookups = []
        for n in plan.numbers:
            pr, issue = st.pr_context(self.conn, self.repo, n), st.issue_context(self.conn, self.repo, n)
            if pr:
                lookups.append({"type": "pr", **pr})
            if issue:
                lookups.append({"type": "issue", **issue})
            if not pr and not issue:
                notes.append(f"#{n} was not found as a PR or issue in this repository.")
        for sha in plan.commit_shas:
            c = st.commit_context(self.conn, self.repo, sha)
            if c:
                lookups.append({"type": "commit", **c})
        if lookups:
            answers["lookups"] = lookups

        if plan.developers:
            answers["developers"] = [{**d, **st.developer_activity(self.conn, self.repo, d["developer_id"])} for d in plan.developers]
            if len(plan.developers) > 1 or any(d["commits"] == 0 or d["prs"] == 0 for d in plan.developers):
                notes.append("A person can appear under more than one identity (e.g. a Git name and a GitHub login "
                             "are not always linked), so activity totals may be split.")

        evidence = self._text_evidence(plan, limit)
        return {"query": query, "plan": plan.to_dict(), "answers": answers,
                "evidence": [e.to_dict() for e in evidence], "notes": notes}

    def _text_evidence(self, plan: QueryPlan, limit: int) -> list[Evidence]:
        words = [t for t in tokenize(plan.text)
                 if t not in GENERIC_WORDS and not (t.isdigit() and int(t) in plan.numbers)]
        if not words and not plan.scopes:
            return []
        query_text = " ".join(words) if words else ""
        results: list[Evidence] = []
        if plan.scopes:
            allowed = {"commit": set(), "pr": set(), "issue": set()}
            for scope in plan.scopes:
                allowed["commit"] |= set(st.scope_commit_ids(self.conn, self.repo, scope))
                prs = st.scope_pr_numbers(self.conn, self.repo, scope)
                allowed["pr"] |= {str(n) for n in prs}
                for r in self.conn.execute(
                        f"SELECT DISTINCT pi.issue_number FROM pr_issue pi JOIN pull_request p ON p.pr_id=pi.pr_id "
                        f"WHERE p.repository_id=? AND p.github_number IN ({','.join('?' * len(prs)) or 'NULL'})",
                        (self.repo, *prs)):
                    allowed["issue"].add(str(r[0]))
            if query_text:
                results = self.search_text(query_text, limit=limit, allowed=allowed)
            elif set(plan.intents) & {"history", "overview", "why"}:
                for scope in plan.scopes[:1]:
                    for h in st.history(self.conn, self.repo, scope, limit=limit):
                        results.append(Evidence("commit", f"commit:{h['sha'][:7]}", h["subject"] or "", "", h["date"],
                                                h["author"], 0.0, "structured", {"sha": h["sha"], "order": "most recent"}))
            return results[:limit]
        return self.search_text(query_text, limit=limit)
