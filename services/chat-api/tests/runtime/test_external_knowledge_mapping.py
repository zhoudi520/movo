from app.enterprise_capabilities.knowledge_source.mapping import map_response
from app.enterprise_capabilities.knowledge_source.evidence import build_external_knowledge_evidence
from app.dsh_runtime.evidence_projection import project_execution_evidence


MAPPING = {
    "answerPath": "response.answer",
    "sourcesPath": "response.references",
    "titlePath": "title",
    "snippetPath": "snippet",
    "documentUrlPath": "documentUrl",
}


def test_maps_multiple_documents_with_original_links() -> None:
    outcome = {
        "success": True,
        "raw": {"structuredContent": {
            "answer": "年假按司龄计算。",
            "references": [
                {"title": "休假制度", "snippet": "按司龄计算", "documentUrl": "https://kb.example.test/leave"},
                {"title": "补充政策", "documentUrl": "https://kb.example.test/supplement"},
            ],
        }},
    }
    result = map_response(outcome, {"displayName": "企业规章知识库", "mapping": MAPPING})
    assert result["answer"] == "年假按司龄计算。"
    assert [item["title"] for item in result["evidence_bundle"]["sources"]] == ["休假制度", "补充政策"]
    assert result["evidence_bundle"]["sources"][0]["source_url"] == "https://kb.example.test/leave"
    assert all(item["source_name"] == "企业规章知识库" for item in result["evidence_bundle"]["sources"])
    persisted = build_external_knowledge_evidence(query="年假如何计算？", mapped=result)
    visible = project_execution_evidence(persisted)
    assert len(visible["sources"]) == 2
    assert visible["sources"][0]["source_type"] == "external_knowledge"
    assert visible["sources"][0]["source_url"] == "https://kb.example.test/leave"
    assert visible["sources"][1]["source_name"] == "企业规章知识库"


def test_answer_without_document_provenance_stays_available() -> None:
    result = map_response(
        {"success": True, "raw": {"answer": "直接回答"}},
        {"displayName": "外部库", "mapping": {"answerPath": "answer"}},
    )
    assert result["answer"] == "直接回答"
    assert result["evidence_bundle"]["sources"][0]["source_name"] == "外部库"


def test_custom_result_field_maps_without_default_answer_name() -> None:
    result = map_response(
        {"success": True, "raw": {"structuredContent": {
            "result": "自定义字段中的答案", "hits": [{"heading": "企业制度"}],
        }}},
        {"displayName": "外部库", "mapping": {
            "answerPath": "response.result", "sourcesPath": "response.hits", "titlePath": "heading",
        }},
    )
    assert result["answer"] == "自定义字段中的答案"
    assert result["evidence_bundle"]["sources"][0]["title"] == "企业制度"


def test_unsafe_links_are_not_exposed() -> None:
    result = map_response(
        {"success": True, "raw": {"response": {"answer": "回答", "references": [{"title": "文档", "documentUrl": "javascript:alert(1)"}]}}},
        {"displayName": "外部库", "mapping": MAPPING},
    )
    assert result["evidence_bundle"]["sources"][0]["source_url"] == ""
