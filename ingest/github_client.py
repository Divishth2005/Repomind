"""Thin GitHub GraphQL client: auth, retries, and rate-limit backoff.

The token is read from the GITHUB_TOKEN environment variable only. It is
never logged, printed, or written into any raw dataset.
"""
import os
import time

import requests
from dotenv import load_dotenv

load_dotenv()

GRAPHQL_URL = "https://api.github.com/graphql"


class GitHubAuthError(RuntimeError):
    pass


class GitHubGraphQLClient:
    def __init__(self, token: str | None = None, max_retries: int = 5):
        self.token = token or os.environ.get("GITHUB_TOKEN")
        if not self.token:
            raise GitHubAuthError(
                "GITHUB_TOKEN is not set. Create a .env file (see .env.example) "
                "with GITHUB_TOKEN=<your token>, or export it in your shell."
            )
        self.max_retries = max_retries
        self.session = requests.Session()
        self.session.headers.update(
            {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}
        )

    def query(self, query: str, variables: dict) -> dict:
        last_error = None
        for attempt in range(self.max_retries):
            resp = self.session.post(
                GRAPHQL_URL, json={"query": query, "variables": variables}, timeout=30
            )

            if resp.status_code == 401:
                raise GitHubAuthError("GitHub rejected the token (401). Check it is valid and not expired.")

            if resp.status_code == 200:
                payload = resp.json()
                if "errors" in payload and not payload.get("data"):
                    last_error = RuntimeError(str(payload["errors"]))
                else:
                    rate = payload.get("data", {}).get("rateLimit")
                    if rate and rate["remaining"] < 50:
                        self._backoff_until(rate["resetAt"])
                    return payload["data"]
            else:
                last_error = RuntimeError(f"HTTP {resp.status_code}: {resp.text[:300]}")

            wait = min(2 ** attempt, 60)
            time.sleep(wait)

        raise last_error or RuntimeError("GitHub GraphQL query failed after retries")

    @staticmethod
    def _backoff_until(reset_at_iso: str):
        from datetime import datetime, timezone

        reset_at = datetime.fromisoformat(reset_at_iso.replace("Z", "+00:00"))
        wait = (reset_at - datetime.now(timezone.utc)).total_seconds()
        if wait > 0:
            time.sleep(min(wait + 2, 300))
