from dataclasses import dataclass

from .models import Consultation, ConsultationStatus, RiskLevel


@dataclass(frozen=True)
class RiskRule:
    rule_id: str
    level: RiskLevel
    keywords: tuple[str, ...]
    reason: str


# 위에서부터 먼저 일치하는 규칙을 사용한다. 더 위험한 규칙이 항상 우선이다.
RISK_RULES = (
    RiskRule(
        rule_id="RISK-CRITICAL-001",
        level=RiskLevel.CRITICAL,
        keywords=("보이스피싱", "명의도용", "지급정지", "의심거래", "사기 피해"),
        reason="금융사고 또는 사기 피해 가능성이 있는 표현이 감지되었습니다.",
    ),
    RiskRule(
        rule_id="RISK-HIGH-001",
        level=RiskLevel.HIGH,
        keywords=("해외송금", "대출 승인", "연체", "압류", "신용점수"),
        reason="금융 결과에 큰 영향을 줄 수 있는 고위험 업무 표현이 감지되었습니다.",
    ),
    RiskRule(
        rule_id="RISK-MEDIUM-001",
        level=RiskLevel.MEDIUM,
        keywords=("분실", "결제 취소", "환불", "오류", "수수료"),
        reason="추가 거래정보 확인이 필요한 표현이 감지되었습니다.",
    ),
    RiskRule(
        rule_id="RISK-LOW-001",
        level=RiskLevel.LOW,
        keywords=("조회", "확인", "어디서", "만기", "변경"),
        reason="일반 조회·확인 성격의 표현이 감지되었습니다.",
    ),
)


def assess_risk(consultation: Consultation) -> Consultation:
    """미분류 상담에 설명 가능한 키워드 규칙을 적용한다."""
    if consultation.risk != RiskLevel.UNKNOWN:
        return consultation

    text = " ".join(
        [consultation.topic, consultation.summary, consultation.question, consultation.intent]
    ).casefold()

    for rule in RISK_RULES:
        matched = [keyword for keyword in rule.keywords if keyword.casefold() in text]
        if not matched:
            continue

        if rule.level in {RiskLevel.CRITICAL, RiskLevel.HIGH}:
            status = ConsultationStatus.ESCALATED
            restriction = (
                f"{rule.level.value} 상담은 일반 승인을 제한하고 관리자 검토가 필요합니다."
            )
        elif rule.level == RiskLevel.MEDIUM:
            status = ConsultationStatus.NEEDS_INFO
            restriction = "거래정보를 추가로 확인한 뒤 답변을 검토해야 합니다."
        else:
            status = ConsultationStatus.READY
            restriction = None

        return consultation.model_copy(
            update={
                "risk": rule.level,
                "status": status,
                "risk_reasons": [rule.reason, f"일치 키워드: {', '.join(matched)}"],
                "rule_ids": [rule.rule_id],
                "restriction_reason": restriction,
            }
        )

    return consultation.model_copy(
        update={
            "risk_reasons": ["현재 규칙과 일치하지 않아 사람의 판단이 필요합니다."],
            "rule_ids": ["RISK-UNKNOWN-001"],
        }
    )

