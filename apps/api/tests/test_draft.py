from app.draft import generate_grounded_draft
from app.models import Consultation, ConsultationStatus, Evidence, RiskLevel


def consultation(
    risk: RiskLevel = RiskLevel.LOW,
    evidence: list[Evidence] | None = None,
) -> Consultation:
    return Consultation(
        id="draft-test-1",
        customer="고객",
        topic="자동이체",
        summary="자동이체 조회",
        question="자동이체를 어디서 조회하나요?",
        risk=risk,
        status=ConsultationStatus.READY,
        waiting_time="00:00",
        intent="자동이체 조회",
        required_checks=["본인확인", "처리 가능 시간"],
        evidence=evidence or [],
        draft="근거 없이 원천 데이터에 있던 답변",
    )


def sample_evidence() -> Evidence:
    return Evidence(
        document_id="KB-AUTO-001",
        title="자동이체 업무처리 지침",
        section="제3조 조회 절차",
        effective_date="2026-04-01",
        source_type="official-public",
        source_organization="금융결제원",
        source_url="https://www.payinfo.or.kr/gatePay.html",
        verified_at="2026-08-21",
        summary_method="official-source-summary",
        excerpt="자동이체 등록 내역은 본인확인 후 조회할 수 있습니다.",
    )


def test_generates_draft_from_evidence() -> None:
    result = generate_grounded_draft(consultation(evidence=[sample_evidence()]))

    assert result.draft_generated is True
    assert "자동이체 등록 내역" in (result.draft or "")
    assert "본인확인" in (result.draft or "")
    assert result.draft_source_ids == ["KB-AUTO-001"]
    assert "공식 공개자료 요약" in (result.draft_notice or "")
    assert "고객별 계약 조건" in (result.draft or "")


def test_blocks_draft_without_evidence() -> None:
    result = generate_grounded_draft(consultation())

    assert result.draft is None
    assert result.draft_generated is False
    assert result.draft_source_ids == []
    assert "근거 문서가 없어" in (result.draft_notice or "")


def test_high_risk_draft_requires_manager_review() -> None:
    result = generate_grounded_draft(
        consultation(risk=RiskLevel.CRITICAL, evidence=[sample_evidence()])
    )
    assert "관리자 검토 후" in (result.draft or "")
