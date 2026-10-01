from app.models import Consultation, ConsultationStatus, Evidence, RiskLevel
from app.quality import evaluate_draft_quality


def consultation(draft: str, *, risk: RiskLevel = RiskLevel.LOW) -> Consultation:
    return Consultation(
        id="quality-test-1",
        customer="고객",
        topic="자동이체",
        summary="자동이체 조회",
        question="자동이체를 조회하고 싶어요.",
        risk=risk,
        status=(
            ConsultationStatus.ESCALATED
            if risk in {RiskLevel.HIGH, RiskLevel.CRITICAL}
            else ConsultationStatus.READY
        ),
        waiting_time="00:00",
        intent="자동이체 조회",
        evidence=[
            Evidence(
                document_id="KB-AUTO-001",
                title="자동이체 안내",
                section="조회",
                effective_date="2026-01-01",
                excerpt="본인확인 후 자동이체 내역을 조회할 수 있습니다.",
            )
        ],
        draft=draft,
        draft_generated=True,
        draft_source_ids=["KB-AUTO-001"],
    )


def test_quality_guardrail_passes_grounded_safe_draft() -> None:
    report = evaluate_draft_quality(
        consultation(
            "본인확인 후 자동이체 내역을 조회할 수 있습니다. "
            "※ 상담사 검토 후 고객에게 안내하세요."
        )
    )

    assert report.status == "Passed"
    assert report.score == 100
    assert all(item.passed for item in report.checks)


def test_quality_guardrail_flags_pii_and_unsupported_number() -> None:
    report = evaluate_draft_quality(
        consultation(
            "고객님의 번호 010-1234-5678로 30만원이 확인됩니다. "
            "※ 상담사 검토 후 고객에게 안내하세요."
        )
    )

    failed_ids = {item.check_id for item in report.checks if not item.passed}
    assert report.status == "Review Required"
    assert "QUALITY-PII-001" in failed_ids
    assert "QUALITY-NUMBER-001" in failed_ids


def test_quality_guardrail_requires_manager_handling_for_high_risk() -> None:
    item = consultation(
        "본인확인 후 자동이체 내역을 조회할 수 있습니다. "
        "※ 상담사 검토 후 고객에게 안내하세요.",
        risk=RiskLevel.HIGH,
    ).model_copy(update={"status": ConsultationStatus.READY})

    report = evaluate_draft_quality(item)

    risk_check = next(check for check in report.checks if check.check_id == "QUALITY-RISK-001")
    assert risk_check.passed is False
