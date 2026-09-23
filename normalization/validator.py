"""Sanity checks over normalized data: dangling foreign keys, missing
identities, and record-count sanity vs. the raw input. Cheap, structural
checks -- not a substitute for the research-level evaluation in Phase 7.
"""


def validate(normalized: dict) -> dict:
    issues = []

    developer_ids = {d["developer_id"] for d in normalized["developers"]}
    commit_ids = {c.commit_id for c in normalized["commits"]}
    file_ids = {f.file_id for f in normalized["files"]}
    pr_ids = {p.pr_id for p in normalized["pull_requests"]}

    for c in normalized["commits"]:
        if c.author_developer_id not in developer_ids:
            issues.append(f"commit {c.commit_id}: unknown author_developer_id")
        if c.committer_developer_id not in developer_ids:
            issues.append(f"commit {c.commit_id}: unknown committer_developer_id")

    for cf in normalized["commit_files"]:
        if cf.commit_id not in commit_ids:
            issues.append(f"commit_file {cf.commit_file_id}: dangling commit_id {cf.commit_id}")
        if cf.file_id not in file_ids:
            issues.append(f"commit_file {cf.commit_file_id}: dangling file_id {cf.file_id}")

    for pr in normalized["pull_requests"]:
        if pr.author_developer_id and pr.author_developer_id not in developer_ids:
            issues.append(f"pr {pr.github_number}: unknown author_developer_id")

    for r in normalized["reviews"]:
        if r.pr_id not in pr_ids:
            issues.append(f"review {r.review_id}: dangling pr_id {r.pr_id}")
        if r.reviewer_developer_id and r.reviewer_developer_id not in developer_ids:
            issues.append(f"review {r.review_id}: unknown reviewer_developer_id")

    for issue in normalized["issues"]:
        if issue.author_developer_id and issue.author_developer_id not in developer_ids:
            issues.append(f"issue {issue.github_number}: unknown author_developer_id")

    return {
        "ok": len(issues) == 0,
        "issue_count": len(issues),
        "issues": issues[:50],
        "counts": {
            "developers": len(developer_ids),
            "files": len(file_ids),
            "commits": len(commit_ids),
            "commit_files": len(normalized["commit_files"]),
            "issues": len(normalized["issues"]),
            "pull_requests": len(pr_ids),
            "reviews": len(normalized["reviews"]),
            "labels": len(normalized["labels"]),
        },
    }
