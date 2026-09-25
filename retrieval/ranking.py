"""Rank fusion. Reciprocal Rank Fusion combines ranked lists whose raw
scores are not comparable (BM25 scores from different corpora, recency
order, structured matches) using only each item's rank."""


def rrf(rank_lists: list[list[str]], weights: list[float] | None = None, k: int = 60) -> list[tuple[str, float]]:
    weights = weights or [1.0] * len(rank_lists)
    scores: dict[str, float] = {}
    for ranks, w in zip(rank_lists, weights):
        for position, key in enumerate(ranks, start=1):
            scores[key] = scores.get(key, 0.0) + w / (k + position)
    return sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
