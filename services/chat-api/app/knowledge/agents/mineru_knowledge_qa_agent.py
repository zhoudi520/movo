"""Knowledge QA agent for MinerU-mode documents (read markdown, not vector search)."""

from __future__ import annotations

from app.core.db import get_db
from app.knowledge.api.schemas import KnowledgeChunk, KnowledgeQARequest, KnowledgeQAResult
from app.knowledge.mineru.catalog import list_mineru_documents
from app.knowledge.mineru.select_relevant import select_relevant_documents
from app.knowledge.mineru.markdown_assets import rewrite_mineru_markdown_image_urls
from app.knowledge.mineru.storage_text import read_storage_text
from app.knowledge.prompting.knowledge_qa_prompt import build_knowledge_qa_messages
from app.services.llm import LLMService


class MineruKnowledgeQAAgent:
    """Answer questions using MinerU document markdown and content summaries."""

    async def answer(self, request: KnowledgeQARequest) -> KnowledgeQAResult:
        """
        Run MinerU-style QA over documents in the requested knowledge bases.

        Args:
            request: Standard knowledge QA request.

        Returns:
            QA result with pseudo-chunks for evidence compatibility.
        """
        catalog = await list_mineru_documents(
            main_id=request.main_id,
            knowledge_base_ids=list(request.knowledge_base_ids or []),
        )
        selected = select_relevant_documents(catalog, request.query, max_files=min(request.top_n, 8))
        if not selected:
            return KnowledgeQAResult(
                answer="未在 MinerU 知识文档中找到可读取的内容。",
                citations=[],
                retrieved_chunks=[],
                used_chunk_ids=[],
            )
        chunks: list[KnowledgeChunk] = []
        db = get_db()
        for index, item in enumerate(selected):
            doc = await db.knowledge_documents.find_one({"_id": item.document_id, "main_id": request.main_id})
            if not doc:
                continue
            try:
                raw_text = read_storage_text(doc, item.parsed_markdown_key)
                text = rewrite_mineru_markdown_image_urls(raw_text, document_id=item.document_id)
            except Exception:
                continue
            chunk_id = f"mineru_{index + 1}"
            chunks.append(
                KnowledgeChunk(
                    document_id=item.document_id,
                    chunk_id=chunk_id,
                    chunk_stage="mineru",
                    text=text,
                    contextual_text=text,
                    title_path=[item.name],
                    page_no=None,
                    content_type="markdown",
                    source_chunk_ids=[],
                    ordinal=index,
                    score=1.0,
                    metadata={"document_title": item.name, "content_summary": item.content_summary},
                )
            )
        if not chunks:
            return KnowledgeQAResult(
                answer="未能读取 MinerU 文档正文。",
                citations=[],
                retrieved_chunks=[],
                used_chunk_ids=[],
            )
        messages = build_knowledge_qa_messages(request.query, chunks)
        raw = await LLMService(intent="knowledge_qa").chat_complete(messages, temperature=None)
        from app.knowledge.agents.knowledge_qa_agent import _clean_answer_text, _extract_used_chunk_ids
        from app.knowledge.citations.citation_resolver import parse_llm_json, resolve_citations

        parsed = parse_llm_json(raw)
        answer = _clean_answer_text(str(parsed.get("answer") or "")) or "内部知识库中未找到足够依据。"
        used_ids = parsed.get("usedChunkIds") or []
        if isinstance(used_ids, list):
            used_chunk_ids = [str(x) for x in used_ids]
        else:
            used_chunk_ids = _extract_used_chunk_ids(raw)
        if not used_chunk_ids:
            used_chunk_ids = [f"{c.document_id}:{c.chunk_id}" for c in chunks[:3]]
        citations = resolve_citations(chunks, used_chunk_ids)
        return KnowledgeQAResult(
            answer=answer,
            citations=citations,
            retrieved_chunks=chunks,
            used_chunk_ids=[f"{c.document_id}:{c.chunk_id}" for c in citations],
            raw_model_output=raw,
        )


mineru_knowledge_qa_agent = MineruKnowledgeQAAgent()
