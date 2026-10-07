import sqlite3
import time

import pytest

from llm.client import FakeClient, LLMError
from tests.test_explain import REPO, world  # noqa: F401  (pytest fixture)
from tests.test_retrieval import make_db
from ui.app import create_app
from ui.jobs import JobError, JobManager
from ui.services import ServiceError, parse_lines


def to_file(conn, path):
    dst = sqlite3.connect(path)
    conn.backup(dst)
    dst.close()
    return str(path)


@pytest.fixture
def client(tmp_path):
    db = to_file(make_db(), tmp_path / "ui.sqlite")
    app = create_app(db, client_factory=lambda: FakeClient(lambda s, u: "Carol reviewed it [fact:1] and [pr:#77]."))
    return app.test_client()


def test_index_page_and_static_files(client):
    page = client.get("/")
    assert page.status_code == 200 and b"RepoMind" in page.data and b"/static/app.js" in page.data
    assert client.get("/static/app.js").status_code == 200 and client.get("/static/style.css").status_code == 200
    assert client.get("/static/../services.py").status_code in (404, 400)  # no path traversal out of static/


def test_repos_and_overview(client):
    assert client.get("/api/repos").get_json() == [{"repo": REPO, "commits": 5}]
    o = client.get(f"/api/repo/{REPO}/overview").get_json()
    assert o["counts"]["commits"] == 5 and o["counts"]["pull_requests"] == 2 and o["counts"]["bot_identities"] == 1
    assert o["top_contributors"][0]["name"] == "Alice Smith"
    r = client.get("/api/repo/no/such/overview")
    assert r.status_code == 404 and "not loaded" in r.get_json()["error"]


def test_risk_and_map_validate_their_inputs(client):
    r = client.get(f"/api/repo/{REPO}/risk?depth=1&active_days=365").get_json()
    assert "does not establish" in r["note"] and r["components"]
    bad = client.get(f"/api/repo/{REPO}/risk?depth=9")
    assert bad.status_code == 400 and "Component depth" in bad.get_json()["error"]
    assert r["components_total"] >= len(r["components"])
    assert client.get(f"/api/repo/{REPO}/risk?active_days=abc").status_code == 400
    g = client.get(f"/api/repo/{REPO}/map?top=5&files=3").get_json()
    assert {n["group"] for n in g["nodes"]} == {"developer", "file"}
    assert client.get(f"/api/repo/{REPO}/map?top=500").status_code == 400


def test_search_items_and_file_summary(client):
    hits = client.get(f"/api/repo/{REPO}/search?q=empty config crash").get_json()["results"]
    assert hits and hits[0]["ref"] in ("issue:#7", "pr:#1", "commit:c2")
    assert client.get(f"/api/repo/{REPO}/search?q=").status_code == 400
    assert client.get(f"/api/repo/{REPO}/item?ref=pr:%231").get_json()["title"] == "Fix empty config crash"
    assert client.get(f"/api/repo/{REPO}/item?ref=issue:%237").get_json()["closed_by_prs"][0]["number"] == 1
    assert client.get(f"/api/repo/{REPO}/item?ref=commit:c2").get_json()["type"] == "commit"
    assert client.get(f"/api/repo/{REPO}/item?ref=pr:%23999").status_code == 404
    assert client.get(f"/api/repo/{REPO}/item?ref=fact:1").status_code == 400
    assert client.get(f"/api/repo/{REPO}/file?path=src/a.py").get_json()["contributors"]["total_commits"] == 3
    assert client.get(f"/api/repo/{REPO}/file?path=nope.py").status_code == 404
    assert [f["path"] for f in client.get(f"/api/repo/{REPO}/files?q=a.py").get_json()][:1] == ["src/a.py"]


def test_ask_returns_evidence_and_only_calls_the_ai_when_asked(client):
    q = "Who reviewed changes to src/a.py?"
    plain = client.post(f"/api/repo/{REPO}/ask", json={"question": q, "use_llm": False}).get_json()
    assert plain["llm"] is None and "Carol" in plain["evidence_text"] and not plain["empty"]
    ai = client.post(f"/api/repo/{REPO}/ask", json={"question": q, "use_llm": True}).get_json()
    assert ai["llm"]["ok"] and ai["llm"]["invalid_citations"] == ["pr:#77"]  # the fake model's invented id is flagged
    nothing = client.post(f"/api/repo/{REPO}/ask", json={"question": "what is #500", "use_llm": True}).get_json()
    assert nothing["empty"] and nothing["llm"]["llm_called"] is False
    assert client.post(f"/api/repo/{REPO}/ask", json={"question": "  "}).status_code == 400


def test_ai_failures_become_messages_not_errors(tmp_path):
    def broken():
        raise LLMError("quota exceeded")
    app = create_app(to_file(make_db(), tmp_path / "b.sqlite"), client_factory=broken)
    out = app.test_client().post(f"/api/repo/{REPO}/ask", json={"question": "Who reviewed changes to src/a.py?", "use_llm": True})
    j = out.get_json()
    assert out.status_code == 200 and j["llm"] == {"ok": False, "error": "quota exceeded"} and "Carol" in j["evidence_text"]


def test_code_endpoints_explain_and_brief(world, tmp_path):  # noqa: F811
    conn, shas = world
    app = create_app(to_file(conn, tmp_path / "w.sqlite"), client_factory=lambda: FakeClient(lambda s, u: "Doubles x [code:L1-L3]."))
    c = app.test_client()
    syms = c.get(f"/api/repo/{REPO}/symbols?path=a.py").get_json()["symbols"]
    assert [s["name"] for s in syms] == ["alpha", "beta"]
    assert c.get(f"/api/repo/{REPO}/symbols?path=README.md").get_json()["symbols"] == []
    ex = c.post(f"/api/repo/{REPO}/code", json={"mode": "explain", "path": "a.py", "function": "alpha", "use_llm": True}).get_json()
    assert ex["target"] == "alpha" and "def alpha" in ex["evidence_text"] and ex["llm"]["citations"] == ["code:L1-L3"]
    br = c.post(f"/api/repo/{REPO}/code", json={"mode": "brief", "path": "a.py", "function": "alpha", "text": "make it async"}).get_json()
    assert "Planned change" in br["evidence_text"] and br["llm"] is None
    bad = c.post(f"/api/repo/{REPO}/code", json={"mode": "explain", "path": "a.py", "function": "nope"})
    assert bad.status_code == 400 and "Some that exist" in bad.get_json()["error"]
    rev = c.post(f"/api/repo/{REPO}/code", json={"mode": "explain", "path": "a.py", "lines": "9-1"})
    assert rev.status_code == 400 and "must not be after" in rev.get_json()["error"]
    outside = c.post(f"/api/repo/{REPO}/code", json={"mode": "explain", "path": "a.py", "lines": "1-999"})
    assert outside.status_code == 400 and "it has 8 lines" in outside.get_json()["error"]
    missing = c.post(f"/api/repo/{REPO}/code", json={"mode": "explain", "path": "nope.py"})
    assert missing.status_code == 400 and "does not exist in the latest version" in missing.get_json()["error"] and "fatal" not in missing.get_json()["error"]
    assert "Files you can try: a.py" in missing.get_json()["error"]  # tells the user what does exist
    assert c.post(f"/api/repo/{REPO}/code", json={"mode": "weird", "path": "a.py"}).status_code == 400


def test_parse_lines():
    assert parse_lines("10-40") == (10, 40) and parse_lines(" 3 - 4 ") == (3, 4) and parse_lines("") is None
    with pytest.raises(ServiceError):
        parse_lines("10 to 40")


def test_jobs_reject_bad_names_and_run_one_at_a_time(tmp_path):
    finished = []
    m = JobManager(on_finish=finished.append, command=lambda repo, skip: ["python3", "-c", "import time; time.sleep(0.4); print('done')"])
    for bad in ("", "no-slash", "a/b/c", "x/y; rm -rf /", "../etc/passwd"):
        with pytest.raises(JobError):
            m.start(bad)
    first = m.start("o/one")
    assert first["status"] == "running"
    with pytest.raises(JobError, match="Another repository"):
        m.start("o/two")
    for _ in range(40):
        if finished:
            break
        time.sleep(0.1)
    assert finished and m.list()[0]["status"] == "done"
    assert m.start("o/two")["repo"] == "o/two"  # allowed again once the first job finished


def test_job_endpoints_validate_input(client):
    assert client.post("/api/jobs", json={"repo": "bad name"}).status_code == 400
    assert client.get("/api/jobs").get_json() == []
