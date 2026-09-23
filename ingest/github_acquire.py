"""Paginated GitHub acquisition with resumable checkpoints.

Writes one raw JSON node per line per resource (issues.jsonl,
pull_requests.jsonl, labels.jsonl). A checkpoint file records the last
cursor consumed per resource so a re-run resumes instead of restarting.
"""
import json
from pathlib import Path

from ingest.github_client import GitHubGraphQLClient
from ingest.github_queries import ISSUES_QUERY, LABELS_QUERY, PULL_REQUESTS_QUERY

RESOURCES = {
    "issues": (ISSUES_QUERY, "issues"),
    "pull_requests": (PULL_REQUESTS_QUERY, "pullRequests"),
    "labels": (LABELS_QUERY, "labels"),
}


def _load_checkpoint(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text())
    return {}


def _save_checkpoint(path: Path, checkpoint: dict):
    path.write_text(json.dumps(checkpoint, indent=2))


def acquire_resource(
    client: GitHubGraphQLClient,
    owner: str,
    name: str,
    resource: str,
    out_dir: Path,
    checkpoint_path: Path,
) -> int:
    query, field = RESOURCES[resource]
    checkpoint = _load_checkpoint(checkpoint_path)
    state = checkpoint.get(resource, {"cursor": None, "done": False})

    if state["done"]:
        print(f"[github] {resource}: already complete, skipping")
        return state.get("count", 0)

    out_path = out_dir / f"{resource}.jsonl"
    mode = "a" if state["cursor"] else "w"
    count = state.get("count", 0)
    page = 0

    with out_path.open(mode, encoding="utf-8") as f:
        while True:
            data = client.query(query, {"owner": owner, "name": name, "cursor": state["cursor"]})
            connection = data["repository"][field]
            nodes = connection["nodes"]

            for node in nodes:
                f.write(json.dumps(node, ensure_ascii=False) + "\n")
                count += 1

            page += 1
            page_info = connection["pageInfo"]
            state["cursor"] = page_info["endCursor"]
            state["count"] = count
            state["done"] = not page_info["hasNextPage"]
            checkpoint[resource] = state
            _save_checkpoint(checkpoint_path, checkpoint)

            print(f"[github] {resource}: page {page}, {count} items so far")

            if not page_info["hasNextPage"]:
                break

    return count


def acquire_github_data(owner: str, name: str, out_dir: Path) -> dict:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = out_dir / "checkpoint.json"

    client = GitHubGraphQLClient()
    results = {}
    for resource in RESOURCES:
        print(f"[github] acquiring {resource} for {owner}/{name} ...")
        results[resource] = acquire_resource(client, owner, name, resource, out_dir, checkpoint_path)

    return results
