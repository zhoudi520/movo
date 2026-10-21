"""Embed citation images into knowledge QA answers when they match cited fragment context."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.knowledge.mineru.markdown_assets import rewrite_mineru_markdown_image_urls

_MD_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
_HTML_IMAGE_RE = re.compile(
    r'<img\b[^>]*\bsrc=["\']([^"\']+)["\'][^>]*(?:alt=["\']([^"\']*)["\'])?',
    re.IGNORECASE,
)
_HEADING_RE = re.compile(r"^#{1,6}\s+(.+)$", re.MULTILINE)


def _normalize_image_url(url: str) -> str:
    """Normalize image URL for deduplication."""
    return str(url or "").strip().split("?", 1)[0].replace("\\", "/")


def _normalize_match_text(value: str) -> str:
    """Normalize text for loose overlap scoring between answer and chunk context."""
    text = str(value or "").lower()
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"[^\w\u3400-\u9fff]", "", text)
    return text


def _context_tokens(text: str, *, size: int = 4) -> set[str]:
    """Build character n-grams from normalized context text."""
    normalized = _normalize_match_text(text)
    if len(normalized) < size:
        return {normalized} if normalized else set()
    return {normalized[index : index + size] for index in range(0, len(normalized) - size + 1)}


def _overlap_score(answer: str, context: str) -> float:
    """
    Score how much the answer overlaps with local markdown context around an image.

    Args:
        answer: Full LLM answer text.
        context: Nearby heading/paragraph text from the cited fragment.

    Returns:
        Ratio of matched context n-grams (0..1).
    """
    tokens = _context_tokens(context)
    if not tokens:
        return 0.0
    answer_norm = _normalize_match_text(answer)
    if not answer_norm:
        return 0.0
    hits = sum(1 for token in tokens if token in answer_norm)
    return hits / len(tokens)


@dataclass(frozen=True)
class _ImageCandidate:
    """One image extracted from a cited fragment with local context."""

    markdown_line: str
    url: str
    context: str


def _nearest_heading(text: str, position: int) -> str:
    """Return the nearest markdown heading above ``position``."""
    heading = ""
    for match in _HEADING_RE.finditer(text):
        if match.start() <= position:
            heading = str(match.group(1) or "").strip()
        else:
            break
    return heading


def _image_context(text: str, start: int, end: int, alt: str) -> str:
    """Build local context windows around one image reference."""
    before = text[max(0, start - 420) : start]
    after = text[end : min(len(text), end + 220)]
    heading = _nearest_heading(text, start)
    parts = [part for part in (heading, alt, before, after) if str(part or "").strip()]
    return "\n".join(parts)


def _extract_image_candidates(text: str) -> list[_ImageCandidate]:
    """
    Extract image candidates and their local context from one chunk body.

    Args:
        text: Cited fragment markdown.

    Returns:
        Ordered image candidates.
    """
    body = str(text or "")
    output: list[_ImageCandidate] = []
    seen: set[str] = set()
    for match in _MD_IMAGE_RE.finditer(body):
        alt = str(match.group(1) or "").strip()
        url = str(match.group(2) or "").strip()
        if not url:
            continue
        key = _normalize_image_url(url)
        if key in seen:
            continue
        seen.add(key)
        context = _image_context(body, match.start(), match.end(), alt)
        output.append(_ImageCandidate(markdown_line=f"![{alt}]({url})", url=url, context=context))
    for match in _HTML_IMAGE_RE.finditer(body):
        url = str(match.group(1) or "").strip()
        alt = str(match.group(2) or "").strip()
        if not url:
            continue
        key = _normalize_image_url(url)
        if key in seen:
            continue
        seen.add(key)
        context = _image_context(body, match.start(), match.end(), alt)
        output.append(_ImageCandidate(markdown_line=f"![{alt}]({url})", url=url, context=context))
    return output


def extract_markdown_image_lines(text: str) -> list[str]:
    """Return markdown image lines found in a cited fragment."""
    return [item.markdown_line for item in _extract_image_candidates(text)]


def _split_answer_blocks(answer: str) -> list[str]:
    """Split answer markdown into paragraph/list blocks for inline image placement."""
    blocks = [block.strip() for block in re.split(r"\n\n+", str(answer or "")) if block.strip()]
    return blocks or [str(answer or "").strip()]


def _join_answer_blocks(blocks: list[str]) -> str:
    """Join answer blocks back into markdown."""
    return "\n\n".join(block for block in blocks if block.strip())


def embed_relevant_citation_images(
    answer: str,
    citation_texts: list[str],
    *,
    max_images: int = 3,
    min_score: float = 0.08,
    min_hits: int = 3,
) -> str:
    """
    Insert images from cited fragments inline when their local context matches the answer.

    Images are only placed after the answer block with the strongest contextual overlap.
    Unrelated images are skipped (no bulk appendix section).

    Args:
        answer: LLM-generated markdown answer.
        citation_texts: Bodies of used citations / chunks (not whole documents).
        max_images: Maximum number of images to embed.
        min_score: Minimum n-gram overlap ratio against image context.
        min_hits: Minimum matched n-grams required even when ratio is low.

    Returns:
        Answer with relevant images embedded inline.
    """
    base = str(answer or "").strip()
    if not base or base == "内部知识库中未找到足够依据。":
        return base

    present_urls = {_normalize_image_url(match.group(2)) for match in _MD_IMAGE_RE.finditer(base)}
    present_urls.update(_normalize_image_url(match.group(1)) for match in _HTML_IMAGE_RE.finditer(base))

    candidates: list[tuple[_ImageCandidate, float, int]] = []
    for text in citation_texts:
        for item in _extract_image_candidates(text):
            url_key = _normalize_image_url(item.url)
            if url_key in present_urls:
                continue
            score = _overlap_score(base, item.context)
            hits = len(_context_tokens(item.context) & _context_tokens(base))
            if score < min_score and hits < min_hits:
                continue
            candidates.append((item, score, hits))

    if not candidates:
        return base

    candidates.sort(key=lambda row: (row[1], row[2]), reverse=True)
    blocks = _split_answer_blocks(base)
    embedded = 0
    for item, score, _hits in candidates:
        if embedded >= max_images:
            break
        url_key = _normalize_image_url(item.url)
        if url_key in present_urls:
            continue
        best_index = 0
        best_block_score = -1.0
        for index, block in enumerate(blocks):
            block_score = _overlap_score(block, item.context)
            if block_score > best_block_score:
                best_block_score = block_score
                best_index = index
        if best_block_score < min_score and _overlap_score(base, item.context) < min_score:
            continue
        blocks[best_index] = f"{blocks[best_index]}\n\n{item.markdown_line}"
        present_urls.add(url_key)
        embedded += 1

    return _join_answer_blocks(blocks)


def enrich_answer_with_used_chunks(
    answer: str,
    used_chunks: list[dict[str, Any]],
    *,
    max_images: int = 3,
) -> str:
    """
    Embed relevant images from used chunk bodies (with MinerU URL rewriting).

    Args:
        answer: LLM-generated markdown answer.
        used_chunks: Serialized used chunk rows from internal knowledge QA.
        max_images: Maximum inline images to embed.

    Returns:
        Answer with contextually relevant citation images embedded inline.
    """
    texts: list[str] = []
    for row in list(used_chunks or []):
        if not isinstance(row, dict):
            continue
        document_id = str(row.get("documentId") or "").strip()
        text = str(row.get("text") or "").strip()
        if not text:
            continue
        if document_id:
            text = rewrite_mineru_markdown_image_urls(text, document_id=document_id)
        texts.append(text)
    return embed_relevant_citation_images(answer, texts, max_images=max_images)
