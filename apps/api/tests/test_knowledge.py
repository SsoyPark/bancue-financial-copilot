import json
from pathlib import Path

from app.knowledge import (
    attach_evidence,
    explain_knowledge_search,
    load_knowledge_directory,
    search_knowledge,
    source_registry,
)
from app.models import Consultation, ConsultationStatus, RiskLevel


def write_document(path, document_id: str, title: str, keywords: list[str]) -> None:
    path.write_text(
        json.dumps(
            {
                "document_id": document_id,
                "title": title,
                "section": "테스트 조항",
                "status": "Valid",
                "effective_date": "2026-01-01",
                "keywords": keywords,
                "content": f"{title}의 처리 기준입니다.",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def consultation(question: str) -> Consultation:
    return Consultation(
        id="knowledge-test-1",
        customer="고객",
        topic="자동이체",
        summary="자동이체 조회 문의",
        question=question,
        risk=RiskLevel.LOW,
        status=ConsultationStatus.READY,
        waiting_time="00:00",
        intent="자동이체 조회",
        required_checks=["공식 근거 검색"],
    )


def test_search_ranks_relevant_document_first(tmp_path) -> None:
    write_document(tmp_path / "auto.json", "KB-AUTO", "자동이체 지침", ["자동이체", "조회"])
    write_document(tmp_path / "card.json", "KB-CARD", "카드 지침", ["카드", "분실"])
    documents = load_knowledge_directory(tmp_path).documents

    matches = search_knowledge("자동이체를 어디서 조회하나요?", documents)

    assert matches[0].document.document_id == "KB-AUTO"
    assert matches[0].matched_terms == ("자동이체", "조회")
    assert matches[0].score >= 10


def test_search_returns_empty_without_keyword_match(tmp_path) -> None:
    write_document(tmp_path / "auto.json", "KB-AUTO", "자동이체 지침", ["자동이체"])
    documents = load_knowledge_directory(tmp_path).documents
    assert search_knowledge("새로운 유형의 일반 문의", documents) == []


def test_confidence_gate_abstains_on_single_keyword(tmp_path) -> None:
    write_document(
        tmp_path / "auto.json",
        "KB-AUTO",
        "자동이체 지침",
        ["자동이체", "조회"],
    )
    documents = load_knowledge_directory(tmp_path).documents

    assert search_knowledge("자동이체 API 개발 문서", documents) == []
    assert search_knowledge(
        "자동이체 API 개발 문서",
        documents,
        minimum_score=0,
    )


def test_does_not_double_count_nested_keywords(tmp_path) -> None:
    write_document(
        tmp_path / "remit.json",
        "KB-REMIT",
        "해외송금 지침",
        ["해외송금", "송금", "보류"],
    )
    documents = load_knowledge_directory(tmp_path).documents

    matches = search_knowledge(
        "해외송금 회사에 취업하고 싶어요.",
        documents,
        minimum_score=0,
    )

    assert matches[0].matched_terms == ("해외송금",)
    assert matches[0].score < 8


def test_explain_search_accepts_candidate_above_threshold(tmp_path) -> None:
    write_document(
        tmp_path / "auto.json",
        "KB-AUTO",
        "자동이체 지침",
        ["자동이체", "조회"],
    )
    documents = load_knowledge_directory(tmp_path).documents

    trace = explain_knowledge_search("자동이체 조회", documents)

    assert trace.decision == "grounded"
    assert trace.minimum_score == 8
    assert trace.candidates[0].document_id == "KB-AUTO"
    assert trace.candidates[0].accepted is True
    assert trace.candidates[0].score >= trace.minimum_score


def test_explain_search_shows_rejected_candidate(tmp_path) -> None:
    write_document(
        tmp_path / "remit.json",
        "KB-REMIT",
        "해외송금 지침",
        ["해외송금", "송금", "보류"],
    )
    documents = load_knowledge_directory(tmp_path).documents

    trace = explain_knowledge_search(
        "해외송금 회사에 취업하려면 어떤 자격증이 필요한가요?",
        documents,
    )

    assert trace.decision == "abstained"
    assert trace.candidates[0].document_id == "KB-REMIT"
    assert trace.candidates[0].accepted is False
    assert trace.candidates[0].score < trace.minimum_score
    assert "검색을 중단" in trace.reason


def test_search_uses_query_expansion_for_indirect_expression(tmp_path) -> None:
    write_document(
        tmp_path / "auto.json",
        "KB-AUTO",
        "자동이체 지침",
        ["자동이체", "자동납부", "출금계좌", "변경"],
    )
    documents = load_knowledge_directory(tmp_path).documents

    matches = search_knowledge(
        "매달 빠져나가는 금액을 다른 통장에서 나가게 하고 싶어요.",
        documents,
    )

    assert matches[0].document.document_id == "KB-AUTO"
    assert matches[0].query_expansions == (
        "자동이체",
        "자동납부",
        "출금계좌",
        "변경",
    )
    assert matches[0].query_rule_ids == ("QUERY-AUTO-001", "QUERY-AUTO-002")


def test_attach_evidence_updates_required_check(tmp_path) -> None:
    write_document(tmp_path / "auto.json", "KB-AUTO", "자동이체 지침", ["자동이체", "조회"])
    documents = load_knowledge_directory(tmp_path).documents

    result = attach_evidence(consultation("자동이체를 조회하고 싶어요."), documents)

    assert result.evidence[0].document_id == "KB-AUTO"
    assert result.evidence[0].matched_terms == ["자동이체", "조회"]
    assert result.retrieval_trace is not None
    assert result.retrieval_trace.decision == "grounded"
    assert "공식 근거 검색" not in result.required_checks
    assert "근거 문서 유효일 확인" in result.required_checks


def test_attach_evidence_keeps_abstention_trace_without_evidence(tmp_path) -> None:
    write_document(
        tmp_path / "auto.json",
        "KB-AUTO",
        "자동이체 지침",
        ["자동이체", "조회"],
    )
    documents = load_knowledge_directory(tmp_path).documents
    item = consultation("API 개발 문서를 찾고 있어요.").model_copy(
        update={
            "topic": "개발",
            "summary": "자동이체 API 개발",
            "intent": "개발 문서 확인",
        }
    )

    result = attach_evidence(item, documents)

    assert result.evidence == []
    assert result.retrieval_trace is not None
    assert result.retrieval_trace.decision == "abstained"
    assert result.retrieval_trace.candidates[0].accepted is False


def test_loads_official_source_metadata() -> None:
    data_dir = Path(__file__).resolve().parents[1] / "data" / "knowledge"
    result = load_knowledge_directory(data_dir)

    assert result.loaded_files == 5
    assert result.official_documents == 5
    assert result.synthetic_documents == 0
    assert result.review_required_documents == 0
    registry = source_registry(result.documents)
    assert registry[0]["source_type"] == "official-public"
    assert registry[0]["source_url"].startswith("https://")
    assert registry[0]["verified_at"] == "2026-08-21"


def test_skips_official_document_without_source_url(tmp_path) -> None:
    payload = {
        "document_id": "KB-BROKEN",
        "title": "출처 누락 문서",
        "section": "테스트",
        "status": "Valid",
        "effective_date": "2026-01-01",
        "keywords": ["테스트"],
        "content": "출처 URL이 없는 공식 문서입니다.",
        "source_type": "official-public",
        "source_organization": "테스트 기관",
        "verified_at": "2026-08-21",
    }
    (tmp_path / "broken.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )

    result = load_knowledge_directory(tmp_path)

    assert result.loaded_files == 0
    assert result.skipped_files == 1


def test_excludes_document_that_requires_review(tmp_path) -> None:
    write_document(
        tmp_path / "auto.json",
        "KB-AUTO",
        "자동이체 지침",
        ["자동이체", "조회"],
    )
    payload = json.loads((tmp_path / "auto.json").read_text(encoding="utf-8"))
    payload["review_status"] = "Review Required"
    (tmp_path / "auto.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )

    documents = load_knowledge_directory(tmp_path).documents

    assert search_knowledge("자동이체 조회", documents) == []
