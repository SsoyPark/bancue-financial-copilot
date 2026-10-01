from app.ai_analysis import analyze_consultation_with_llm, parse_structured_analysis
from app.llm import LLMTextResponse
from app.models import Consultation, ConsultationStatus, RiskLevel


def consultation() -> Consultation:
    return Consultation(
        id="analysis-test-1",
        customer="고객",
        topic="중도상환",
        summary="수수료 문의",
        question="중도상환수수료가 왜 이렇게 많이 나왔나요? 010-1234-5678",
        risk=RiskLevel.MEDIUM,
        status=ConsultationStatus.NEEDS_INFO,
        waiting_time="00:00",
        intent="중도상환 수수료 확인",
        required_checks=["대출 상품"],
    )


class StructuredLLM:
    model = "gemini-test"
    configured = True

    def __init__(self, risk: str = "Low") -> None:
        self.risk = risk
        self.prompt = ""

    def generate(self, system_instruction: str, prompt: str) -> LLMTextResponse:
        self.prompt = prompt
        return LLMTextResponse(
            text=(
                '{"summary":"중도상환수수료 과다 문의",'
                '"intent":"수수료 산정 기준 확인",'
                f'"risk":"{self.risk}","confidence":0.94,'
                '"required_checks":["계약일","상환 예정일"],'
                '"rationale":["개별 약정 확인 필요"]}'
            ),
            model=self.model,
            latency_ms=88,
        )


class MissingKeyLLM:
    model = "gemini-test"
    configured = False

    def generate(self, system_instruction: str, prompt: str) -> LLMTextResponse:
        raise AssertionError("API 키가 없으면 호출하면 안 됩니다.")


def test_parses_json_code_fence() -> None:
    result = parse_structured_analysis(
        """```json
{"summary":"자동이체 조회","intent":"조회 경로 확인","risk":"Low","confidence":0.8,"required_checks":[],"rationale":[]}
```"""
    )
    assert result.intent == "조회 경로 확인"
    assert result.risk == RiskLevel.LOW


def test_llm_analysis_masks_pii_and_keeps_safer_rule_risk() -> None:
    client = StructuredLLM(risk="Low")
    result = analyze_consultation_with_llm(consultation(), client)

    assert "010-1234-5678" not in client.prompt
    assert "[전화번호]" in client.prompt
    assert result.summary == "중도상환수수료 과다 문의"
    assert result.intent == "수수료 산정 기준 확인"
    assert result.risk == RiskLevel.MEDIUM
    assert result.analysis_confidence == 0.94
    assert result.analysis_engine == "gemini-structured-triage-v1"
    assert result.required_checks[:2] == ["계약일", "상환 예정일"]
    assert "더 높은 기존 위험도" in result.analysis_rationale[-1]


def test_llm_analysis_can_raise_risk_and_escalate() -> None:
    result = analyze_consultation_with_llm(consultation(), StructuredLLM(risk="High"))

    assert result.risk == RiskLevel.HIGH
    assert result.status == ConsultationStatus.ESCALATED
    assert "관리자 검토" in (result.restriction_reason or "")


def test_analysis_falls_back_without_api_key() -> None:
    result = analyze_consultation_with_llm(consultation(), MissingKeyLLM())

    assert result.analysis_engine == "rules-fallback-v1"
    assert result.risk == RiskLevel.MEDIUM
    assert result.analysis_confidence is None
