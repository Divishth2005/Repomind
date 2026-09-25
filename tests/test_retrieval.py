import pytest

from database.connection import get_connection, init_schema
from retrieval import structured as st
from retrieval.evaluate import evaluate, issue_pr_pairs
from retrieval.hybrid import Retriever
from retrieval.query import interpret
from retrieval.ranking import rrf
from retrieval.text_search import BM25Index, Document, build_documents, stem, tokenize

REPO = "o/r"


def make_db():
    conn = get_connection(":memory:")
    init_schema(conn)
    conn.execute("INSERT INTO repository VALUES (?, 'o', 'r', 'u', NULL, NULL)", (REPO,))
    devs = [("alice", "alice", "Alice Smith", 0), ("bob", "bob", "Bob Jones", 0),
            ("carol", "carol", "Carol", 0), ("robot", "robot[bot]", "robot[bot]", 1)]
    for i, login, name, bot in devs:
        conn.execute("INSERT INTO developer VALUES (?, ?, ?, NULL, ?, 'high', '[]')", (i, login, name, bot))
    for fid, path in (("f1", "src/a.py"), ("f2", "src/b.py"), ("f3", "docs/x.md")):
        conn.execute("INSERT INTO file VALUES (?, ?, ?)", (fid, REPO, path))
    commits = [
        ("c1", "alice", "2022-01-01T00:00:00+00:00", "add parser for config files", "", ["f1"]),
        ("c2", "alice", "2023-01-01T00:00:00+00:00", "fix crash when parsing empty config", "Handles empty input.", ["f1", "f2"]),
        ("c3", "bob", "2024-01-01T00:00:00+00:00", "speed up lookup (#2)", "", ["f1"]),
        ("c4", "robot", "2024-06-01T00:00:00+00:00", "bump dependencies", "", ["f2"]),
        ("c5", "alice", "2024-02-01T00:00:00+00:00", "update docs", "", ["f3"]),
    ]
    for cid, author, ts, subject, body, files in commits:
        conn.execute("INSERT INTO commit_ VALUES (?, ?, ?, ?, ?, ?, ?, '[]', 0, ?)", (cid, REPO, author, author, ts, subject, body, cid))
        for f in files:
            conn.execute("INSERT INTO commit_file VALUES (?, ?, ?, 1, 1)", (f"{cid}{f}", cid, f))
    conn.execute("INSERT INTO issue VALUES ('i7', ?, 7, 'Crash when parsing empty config file', 'It crashes.', 'CLOSED', 'carol', '2022-12-01', '2023-01-02', '[]', 'x')", (REPO,))
    conn.execute("INSERT INTO issue VALUES ('i8', ?, 8, 'Add dark mode', 'Please.', 'OPEN', 'carol', '2024-03-01', NULL, '[]', 'x')", (REPO,))
    conn.execute("INSERT INTO pull_request VALUES ('p1', ?, 1, 'Fix empty config crash', 'Fixes #7', 'MERGED', 'bob', '2022-12-20', '2023-01-01', '[]', '[\"c2\"]', '[7]', 'x')", (REPO,))
    conn.execute("INSERT INTO pull_request VALUES ('p2', ?, 2, 'Speed up lookup', 'perf', 'MERGED', 'alice', '2023-12-20', '2024-01-01', '[]', '[]', '[]', 'x')", (REPO,))
    conn.execute("INSERT INTO pr_commit VALUES ('p1', 'c2')")
    conn.execute("INSERT INTO pr_issue VALUES ('p1', 7)")
    reviews = [("r1", "p1", "carol", "APPROVED", "Looks good, thanks for fixing the empty config crash"),
               ("r2", "p1", "alice", "COMMENTED", "small nit"), ("r3", "p1", "bob", "COMMENTED", "replying to myself"),
               ("r4", "p2", "carol", "APPROVED", "ok")]
    for rid, pr, who, state, body in reviews:
        conn.execute("INSERT INTO review VALUES (?, ?, ?, ?, '2023-01-01', ?)", (rid, pr, who, state, body))
    conn.commit()
    return conn


@pytest.fixture
def conn():
    return make_db()


def test_tokenizer_and_stemmer():
    assert tokenize("Fixed the URLBuilder crashes") == ["fix", "url", "builder", "crash"]
    assert stem("crashes") == "crash" and stem("class") == "class" and stem("bugs") == "bug"
    assert tokenize("the of and") == []


def test_bm25_ranks_relevant_first_and_respects_allowed():
    docs = [Document("pr", "1", "pr:#1", "fix empty config crash", ""),
            Document("pr", "2", "pr:#2", "add dark mode", ""),
            Document("pr", "3", "pr:#3", "config docs", "")]
    idx = BM25Index(docs)
    assert idx.search("crash on empty config")[0][0].key == "1"
    assert [d.key for d, _ in idx.search("config", allowed={"3"})] == ["3"]
    assert idx.search("nothing matches zzz") == []


def test_rrf_orders_by_combined_rank_and_weight():
    assert rrf([["a", "b"], ["b", "a"]], weights=[1.0, 2.0])[0][0] == "b"
    assert rrf([["a", "b"], ["a", "c"]])[0][0] == "a"


def test_resolve_scope(conn):
    assert st.resolve_scope(conn, REPO, "a.py") == [st.Scope("file", "src/a.py")]
    assert st.resolve_scope(conn, REPO, "src") == [st.Scope("dir", "src/")]
    assert st.resolve_scope(conn, REPO, "missing.py") == []


def test_contributors_exclude_bots_by_default(conn):
    scope = st.Scope("file", "src/b.py")
    names = [c["name"] for c in st.contributors(conn, REPO, scope)["contributors"]]
    assert names == ["Alice Smith"]
    assert "robot[bot]" in [c["name"] for c in st.contributors(conn, REPO, scope, include_bots=True)["contributors"]]


def test_history_order_and_pr_links(conn):
    h = st.history(conn, REPO, st.Scope("file", "src/a.py"))
    assert [x["sha"] for x in h] == ["c3", "c2", "c1"]
    assert h[0]["pr_from_subject"] == 2 and h[0]["prs_linked"] == []
    assert h[1]["prs_linked"] == [1]


def test_prs_and_reviewers_use_linked_and_subject_prs(conn):
    scope = st.Scope("file", "src/a.py")
    prs = {p["number"]: p["link"] for p in st.prs_touching(conn, REPO, scope)}
    assert prs == {1: "linked", 2: "subject"}
    rev = {r["name"]: r["prs_reviewed"] for r in st.reviewers(conn, REPO, scope)}
    assert rev == {"Carol": 2, "Alice Smith": 1}  # bob's review of his own PR is excluded


def test_pr_issue_commit_contexts(conn):
    pr = st.pr_context(conn, REPO, 1)
    assert [i["number"] for i in pr["closes_issues"]] == [7]
    assert len(pr["reviews"]) == 3 and "src/a.py" in pr["files"]
    assert st.pr_context(conn, REPO, 999) is None
    assert st.pr_context(conn, REPO, 2)["commits_from_subject"][0]["sha"] == "c3"
    assert [p["number"] for p in st.issue_context(conn, REPO, 7)["closed_by_prs"]] == [1]
    c = st.commit_context(conn, REPO, "c2")
    assert c["prs_linked"] == [1] and {f["path"] for f in c["files"]} == {"src/a.py", "src/b.py"}


def test_find_developers_and_link_coverage(conn):
    assert st.find_developers(conn, REPO, "alice smith")[0]["developer_id"] == "alice"
    assert st.find_developers(conn, REPO, "nobody") == []
    cov = st.pr_link_coverage(conn, REPO)
    assert cov == {"pull_requests": 2, "linked_via_commits": 1, "commits_with_pr_number_in_subject": 1}


def test_interpret_intents_scopes_and_refs(conn):
    q = lambda text, names=None: interpret(conn, REPO, text, names)
    p = q("Who reviewed changes to a.py?")
    assert p.intents == ["reviewers"] and [s.path for s in p.scopes] == ["src/a.py"]
    assert q("who works on src/").intents == ["contributors"]
    assert q("what is #7").numbers == [7] and q("what is #7").intents == ["lookup"]
    assert "why" in q("why was the config crash fixed?").intents
    assert q("bus factor of src/a.py").intents == ["risk"]
    p = q("what did Alice Smith work on?", ["Alice Smith"])
    assert p.intents == ["developer"] and p.developers[0]["developer_id"] == "alice"
    assert "alice" not in p.text.lower()  # a matched name is not reused as a search term
    assert q("dark mode").intents == ["search"]
    assert q("commit c2 details").commit_shas == []  # too short to be a hash


def test_retrieve_end_to_end(conn):
    r = Retriever(conn, REPO)
    out = r.retrieve("Who reviewed changes to src/a.py?")
    assert {x["name"] for x in out["answers"]["src/a.py"]["reviewers"]} == {"Carol", "Alice Smith"}
    out = r.retrieve("what is #1")
    assert out["answers"]["lookups"][0]["type"] == "pr"
    out = r.retrieve("empty config crash")
    assert out["evidence"][0]["ref"] in ("issue:#7", "pr:#1", "commit:c2")
    assert r.retrieve("what is #500")["notes"]


def test_scoped_text_search_only_returns_items_touching_scope(conn):
    out = Retriever(conn, REPO).retrieve("why was the crash in src/b.py fixed?")
    refs = {e["ref"] for e in out["evidence"]}
    assert "commit:c2" in refs and "pr:#2" not in refs


def test_assess_returns_signals(conn):
    a = Retriever(conn, REPO).assess(st.Scope("file", "src/a.py"))
    assert a["available"] and a["total_commits"] == 3 and a["risk_level"] in ("high", "medium", "low", "dormant", "insufficient_evidence")
    assert not Retriever(conn, REPO).assess(st.Scope("file", "nope.py"))["available"]


def test_documents_skip_merge_commits_and_short_reviews(conn):
    conn.execute("UPDATE commit_ SET is_merge = 1 WHERE commit_id = 'c5'")
    assert "c5" not in {d.key for d in build_documents(conn, REPO, "commit")}
    assert {d.key for d in build_documents(conn, REPO, "review")} == {"r1"}  # only reviews with >= 20 characters are indexed


def test_evaluation_pairs_and_minimum_size(conn):
    assert issue_pr_pairs(conn, REPO) == [{"issue": 7, "title": "Crash when parsing empty config file", "relevant": {"1"}}]
    assert evaluate(conn, REPO) is None  # too few pairs to report numbers
