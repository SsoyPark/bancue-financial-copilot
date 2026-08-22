from app.models import Consultation, ConsultationStatus, RiskLevel
from app.risk import assess_risk


def consultation(question: str) -> Consultation:
    return Consultation(
        id="test-1",
        customer="고객",
        topic="테스트",
        summary=question,
        question=question,
        risk=RiskLevel.UNKNOWN,
        status=ConsultationStatus.RECEIVED,
        waiting_time="00:00",
        intent=question,
    )


def test_critical_rule_has_priority() -> None:
    result = assess_risk(consultation("보이스피싱 피해 계좌를 조회하고 싶어요"))
    assert result.risk == RiskLevel.CRITICAL
    assert result.status == ConsultationStatus.ESCALATED
    assert result.rule_ids == ["RISK-CRITICAL-001"]


def test_low_rule_for_simple_lookup() -> None:
    result = assess_risk(consultation("자동이체를 어디서 조회하나요?"))
    assert result.risk == RiskLevel.LOW
    assert result.status == ConsultationStatus.READY
    assert result.restriction_reason is None


def test_unknown_when_no_rule_matches() -> None:
    result = assess_risk(consultation("새로운 형태의 문의입니다"))
    assert result.risk == RiskLevel.UNKNOWN
    assert result.rule_ids == ["RISK-UNKNOWN-001"]

