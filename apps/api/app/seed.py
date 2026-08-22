from .models import Consultation, ConsultationStatus, Evidence, RiskLevel


CONSULTATIONS = [
    Consultation(
        id="BK-240819-031",
        customer="김○진",
        topic="해외송금",
        summary="해외송금 보류 및 본인확인 문의",
        question="해외송금이 보류됐는데 오늘 안에 처리할 수 있나요?",
        risk=RiskLevel.CRITICAL,
        status=ConsultationStatus.ESCALATED,
        waiting_time="14:32",
        intent="해외송금 보류 해제 문의",
        required_checks=[
            "본인확인 완료 여부",
            "제재·이상거래 탐지 사유",
            "수취 국가 및 금액",
            "처리 가능 시점",
        ],
        evidence=[
            Evidence(
                title="해외송금 업무지침 v3.2",
                section="제4조 본인확인 및 거래 보류 절차",
                effective_date="2026-07-31",
            )
        ],
        draft="고객님의 해외송금은 추가 본인확인이 필요한 상태입니다. 보류 사유 확인 후 처리 가능 시점을 안내드리겠습니다.",
        restriction_reason="Critical 상담은 승인 없이 답변을 전송할 수 없습니다.",
    ),
    Consultation(
        id="BK-240819-027",
        customer="이○현",
        topic="대출",
        summary="대출 중도상환 수수료 이의",
        question="중도상환 수수료가 예상보다 많이 나온 이유가 궁금합니다.",
        risk=RiskLevel.HIGH,
        status=ConsultationStatus.READY,
        waiting_time="11:05",
        intent="중도상환 수수료 산정 기준 확인",
        required_checks=["대출 상품", "약정일", "상환 예정 금액"],
        evidence=[
            Evidence(
                title="가계대출 수수료 안내 v2.1",
                section="중도상환해약금 산정 기준",
                effective_date="2026-06-01",
            )
        ],
        draft="정확한 수수료는 고객님의 약정 조건과 상환 예정 금액을 확인한 뒤 안내드릴 수 있습니다.",
        restriction_reason="High 상담은 관리자 검토 후 처리할 수 있습니다.",
    ),
    Consultation(
        id="BK-240819-022",
        customer="박○영",
        topic="카드",
        summary="카드 분실 후 결제 취소 문의",
        question="카드를 잃어버렸는데 방금 결제된 건을 취소할 수 있나요?",
        risk=RiskLevel.MEDIUM,
        status=ConsultationStatus.NEEDS_INFO,
        waiting_time="08:41",
        intent="분실 카드 승인 건 확인",
        required_checks=["분실 신고 여부", "승인 시각", "가맹점명"],
        evidence=[],
        draft=None,
        restriction_reason="결제 정보를 추가로 확인해야 합니다.",
    ),
    Consultation(
        id="BK-240819-019",
        customer="정○수",
        topic="예금",
        summary="예금 만기일과 자동연장 문의",
        question="예금 만기일이 지나면 자동으로 연장되나요?",
        risk=RiskLevel.LOW,
        status=ConsultationStatus.READY,
        waiting_time="05:18",
        intent="예금 자동연장 조건 확인",
        required_checks=["상품명", "만기일"],
        evidence=[
            Evidence(
                title="예금 상품설명서",
                section="만기 처리 방법",
                effective_date="2026-01-01",
            )
        ],
        draft="상품별 만기 처리 방식이 다르므로 가입하신 상품명과 만기일을 확인한 뒤 안내드리겠습니다.",
    ),
]

