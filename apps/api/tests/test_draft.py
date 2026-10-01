from app.draft import generate_grounded_draft, generate_llm_grounded_draft
from app.llm import LLMGenerationError, LLMTextResponse
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


class SuccessfulLLM:
    model = "gemini-test"
    configured = True

    def __init__(self) -> None:
        self.prompt = ""

    def generate(self, system_instruction: str, prompt: str) -> LLMTextResponse:
        self.prompt = prompt
        return LLMTextResponse(
            text="자동이체 조회 경로를 확인해 안내드리겠습니다.",
            model=self.model,
            latency_ms=123,
        )


class MissingKeyLLM:
    model = "gemini-test"
    configured = False

    def generate(self, system_instruction: str, prompt: str) -> LLMTextResponse:
        raise AssertionError("API 키가 없으면 호출하면 안 됩니다.")


class FailingLLM:
    model = "gemini-test"
    configured = True

    def generate(self, system_instruction: str, prompt: str) -> LLMTextResponse:
        raise LLMGenerationError("테스트 API 오류")


def test_generates_llm_draft_from_verified_evidence_and_masks_pii() -> None:
    client = SuccessfulLLM()
    item = consultation(evidence=[sample_evidence()]).model_copy(
        update={"question": "010-1234-5678로 자동이체 조회를 요청합니다."}
    )

    result = generate_llm_grounded_draft(item, client)

    assert result.draft_engine == "gemini-grounded-rag-v1"
    assert result.draft_model == "gemini-test"
    assert result.draft_latency_ms == 123
    assert result.draft_source_ids == ["KB-AUTO-001"]
    assert "KB-AUTO-001" in (result.draft or "")
    assert "010-1234-5678" not in client.prompt
    assert "[전화번호]" in client.prompt


def test_uses_template_without_api_key() -> None:
    result = generate_llm_grounded_draft(
        consultation(evidence=[sample_evidence()]),
        MissingKeyLLM(),
    )

    assert result.draft_generated is True
    assert result.draft_engine == "grounded-template-fallback-v1"
    assert "GEMINI_API_KEY" in (result.draft_fallback_reason or "")


def test_uses_template_when_llm_call_fails() -> None:
    result = generate_llm_grounded_draft(
        consultation(evidence=[sample_evidence()]),
        FailingLLM(),
    )

    assert result.draft_generated is True
    assert result.draft_engine == "grounded-template-fallback-v1"
    assert result.draft_fallback_reason == "테스트 API 오류"


def test_llm_uses_only_top_ranked_evidence() -> None:
    client = SuccessfulLLM()
    unrelated = Evidence(
        document_id="KB-LOAN-ARREARS-001",
        title="연체 안내",
        section="연체",
        effective_date="2024-10-17",
        source_type="official-public",
        source_organization="금융위원회",
        source_url="https://example.com/arrears",
        verified_at="2026-08-24",
        excerpt="연체 채무조정 기준입니다.",
    )
    primary = sample_evidence().model_copy(
        update={
            "document_id": "KB-LOAN-001",
            "title": "중도상환 안내",
            "excerpt": "중도상환 수수료 기준입니다.",
        }
    )

    result = generate_llm_grounded_draft(
        consultation(evidence=[primary, unrelated]),
        client,
    )

    assert result.draft_source_ids == ["KB-LOAN-001"]
    assert "KB-LOAN-001" in client.prompt
    assert "KB-LOAN-ARREARS-001" not in client.prompt
