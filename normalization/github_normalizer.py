"""Turn raw issues.jsonl / pull_requests.jsonl / labels.jsonl into normalized
Issue, PullRequest, Review, and Label records.

Each record's `raw_source_reference` points back at its file and GitHub
number/name, which is the natural key in the raw GraphQL dump.
"""
import json
from pathlib import Path

from normalization.identity import IdentityResolver, stable_id
from normalization.schema import Issue, Label, PullRequest, Review


def _read_jsonl(path: Path):
    if not path.exists():
        return
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def normalize_github(
    github_raw_dir: Path,
    owner: str,
    name: str,
    resolver: IdentityResolver,
) -> dict:
    github_raw_dir = Path(github_raw_dir)
    repository_id = f"{owner}/{name}"

    labels: dict[str, Label] = {}
    issues: list[Issue] = []
    prs: list[PullRequest] = []
    reviews: list[Review] = []

    for raw in _read_jsonl(github_raw_dir / "labels.jsonl"):
        label_id = stable_id("label", repository_id, raw["name"])
        labels[raw["name"]] = Label(
            label_id=label_id, repository_id=repository_id, name=raw["name"], color=raw["color"]
        )

    for raw in _read_jsonl(github_raw_dir / "issues.jsonl"):
        author_login = (raw.get("author") or {}).get("login")
        author_dev_id = resolver.resolve_github_login(author_login)
        label_names = [l["name"] for l in raw.get("labels", {}).get("nodes", [])]

        issues.append(
            Issue(
                issue_id=stable_id("issue", repository_id, str(raw["number"])),
                repository_id=repository_id,
                github_number=raw["number"],
                title=raw["title"] or "",
                body=raw.get("body") or "",
                state=raw["state"],
                author_developer_id=author_dev_id,
                created_at=raw.get("createdAt"),
                closed_at=raw.get("closedAt"),
                labels=label_names,
                raw_source_reference=f"issues.jsonl#{raw['number']}",
            )
        )

    for raw in _read_jsonl(github_raw_dir / "pull_requests.jsonl"):
        author_login = (raw.get("author") or {}).get("login")
        author_dev_id = resolver.resolve_github_login(author_login)
        label_names = [l["name"] for l in raw.get("labels", {}).get("nodes", [])]
        commit_shas = [c["commit"]["oid"] for c in raw.get("commits", {}).get("nodes", [])]
        closing_issue_numbers = [
            i["number"] for i in raw.get("closingIssuesReferences", {}).get("nodes", [])
        ]
        pr_id = stable_id("pr", repository_id, str(raw["number"]))

        prs.append(
            PullRequest(
                pr_id=pr_id,
                repository_id=repository_id,
                github_number=raw["number"],
                title=raw["title"] or "",
                body=raw.get("body") or "",
                state=raw["state"],
                author_developer_id=author_dev_id,
                created_at=raw.get("createdAt"),
                merged_at=raw.get("mergedAt"),
                labels=label_names,
                commit_shas=commit_shas,
                closing_issue_numbers=closing_issue_numbers,
                raw_source_reference=f"pull_requests.jsonl#{raw['number']}",
            )
        )

        for r in raw.get("reviews", {}).get("nodes", []):
            reviewer_login = (r.get("author") or {}).get("login")
            reviewer_dev_id = resolver.resolve_github_login(reviewer_login)
            reviews.append(
                Review(
                    review_id=stable_id(
                        "review", pr_id, reviewer_login or "unknown", r.get("submittedAt") or ""
                    ),
                    pr_id=pr_id,
                    reviewer_developer_id=reviewer_dev_id,
                    state=r["state"],
                    submitted_at=r.get("submittedAt"),
                    body=r.get("body") or "",
                )
            )

    return {
        "labels": list(labels.values()),
        "issues": issues,
        "pull_requests": prs,
        "reviews": reviews,
    }
