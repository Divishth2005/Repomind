"""Retrieval evaluation (build plan Sec 40.4).

Task: given only an issue's TITLE, retrieve the pull request that closed it.
Ground truth comes from GitHub's own "closes #N" links (pr_issue), so it is
independent of the text search being tested. Caveats: only PRs that
explicitly link an issue are covered, and the query is a title while the
target is PR text, so this measures one kind of retrieval, not all.

Two variants are compared (PR title only vs title + body), a chance
baseline is reported, and misses are analysed for zero word overlap --
the failure lexical search cannot fix, which is the case for embeddings.
"""
import random
import sqlite3
from collections import defaultdict

from retrieval.text_search import BM25Index, build_documents, tokenize


def issue_pr_pairs(conn: sqlite3.Connection, repo: str) -> list[dict]:
    rows = conn.execute(
        """SELECT i.github_number AS issue_no, i.title AS title, p.github_number AS pr_no
           FROM pr_issue pi JOIN pull_request p ON p.pr_id = pi.pr_id
           JOIN issue i ON i.repository_id = p.repository_id AND i.github_number = pi.issue_number
           WHERE p.repository_id = ? AND length(trim(COALESCE(i.title, ''))) > 0""", (repo,)).fetchall()
    grouped = defaultdict(lambda: {"title": None, "prs": set()})
    for r in rows:
        grouped[r["issue_no"]]["title"] = r["title"]
        grouped[r["issue_no"]]["prs"].add(str(r["pr_no"]))
    return [{"issue": k, "title": v["title"], "relevant": v["prs"]} for k, v in sorted(grouped.items())]


def _score(index: BM25Index, pairs, depth=100) -> dict:
    ranks = []
    for p in pairs:
        hits = index.search(p["title"], limit=depth)
        rank = next((i for i, (d, _) in enumerate(hits, 1) if d.key in p["relevant"]), None)
        ranks.append(rank)
    n = len(ranks)
    at = lambda k: sum(1 for r in ranks if r is not None and r <= k) / n
    return {"recall@1": at(1), "recall@5": at(5), "recall@10": at(10),
            "mrr": sum(1 / r for r in ranks if r) / n, "ranks": ranks}


def evaluate(conn, repo: str, max_queries: int = 400, seed: int = 0, examples: int = 5) -> dict | None:
    pairs = issue_pr_pairs(conn, repo)
    if len(pairs) < 20:
        return None
    rng = random.Random(seed)
    if len(pairs) > max_queries:
        pairs = rng.sample(pairs, max_queries)
    body_docs = build_documents(conn, repo, "pr", include_body=True)
    title_docs = build_documents(conn, repo, "pr", include_body=False)
    with_body, title_only = BM25Index(body_docs), BM25Index(title_docs)
    n_docs = len(body_docs)

    res_body, res_title = _score(with_body, pairs), _score(title_only, pairs)
    chance = sum(min(1.0, 10 * len(p["relevant"]) / n_docs) for p in pairs) / len(pairs)

    text_by_key = {d.key: d.title + " " + d.text for d in body_docs}
    title_by_key = {d.key: d.title for d in body_docs}
    misses = [(p, r) for p, r in zip(pairs, res_body["ranks"]) if r is None or r > 10]
    zero_overlap, sample = 0, []
    for p, r in misses:
        q = set(tokenize(p["title"]))
        overlap = max((len(q & set(tokenize(text_by_key.get(k, "")))) for k in p["relevant"]), default=0)
        if overlap == 0:
            zero_overlap += 1
        if len(sample) < examples:
            k = sorted(p["relevant"])[0]
            sample.append({"issue": p["issue"], "query": p["title"], "true_pr": k, "true_pr_title": title_by_key.get(k),
                           "rank": r, "shared_words": overlap})
    return {
        "queries": len(pairs), "corpus_prs": n_docs,
        "with_body": {k: v for k, v in res_body.items() if k != "ranks"},
        "title_only": {k: v for k, v in res_title.items() if k != "ranks"},
        "chance_recall@10": chance, "misses_at_10": len(misses),
        "misses_with_zero_word_overlap": zero_overlap, "miss_examples": sample,
    }
