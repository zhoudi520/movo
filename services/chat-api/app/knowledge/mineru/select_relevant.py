"""Select relevant MinerU documents for a user question."""

from __future__ import annotations

import re

from app.knowledge.mineru.catalog import MineruDocumentInfo


def select_relevant_documents(
    documents: list[MineruDocumentInfo],
    question: str,
    *,
    max_files: int = 8,
) -> list[MineruDocumentInfo]:
    """
    Rank readable documents by simple relevance heuristics.

    Args:
        documents: Catalog entries.
        question: User query.
        max_files: Maximum documents to return.

    Returns:
        Selected readable documents.
    """
    readable = [item for item in documents if item.readable]
    if not readable:
        return []
    tokens = [t for t in re.split(r"\W+", question.lower()) if len(t) >= 2]
    if not tokens:
        return readable[:max_files]

    def score(item: MineruDocumentInfo) -> int:
        hay = f"{item.name} {item.content_summary}".lower()
        return sum(1 for token in tokens if token in hay)

    ranked = sorted(readable, key=score, reverse=True)
    if ranked[0] and score(ranked[0]) == 0:
        return readable[:max_files]
    return ranked[:max_files]
