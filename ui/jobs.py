"""Add a repository from the UI by running the normal pipeline in the
background (one job at a time, since it writes to the shared database)."""
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = ROOT / "data" / "processed" / "_ui"
REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


class JobError(Exception):
    pass


class JobManager:
    def __init__(self, on_finish=None, command=None):
        self.jobs: dict[str, dict] = {}
        self.on_finish = on_finish
        self.command = command or (lambda repo, skip: [sys.executable, "-u", "pipeline.py", "--repo", repo] + (["--skip-github"] if skip else []))
        self.lock = threading.Lock()

    def start(self, repo: str, skip_github: bool = False) -> dict:
        if not REPO_RE.match(repo or ""):
            raise JobError("Repository must look like owner/name")
        with self.lock:
            if any(j["status"] == "running" for j in self.jobs.values()):
                raise JobError("Another repository is still being added; wait for it to finish.")
            LOG_DIR.mkdir(parents=True, exist_ok=True)
            log_path = LOG_DIR / (repo.replace("/", "__") + ".log")
            job = {"repo": repo, "status": "running", "started": time.time(), "log": str(log_path), "skip_github": skip_github}
            self.jobs[repo] = job
            threading.Thread(target=self._run, args=(job,), daemon=True).start()
            return self.describe(job)

    def _run(self, job):
        with open(job["log"], "w") as log:
            code = subprocess.run(self.command(job["repo"], job["skip_github"]), cwd=ROOT, stdout=log, stderr=subprocess.STDOUT).returncode
        job["status"] = "done" if code == 0 else "failed"
        job["finished"] = time.time()
        if self.on_finish:
            self.on_finish(job)

    @staticmethod
    def describe(job) -> dict:
        try:
            lines = Path(job["log"]).read_text(errors="replace").strip().splitlines()[-6:]
        except OSError:
            lines = []
        end = job.get("finished", time.time())
        return {"repo": job["repo"], "status": job["status"], "seconds": round(end - job["started"]), "skip_github": job["skip_github"],
                "log_tail": lines}

    def list(self) -> list[dict]:
        return [self.describe(j) for j in self.jobs.values()]
