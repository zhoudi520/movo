"""Persist external document provenance in the existing execution evidence stream."""

from __future__ import annotations

from typing import Any

from app.enterprise_capabilities.evidence.foundation import EvidenceNormalizer


def build_external_knowledge_evidence(*, query: str, mapped: dict[str, Any]) -> dict[str, Any]:
    answer = str(mapped.get("answer") or "")
    rows = list((mapped.get("evidence_bundle") or {}).get("sources") or [])
    results = []
    for source in rows[:20]:
        if not isinstance(source, dict):
            continue
        name = str(source.get("source_name") or "外部知识库")
        snippet = str(source.get("snippet") or "")
        results.append({
            "tool": "knowledge_search",
            "title": str(source.get("title") or name),
            "source": name,
            "source_url": str(source.get("source_url") or ""),
            "content": snippet or answer,
            "summary": snippet or answer,
            "meta": {
                "provenance": "external_knowledge",
                "source_name": name,
            },
        })
    return EvidenceNormalizer.build_research_bundle(
        query=query, tools_used=["knowledge_search"], results=results,
    )
