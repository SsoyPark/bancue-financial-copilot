from app.database import WorkflowStateStore
from app.models import (
    ActionRecord,
    Consultation,
    ConsultationStatus,
    FeedbackIssue,
    FeedbackRating,
    FeedbackRecord,
    RiskLevel,
    WorkflowAction,
)


def consultation() -> Consultation:
    return Consultation(
        id="database-test-1",
        customer="고객",
        topic="자동이체",
        summary="자동이체 조회",
        question="자동이체를 어디서 조회하나요?",
        risk=RiskLevel.LOW,
        status=ConsultationStatus.READY,
        waiting_time="00:00",
        intent="자동이체 조회",
        action_history=[],
    )


def completed_consultation() -> Consultation:
    return consultation().model_copy(
        update={
            "status": ConsultationStatus.COMPLETED,
            "restriction_reason": None,
            "action_history": [
                ActionRecord(
                    action=WorkflowAction.APPROVE,
                    actor="테스트 상담사",
                    note="승인 테스트",
                    confirmed_checks=["본인확인"],
                    created_at="2026-08-21T00:00:00+00:00",
                )
            ],
        }
    )


def test_save_and_restore_across_store_instances(tmp_path) -> None:
    db_path = tmp_path / "state.db"
    first_store = WorkflowStateStore(db_path)
    first_store.save(completed_consultation())

    restarted_store = WorkflowStateStore(db_path)
    restored = restarted_store.restore(consultation())

    assert restored.status == ConsultationStatus.COMPLETED
    assert restored.action_history[0].action == WorkflowAction.APPROVE
    assert restored.action_history[0].actor == "테스트 상담사"
    assert restarted_store.count() == 1


def test_restore_returns_original_when_state_is_missing(tmp_path) -> None:
    store = WorkflowStateStore(tmp_path / "state.db")
    original = consultation()
    assert store.restore(original) == original


def test_save_updates_existing_state(tmp_path) -> None:
    store = WorkflowStateStore(tmp_path / "state.db")
    store.save(completed_consultation())
    changed = completed_consultation().model_copy(
        update={"status": ConsultationStatus.NEEDS_INFO}
    )
    store.save(changed)

    assert store.count() == 1
    assert store.restore(consultation()).status == ConsultationStatus.NEEDS_INFO


def test_saves_and_summarizes_feedback(tmp_path) -> None:
    store = WorkflowStateStore(tmp_path / "state.db")
    created = store.save_feedback(
        FeedbackRecord(
            consultation_id="database-test-1",
            rating=FeedbackRating.NEEDS_IMPROVEMENT,
            intent_score=2,
            draft_score=3,
            issue_types=[FeedbackIssue.WRONG_EVIDENCE],
            note="근거 문서를 다시 확인해 주세요.",
            actor="테스트 상담사",
            created_at="2026-08-21T00:00:00+00:00",
        )
    )
    store.save_feedback(
        FeedbackRecord(
            consultation_id="database-test-2",
            rating=FeedbackRating.HELPFUL,
            intent_score=5,
            draft_score=4,
            actor="테스트 상담사",
            created_at="2026-08-21T00:01:00+00:00",
        )
    )

    summary = store.feedback_summary()

    assert created.id == 1
    assert store.feedback_count() == 2
    assert summary.total == 2
    assert summary.helpful == 1
    assert summary.needs_improvement == 1
    assert summary.helpful_rate == 0.5
    assert summary.scored_feedback == 2
    assert summary.average_intent_score == 3.5
    assert summary.average_draft_score == 3.5
    assert summary.issue_counts["wrong_evidence"] == 1
    assert summary.recent[0].consultation_id == "database-test-2"
    assert summary.recent[0].intent_score == 5
