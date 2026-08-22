import pytest

from app.models import (
    ActionRequest,
    Consultation,
    ConsultationStatus,
    RiskLevel,
    WorkflowAction,
)
from app.workflow import WorkflowError, apply_action


def consultation(
    risk: RiskLevel = RiskLevel.LOW,
    status: ConsultationStatus = ConsultationStatus.READY,
) -> Consultation:
    return Consultation(
        id="workflow-test-1",
        customer="고객",
        topic="자동이체",
        summary="자동이체 조회",
        question="자동이체를 어디서 조회하나요?",
        risk=risk,
        status=status,
        waiting_time="00:00",
        intent="자동이체 조회",
        required_checks=["본인확인", "근거 문서 유효일 확인"],
        draft="근거 기반 초안",
        draft_generated=True,
    )


def request(action: WorkflowAction, checks: list[str] | None = None) -> ActionRequest:
    return ActionRequest(
        action=action,
        actor="테스트 상담사",
        note="테스트 처리",
        confirmed_checks=checks or [],
    )


def test_approve_completes_consultation_and_records_history() -> None:
    result = apply_action(
        consultation(),
        request(WorkflowAction.APPROVE, ["본인확인", "근거 문서 유효일 확인"]),
        created_at="2026-08-21T00:00:00+00:00",
    )
    assert result.status == ConsultationStatus.COMPLETED
    assert result.action_history[0].action == WorkflowAction.APPROVE
    assert result.action_history[0].actor == "테스트 상담사"


def test_approve_requires_all_checks() -> None:
    with pytest.raises(WorkflowError, match="필수 확인 항목"):
        apply_action(
            consultation(),
            request(WorkflowAction.APPROVE, ["본인확인"]),
        )


def test_high_risk_cannot_be_approved() -> None:
    with pytest.raises(WorkflowError, match="관리자 이관"):
        apply_action(
            consultation(risk=RiskLevel.HIGH),
            request(WorkflowAction.APPROVE, ["본인확인", "근거 문서 유효일 확인"]),
        )


def test_reject_and_escalate_change_status() -> None:
    rejected = apply_action(consultation(), request(WorkflowAction.REJECT))
    escalated = apply_action(consultation(), request(WorkflowAction.ESCALATE))
    assert rejected.status == ConsultationStatus.NEEDS_INFO
    assert escalated.status == ConsultationStatus.ESCALATED
