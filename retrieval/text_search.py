"""Lexical text retrieval (BM25) over commit messages, PR and issue text,
and review comments.

This is keyword matching, NOT embedding-based semantic search: it cannot
match a query and a document that share no words. That limitation is
measured in retrieval/evaluate.py (share of misses with zero word overlap)
so the decision to add embeddings is based on evidence, not fashion.
"""
import math
import re
import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field

STOPWORDS = frozenset(
    """a an and are as at be been but by can could did do does for from had has have how i if in into is it its
    of on or our should so than that the their then there these they this to was we were what when where which
    who whom why will with would you your not no also just about over under after before""".split()
)

_CAMEL = re.compile(r"([a-z0-9])([A-Z])")
_ACRONYM = re.compile(r"([A-Z]+)([A-Z][a-z])")
_TOKEN = re.compile(r"[a-z0-9]+")


def stem(word: str) -> str:
    """Very light suffix stripping (plural / -ing / -ed). Deliberately
    conservative; a wrong stem only costs a little recall."""
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 5 and word.endswith("ing"):
        return word[:-3]
    if len(word) > 4 and word.endswith("ed"):
        return word[:-2]
    if len(word) > 4 and word.endswith(("shes", "ches", "xes", "sses", "zes")):
        return word[:-2]
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def tokenize(text: str) -> list[str]:
    text = _CAMEL.sub(r"\1 \2", _ACRONYM.sub(r"\1 \2", text or ""))
    return [stem(t) for t in _TOKEN.findall(text.lower()) if len(t) > 1 and t not in STOPWORDS]


@dataclass
class Document:
    kind: str
    key: str  # unique within its kind
    ref: str
    title: str
    text: str
    date: str | None = None
    author: str | None = None
    meta: dict = field(default_factory=dict)


class BM25Index:
    def __init__(self, docs: list[Document], k1: float = 1.5, b: float = 0.75):
        self.docs = docs
        self.k1, self.b = k1, b
        self.postings: dict[str, list[tuple[int, int]]] = defaultdict(list)
        self.lengths: list[int] = []
        for i, doc in enumerate(docs):
            counts: dict[str, int] = defaultdict(int)
            tokens = tokenize(doc.title + " " + doc.text)
            for t in tokens:
                counts[t] += 1
            self.lengths.append(len(tokens))
            for t, c in counts.items():
                self.postings[t].append((i, c))
        self.n = len(docs)
        self.avg_len = (sum(self.lengths) / self.n) if self.n else 0.0
        self.key_to_idx = {d.key: i for i, d in enumerate(docs)}

    def _idf(self, term: str) -> float:
        df = len(self.postings.get(term, ()))
        return math.log(1 + (self.n - df + 0.5) / (df + 0.5))

    def search(self, query: str, limit: int = 10, allowed: set[str] | None = None) -> list[tuple[Document, float]]:
        scores: dict[int, float] = defaultdict(float)
        for term in set(tokenize(query)):
            idf = self._idf(term)
            for i, tf in self.postings.get(term, ()):
                if allowed is not None and self.docs[i].key not in allowed:
                    continue
                norm = tf + self.k1 * (1 - self.b + self.b * self.lengths[i] / (self.avg_len or 1.0))
                scores[i] += idf * tf * (self.k1 + 1) / norm
        ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))[:limit]
        return [(self.docs[i], s) for i, s in ranked]


def _name(display, login):
    return display or login


def build_documents(conn: sqlite3.Connection, repository_id: str, kind: str, include_body: bool = True) -> list[Document]:
    r = (repository_id,)
    docs: list[Document] = []
    if kind == "commit":
        rows = conn.execute(
            """SELECT c.commit_id, c.subject, c.body, c.timestamp, d.display_name, d.github_login, d.is_bot
               FROM commit_ c JOIN developer d ON d.developer_id = c.author_developer_id
               WHERE c.repository_id = ? AND c.is_merge = 0""", r)
        for row in rows:
            body = (row["body"] or "")[:1500] if include_body else ""
            docs.append(Document("commit", row["commit_id"], f"commit:{row['commit_id'][:7]}", row["subject"] or "",
                                 body, row["timestamp"], _name(row["display_name"], row["github_login"]),
                                 {"sha": row["commit_id"], "is_bot": bool(row["is_bot"])}))
    elif kind in ("pr", "issue"):
        table, col = ("pull_request", "merged_at") if kind == "pr" else ("issue", "closed_at")
        rows = conn.execute(
            f"""SELECT t.github_number, t.title, t.body, t.state, t.created_at, t.{col} AS done_at,
                       d.display_name, d.github_login
                FROM {table} t LEFT JOIN developer d ON d.developer_id = t.author_developer_id
                WHERE t.repository_id = ?""", r)
        for row in rows:
            body = (row["body"] or "")[:3000] if include_body else ""
            docs.append(Document(kind, str(row["github_number"]), f"{kind}:#{row['github_number']}", row["title"] or "",
                                 body, row["created_at"], _name(row["display_name"], row["github_login"]),
                                 {"number": row["github_number"], "state": row["state"], "done_at": row["done_at"]}))
    elif kind == "review":
        rows = conn.execute(
            """SELECT rv.review_id, rv.body, rv.state, rv.submitted_at, p.github_number, p.title AS pr_title,
                      d.display_name, d.github_login
               FROM review rv JOIN pull_request p ON p.pr_id = rv.pr_id
               LEFT JOIN developer d ON d.developer_id = rv.reviewer_developer_id
               WHERE p.repository_id = ? AND length(COALESCE(rv.body, '')) >= 20""", r)
        for row in rows:
            docs.append(Document("review", row["review_id"], f"review:{row['review_id'][:8]}", f"review on PR #{row['github_number']}",
                                 (row["body"] or "")[:1500], row["submitted_at"], _name(row["display_name"], row["github_login"]),
                                 {"pr_number": row["github_number"], "pr_title": row["pr_title"], "state": row["state"]}))
    else:
        raise ValueError(f"unknown kind: {kind}")
    return docs
