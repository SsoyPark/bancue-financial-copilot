"""생성 답변을 전송 전에 점검하는 설명 가능한 품질 가드레일."""

from __future__ import annotations

import re
from datetime import datetime, timezone

from .models import Consultation, DraftQualityCheck, DraftQualityReport, RiskLevel
from .pii import mask_text


NUMBER_PATTERN = re.compile(r"\d+(?:[.,]\d+)*(?:%|년|월|일|원|만원|억원|회|시간|분)?")


def _check(check_id: str, label: str, passed: bool, detail: str) -> DraftQualityCheck:
    return DraftQualityCheck(
        check_id=check_id,
        label=label,
        passed=passed,
        detail=detail,
    )


def evaluate_draft_quality(consultation: Consultation) -> DraftQualityReport:
    draft = (consultation.draft or "").strip()
    evidence_ids = {item.document_id for item in consultation.evidence if item.document_id}
    source_ids = set(consultation.draft_source_ids)
    traceable = bool(source_ids) and source_ids.issubset(evidence_ids)

    pii_result = mask_text(draft)
    pii_safe = not pii_result.detected_types
    reviewer_notice = "상담사 검토" in draft or "관리자 검토" in draft

    knowledge_text = " ".join(
        " ".join([item.title, item.section, item.excerpt or "", item.effective_date])
        for item in consultation.evidence
        if item.document_id in source_ids
    )
    answer_body = draft.split("※ 사용 근거:", 1)[0]
    numeric_claims = set(NUMBER_PATTERN.findall(answer_body))
    unsupported_numbers = sorted(
        token for token in numeric_claims if token not in knowledge_text
    )
    numeric_grounded = not unsupported_numbers

    high_risk_notice = (
        consultation.risk not in {RiskLevel.CRITICAL, RiskLevel.HIGH}
        or "관리자" in draft
        or consultation.status.value == "Escalated"
    )
    complete = len(draft) >= 40 and draft[-1] in {".", "요", "다", ")"}

    checks = [
        _check(
            "QUALITY-EVIDENCE-001",
            "근거 추적",
            traceable,
            "사용 근거가 검색된 문서와 일치합니다."
            if traceable
            else "사용 근거가 없거나 검색 결과와 일치하지 않습니다.",
        ),
        _check(
            "QUALITY-PII-001",
            "개인정보 비노출",
            pii_safe,
            "초안에서 개인정보 패턴이 감지되지 않았습니다."
            if pii_safe
            else f"초안에서 {', '.join(pii_result.detected_types)} 패턴이 감지되었습니다.",
        ),
        _check(
            "QUALITY-NUMBER-001",
            "수치 근거",
            numeric_grounded,
            "초안의 수치가 연결 근거 안에서 확인됩니다."
            if numeric_grounded
            else f"근거에서 확인되지 않은 수치: {', '.join(unsupported_numbers)}",
        ),
        _check(
            "QUALITY-REVIEW-001",
            "사람 검토 안내",
            reviewer_notice,
            "상담사 검토 안내가 포함되었습니다."
            if reviewer_notice
            else "상담사 검토 안내가 필요합니다.",
        ),
        _check(
            "QUALITY-RISK-001",
            "고위험 처리",
            high_risk_notice,
            "위험도에 맞는 검토·이관 조건을 충족합니다."
            if high_risk_notice
            else "고위험 상담의 관리자 검토 안내가 필요합니다.",
        ),
        _check(
            "QUALITY-COMPLETE-001",
            "응답 완결성",
            complete,
            "답변이 완결된 형식입니다."
            if complete
            else "답변이 너무 짧거나 문장이 끝나지 않았습니다.",
        ),
    ]
    passed_count = sum(item.passed for item in checks)
    score = round(passed_count / len(checks) * 100)
    return DraftQualityReport(
        status="Passed" if passed_count == len(checks) else "Review Required",
        score=score,
        checks=checks,
        evaluated_at=datetime.now(timezone.utc).isoformat(),
    )
