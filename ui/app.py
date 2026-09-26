"""The web app: a small JSON API plus one static page. Local use only
(bound to 127.0.0.1); API keys stay on the server and never reach the page."""
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

from llm.client import make_client
from ui.jobs import JobError, JobManager
from ui.services import ServiceError, Workspace

ROOT = Path(__file__).resolve().parent.parent
STATIC = Path(__file__).resolve().parent / "static"


def create_app(db_path=None, client_factory=None, job_command=None) -> Flask:
    app = Flask(__name__, static_folder=None)
    ws = Workspace(db_path or ROOT / "data" / "repomind.sqlite", client_factory or (lambda: make_client(max_retries=1)))
    jobs = JobManager(on_finish=lambda job: ws.invalidate(), command=job_command)
    app.config["workspace"], app.config["jobs"] = ws, jobs

    @app.errorhandler(ServiceError)
    def service_error(e):
        return jsonify({"error": str(e)}), e.status

    @app.errorhandler(JobError)
    def job_error(e):
        return jsonify({"error": str(e)}), 400

    def body():
        return request.get_json(silent=True) or {}

    @app.get("/")
    def index():
        return send_from_directory(STATIC, "index.html")

    @app.get("/static/<path:name>")
    def static_files(name):
        return send_from_directory(STATIC, name)

    @app.get("/api/repos")
    def repos():
        return jsonify(ws.repos())

    R = "/api/repo/<owner>/<name>"

    @app.get(R + "/overview")
    def overview(owner, name):
        return jsonify(ws.overview(f"{owner}/{name}"))

    @app.get(R + "/risk")
    def risk(owner, name):
        return jsonify(ws.risk(f"{owner}/{name}", request.args.get("depth", 2), request.args.get("active_days", 365)))

    @app.get(R + "/map")
    def graph(owner, name):
        return jsonify(ws.graph(f"{owner}/{name}", request.args.get("top", 15), request.args.get("files", 6)))

    @app.get(R + "/files")
    def files(owner, name):
        return jsonify(ws.files(f"{owner}/{name}", request.args.get("q", "")))

    @app.get(R + "/symbols")
    def symbols(owner, name):
        return jsonify(ws.symbols(f"{owner}/{name}", request.args.get("path", "")))

    @app.get(R + "/search")
    def search(owner, name):
        return jsonify(ws.search(f"{owner}/{name}", request.args.get("q", "")))

    @app.get(R + "/item")
    def item(owner, name):
        return jsonify(ws.item(f"{owner}/{name}", request.args.get("ref", "")))

    @app.get(R + "/file")
    def file_summary(owner, name):
        return jsonify(ws.file_summary(f"{owner}/{name}", request.args.get("path", "")))

    @app.post(R + "/ask")
    def ask(owner, name):
        b = body()
        return jsonify(ws.ask(f"{owner}/{name}", b.get("question"), bool(b.get("use_llm"))))

    @app.post(R + "/code")
    def code(owner, name):
        b = body()
        return jsonify(ws.code(f"{owner}/{name}", b.get("mode", "explain"), b.get("path"), b.get("function"),
                               b.get("lines"), b.get("text"), bool(b.get("use_llm"))))

    @app.get("/api/jobs")
    def list_jobs():
        return jsonify(jobs.list())

    @app.post("/api/jobs")
    def start_job():
        b = body()
        return jsonify(jobs.start(b.get("repo", ""), bool(b.get("skip_github")))), 202

    return app
