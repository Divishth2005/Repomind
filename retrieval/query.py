"""Rule-based query interpretation: what is being asked, and about what.

Deliberately simple and transparent -- keyword patterns, no model. It
covers the question types the project targets (plan Sec 24) and falls back
to plain text search for anything else. Module 8 may add LLM-based query
analysis on top; this layer must work without it.
"""
import re
import sqlite3
from dataclasses import dataclass, field

from retrieval import structured as st

INTENT_PATTERNS = [
    ("reviewers", re.compile(r"\bwho\b.*\breview|\breviewers?\b|\breviewed by\b")),
    ("contributors", re.compile(
        r"\bwho\b.*\b(work|maintain|contribut|wrote|write|writes|chang|modif|own|touch|edit|commit|know)\w*"
        r"|\bmain (author|contributor|maintainer)s?\b|\bcontributors?\b|\bmaintainers?\b")),
    ("risk", re.compile(r"\bbus factor\b|\brisk\w*\b|\bconcentrat\w+|\bsingle point\b|\bknowledge\b|\bkey person\b")),
    ("history", re.compile(r"\bhistory\b|\brecent(ly)?\b|\bwhat (has )?changed\b|\bwhat changed\b|\bevolv\w+|\blatest\b")),
    ("why", re.compile(
        r"\bwhy\b|\bwhich (pr|pull request|commit)\b|\b(introduc|caus)\w+|\bwhen was\b|\bwho (introduced|added)\b")),
    ("issues", re.compile(r"\b(related|associated|linked) issues?\b|\bissues?\b.*\b(affect|about|relat|touch)\w*")),
]
CODE_EXT = re.compile(r"\.(py|js|ts|tsx|jsx|go|rs|c|h|cpp|java|rb|php|cs|sh|md|rst|txt|ya?ml|toml|json|cfg|ini|html|css|lock)$", re.IGNORECASE)
PATH_RE = re.compile(r"[\w./\-]*[\w\-]+\.[A-Za-z0-9]{1,5}\b|\b[\w\-]+(?:/[\w.\-]+)+/?")
HASH_RE = re.compile(r"\b[0-9a-f]{7,40}\b")
REF_RE = re.compile(r"(?:#|\b(?:pr|pull request|pull|issue)\s*#?\s*)(\d+)\b", re.IGNORECASE)


@dataclass
class QueryPlan:
    query: str
    intents: list[str]
    scopes: list = field(default_factory=list)
    scope_mentions: list = field(default_factory=list)
    unresolved: list = field(default_factory=list)  # file-like names that match nothing in this repository
    numbers: list = field(default_factory=list)
    commit_shas: list = field(default_factory=list)
    developers: list = field(default_factory=list)
    text: str = ""

    def to_dict(self):
        return {
            "intents": self.intents,
            "scopes": [s.label for s in self.scopes],
            "numbers": self.numbers,
            "commit_shas": self.commit_shas,
            "developers": [d["name"] for d in self.developers],
            "text_query": self.text,
        }


def interpret(conn: sqlite3.Connection, repo: str, query: str, developer_names: list[str] | None = None) -> QueryPlan:
    q = query.strip()
    low = q.lower()

    mentions = [m.strip(".,;:?!)") for m in PATH_RE.findall(q)]
    mentions = [m for m in mentions if not re.fullmatch(r"\d+(\.\d+)*", m) and not m.lower().startswith(("e.g", "i.e"))]
    scopes, seen = [], set()
    used_mentions, unresolved = [], []
    for m in mentions:
        found = st.resolve_scope(conn, repo, m)
        if found:
            used_mentions.append(m)
        elif "/" in m or CODE_EXT.search(m):
            unresolved.append(m)
        for s in found:
            if s.path not in seen:
                seen.add(s.path)
                scopes.append(s)

    numbers = sorted({int(n) for n in REF_RE.findall(q)})
    shas = []
    for h in HASH_RE.findall(low):
        if conn.execute("SELECT 1 FROM commit_ WHERE repository_id=? AND commit_id LIKE ? LIMIT 1", (repo, h + "%")).fetchone():
            shas.append(h)

    devs, matched_names = [], []
    for name in developer_names or []:
        if len(name) >= 4 and re.search(rf"(?<![\w]){re.escape(name.lower())}(?![\w])", low):
            found = st.find_developers(conn, repo, name)
            if found:
                matched_names.append(name)
            devs += found
    uniq = {d["developer_id"]: d for d in devs}
    devs = sorted(uniq.values(), key=lambda d: -(d["commits"] + d["prs"]))[:3]

    intents = [name for name, pat in INTENT_PATTERNS if pat.search(low)]
    if "reviewers" in intents and "contributors" in intents and not re.search(r"work|maintain|wrote|contribut|author|own", low):
        intents.remove("contributors")  # "who reviewed changes to X" is about reviewers, not authors
    if not intents:
        if scopes:
            intents = ["overview"]
        elif numbers or shas:
            intents = ["lookup"]
        elif devs:
            intents = ["developer"]
        else:
            intents = ["search"]
    elif devs and "contributors" in intents and not scopes:
        intents.remove("contributors")
        intents.append("developer")

    text = q
    for m in used_mentions:
        text = text.replace(m, " ")
    for name in matched_names:
        text = re.sub(re.escape(name), " ", text, flags=re.IGNORECASE)
    return QueryPlan(q, intents, scopes, used_mentions, unresolved, numbers, shas, devs, " ".join(text.split()))
