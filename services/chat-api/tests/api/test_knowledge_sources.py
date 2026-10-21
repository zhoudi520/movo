import asyncio

from app.api.endpoints import knowledge_sources


def test_personal_knowledge_metadata_keeps_scope_for_product_extensions(monkeypatch) -> None:
    async def current_scope(_authorization):
        return "user", "tenant"

    async def find_document(_document_id, _main_id, _user_id):
        return {
            "_id": "doc",
            "scope": "personal",
            "name": "Personal document",
            "original_filename": "personal.docx",
        }

    monkeypatch.setattr(knowledge_sources, "_current_scope", current_scope)
    monkeypatch.setattr(knowledge_sources, "_find_document_or_404", find_document)

    payload = asyncio.run(knowledge_sources.get_knowledge_source_document("doc", "Bearer token"))

    assert payload["scope"] == "personal"
    assert payload["canDownload"] is True


def test_mineru_pseudo_chunk(monkeypatch, tmp_path) -> None:
    storage_root = tmp_path / "storage"
    artifact_dir = storage_root / "knowledge-documents" / "tenant" / "doc1" / "artifacts"
    artifact_dir.mkdir(parents=True)
    (artifact_dir / "parsed.md").write_text("# Title\n![img](assets/a.png)\n", encoding="utf-8")

    async def current_scope(_authorization, _access_token=None):
        return "user", "tenant"

    async def find_document(_document_id, _main_id, _user_id):
        return {
            "_id": "doc1",
            "main_id": "tenant",
            "learning_mode": "mineru",
            "parsed_markdown_key": "knowledge-documents/tenant/doc1/artifacts/parsed.md",
            "name": "Demo",
        }

    from app.core.config import get_settings

    monkeypatch.setenv("KNOWLEDGE_LOCAL_STORAGE_DIR", str(storage_root))
    get_settings.cache_clear()
    monkeypatch.setattr(knowledge_sources, "_current_scope", current_scope)
    monkeypatch.setattr(knowledge_sources, "_find_document_or_404", find_document)

    payload = asyncio.run(
        knowledge_sources.get_knowledge_source_chunk("doc1", "mineru_1", "Bearer token"),
    )

    assert payload["chunkId"] == "mineru_1"
    assert payload["contentType"] == "markdown"
    assert "/artifacts/assets/a.png" in payload["text"]
    get_settings.cache_clear()
