from datetime import datetime, timezone

from .models import (
    ActionRecord,
    ActionRequest,
    Consultation,
    ConsultationStatus,
    RiskLevel,
    WorkflowAction,
)


class WorkflowError(ValueError):
    pass


def apply_action(
    consultation: Consultation,
    request: ActionRequest,
    created_at: str | None = None,
) -> Consultation:
    """상담 처리 규칙을 검사하고 상태와 이력을 갱신한다."""
    if consultation.status == ConsultationStatus.COMPLETED:
        raise WorkflowError("이미 완료된 상담은 다시 처리할 수 없습니다.")

    if request.action == WorkflowAction.APPROVE:
        if consultation.risk in {RiskLevel.CRITICAL, RiskLevel.HIGH}:
            raise WorkflowError("Critical 또는 High 상담은 승인할 수 없으며 관리자 이관이 필요합니다.")
        if not consultation.draft_generated or not consultation.draft:
            raise WorkflowError("근거 기반 답변 초안이 없어 승인할 수 없습니다.")
        if (
            consultation.draft_quality is not None
            and consultation.draft_quality.status != "Passed"
        ):
            raise WorkflowError("답변 품질 가드레일을 통과해야 승인할 수 있습니다.")

        confirmed = set(request.confirmed_checks)
        missing_checks = [
            item for item in consultation.required_checks if item not in confirmed
        ]
        if missing_checks:
            raise WorkflowError(
                f"필수 확인 항목을 모두 완료해야 합니다: {', '.join(missing_checks)}"
            )
        next_status = ConsultationStatus.COMPLETED
        restriction_reason = None
    elif request.action == WorkflowAction.REJECT:
        next_status = ConsultationStatus.NEEDS_INFO
        restriction_reason = "상담사가 답변 초안을 반려하여 추가 확인이 필요합니다."
    else:
        next_status = ConsultationStatus.ESCALATED
        restriction_reason = consultation.restriction_reason or (
            "상담사가 관리자 검토를 요청했습니다."
        )

    record = ActionRecord(
        action=request.action,
        actor=request.actor,
        note=request.note,
        confirmed_checks=request.confirmed_checks,
        created_at=created_at or datetime.now(timezone.utc).isoformat(),
    )
    return consultation.model_copy(
        update={
            "status": next_status,
            "restriction_reason": restriction_reason,
            "action_history": [*consultation.action_history, record],
        }
    )
