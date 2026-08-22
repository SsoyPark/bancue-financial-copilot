from .models import Consultation, RiskLevel


OFFICIAL_GENERATED_NOTICE = (
    "공식 공개자료 요약 기반 템플릿 초안입니다. 원문과 고객 계약 조건 확인 후 안내하세요."
)
SYNTHETIC_GENERATED_NOTICE = (
    "합성 테스트 문서 기반 템플릿 초안입니다. 상담사 검토 전 전송할 수 없습니다."
)
MISSING_EVIDENCE_NOTICE = "연결된 근거 문서가 없어 답변 초안을 생성하지 않았습니다."


def generate_grounded_draft(consultation: Consultation) -> Consultation:
    """상위 근거의 내용과 확인 항목만 사용해 설명 가능한 초안을 만든다."""
    primary = next(
        (evidence for evidence in consultation.evidence if evidence.excerpt),
        None,
    )
    if primary is None:
        return consultation.model_copy(
            update={
                "draft": None,
                "draft_generated": False,
                "draft_source_ids": [],
                "draft_notice": MISSING_EVIDENCE_NOTICE,
            }
        )

    lines = [
        "문의 내용을 확인했습니다.",
        (
            f"현재 연결된 근거 자료 「{primary.title}」의 "
            f"「{primary.section}」에 따르면, {primary.excerpt}"
        ),
    ]

    checks = consultation.required_checks[:3]
    if checks:
        lines.append(f"정확한 안내를 위해 다음 항목을 확인하겠습니다: {', '.join(checks)}.")

    if consultation.risk in {RiskLevel.CRITICAL, RiskLevel.HIGH}:
        lines.append("해당 문의는 관리자 검토 후 최종 안내됩니다.")

    official_source = primary.source_type == "official-public"
    if official_source:
        lines.append(
            "※ 공식 공개자료를 요약한 포트폴리오용 초안입니다. "
            "실제 안내 전 원문과 고객별 계약 조건을 확인해야 합니다."
        )
    else:
        lines.append("※ 현재 초안은 합성 테스트 문서를 사용한 포트폴리오용 결과입니다.")
    source_ids = [
        evidence.document_id
        for evidence in consultation.evidence
        if evidence.document_id
    ]

    return consultation.model_copy(
        update={
            "draft": "\n\n".join(lines),
            "draft_generated": True,
            "draft_source_ids": source_ids,
            "draft_notice": (
                OFFICIAL_GENERATED_NOTICE
                if official_source
                else SYNTHETIC_GENERATED_NOTICE
            ),
        }
    )
