"""Model-free checks for Module 10 (no LLM involved).

cochange_eval: does what changed together in the past predict what changes
together in the future? Commits are split by time (first 70% train, last 30%
test). For each test commit and each file in it that the training data knows,
the top-k co-change partners are predicted from the training data only and
compared with the other files actually changed in that commit. The baseline
predicts the k most frequently changed files overall (a strong default,
since busy files are in many commits).

bugfix_eval: how well does "the wording says fix" agree with GitHub's own bug
labels? Positives are PRs that closed an issue labelled as a bug; negatives
are PRs that closed only labelled non-bug issues. Labels are imperfect ground
truth, so this is a sanity check on the rule, not a measure of truth.
"""
import sqlite3
from collections import Counter

from assist.bugfix import has_bug_label, looks_like_fix
from assist.cochange import CoChange, load_commits


def cochange_eval(conn: sqlite3.Connection, repo: str, k: int = 5, min_support: int = 3,
                  train_frac: float = 0.7, max_files: int = 30, skip_boilerplate: bool = False) -> dict:
    commits = load_commits(conn, repo, max_files, skip_boilerplate=skip_boilerplate)
    if len(commits) < 50:
        return {"repo": repo, "commits": len(commits), "cases": 0}
    cut = int(len(commits) * train_frac)
    train, test = commits[:cut], commits[cut:]
    model = CoChange(train)
    popular = [p for p, _ in model.file_count.most_common(k + 1)]

    cases = hits_co = hits_pop = 0
    prec_co = prec_pop = 0.0
    multi_file = 0
    for _, paths in test:
        if len(paths) < 2:
            continue
        for f in paths:
            multi_file += 1
            if model.file_count.get(f, 0) < min_support:
                continue
            others = paths - {f}
            co = [r["path"] for r in model.partners(f, k, min_support=2)]
            pop = [p for p in popular if p != f][:k]
            cases += 1
            hit_c = others & set(co)
            hit_p = others & set(pop)
            hits_co += bool(hit_c)
            hits_pop += bool(hit_p)
            prec_co += len(hit_c) / len(co) if co else 0.0
            prec_pop += len(hit_p) / len(pop) if pop else 0.0
    if not cases:
        return {"repo": repo, "commits": len(commits), "cases": 0}
    return {
        "repo": repo, "commits": len(commits), "train_commits": len(train), "test_commits": len(test),
        "cases": cases, "coverage": cases / multi_file if multi_file else None,
        f"hit@{k}_cochange": hits_co / cases, f"hit@{k}_popularity": hits_pop / cases,
        f"precision_cochange": prec_co / cases, f"precision_popularity": prec_pop / cases,
        "k": k,
    }


def bugfix_eval(conn: sqlite3.Connection, repo: str) -> dict:
    rows = conn.execute(
        """SELECT p.github_number AS pr, p.title AS title, i.labels AS labels FROM pr_issue pi
           JOIN pull_request p ON p.pr_id = pi.pr_id
           JOIN issue i ON i.github_number = pi.issue_number AND i.repository_id = p.repository_id
           WHERE p.repository_id = ?""", (repo,)).fetchall()
    per_pr: dict[int, dict] = {}
    for r in rows:
        labels = r["labels"] or "[]"
        if labels == "[]":
            continue  # unlabeled issue: no ground truth either way
        e = per_pr.setdefault(r["pr"], {"title": r["title"], "bug": False})
        e["bug"] = e["bug"] or has_bug_label(labels)
    pos = [e for e in per_pr.values() if e["bug"]]
    neg = [e for e in per_pr.values() if not e["bug"]]
    if len(pos) < 10 or len(neg) < 10:
        return {"repo": repo, "positives": len(pos), "negatives": len(neg), "enough": False}
    tp = sum(looks_like_fix(e["title"]) for e in pos)
    fp = sum(looks_like_fix(e["title"]) for e in neg)
    return {"repo": repo, "enough": True, "positives": len(pos), "negatives": len(neg),
            "recall_on_bug_labelled": tp / len(pos), "fires_on_non_bug": fp / len(neg),
            "precision": tp / (tp + fp) if tp + fp else None}
