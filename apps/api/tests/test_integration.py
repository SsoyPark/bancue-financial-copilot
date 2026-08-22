from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_standard_consultation_to_feedback_flow() -> None:
    consultation_id = "21-1_bk_03_000002_001"

    listed = client.get("/api/consultations")
    assert listed.status_code == 200
    assert any(item["id"] == consultation_id for item in listed.json()["items"])

    detail = client.get(f"/api/consultations/{consultation_id}")
    assert detail.status_code == 200
    consultation = detail.json()
    assert consultation["risk"] == "Low"
    assert consultation["retrieval_trace"]["decision"] == "grounded"
    assert consultation["evidence"]
    assert consultation["draft_generated"] is True
    assert consultation["draft_source_ids"]

    feedback = client.post(
        f"/api/consultations/{consultation_id}/feedback",
        json={
            "intent_score": 5,
            "draft_score": 4,
            "note": "통합 테스트 피드백",
            "actor": "박소영 상담사",
        },
    )
    assert feedback.status_code == 200
    assert feedback.json()["rating"] == "helpful"

    summary = client.get("/api/feedback/summary")
    assert summary.status_code == 200
    assert any(
        item["consultation_id"] == consultation_id
        and item["intent_score"] == 5
        and item["draft_score"] == 4
        for item in summary.json()["recent"]
    )


def test_high_risk_consultation_blocks_approval_then_escalates() -> None:
    consultation_id = "21-1_bk_03_000005_001"
    detail = client.get(f"/api/consultations/{consultation_id}")

    assert detail.status_code == 200
    assert detail.json()["risk"] == "Critical"

    blocked = client.post(
        f"/api/consultations/{consultation_id}/actions",
        json={
            "action": "approve",
            "confirmed_checks": detail.json()["required_checks"],
        },
    )
    assert blocked.status_code == 409

    escalated = client.post(
        f"/api/consultations/{consultation_id}/actions",
        json={
            "action": "escalate",
            "actor": "박소영 상담사",
            "note": "고위험 통합 테스트",
        },
    )
    assert escalated.status_code == 200
    assert escalated.json()["status"] == "Escalated"
    assert escalated.json()["action_history"][-1]["action"] == "escalate"


def test_retrieval_evaluation_and_abstention_flow() -> None:
    grounded = client.get(
        "/api/knowledge/explain",
        params={"q": "자동이체 조회"},
    )
    abstained = client.get(
        "/api/knowledge/explain",
        params={"q": "해외송금 회사에 취업하려면 어떤 자격증이 필요한가요?"},
    )
    comparison = client.get("/api/evaluation/retrieval/comparison")

    assert grounded.status_code == 200
    assert grounded.json()["decision"] == "grounded"
    assert grounded.json()["candidates"][0]["score"] >= 8
    assert abstained.status_code == 200
    assert abstained.json()["decision"] == "abstained"
    assert abstained.json()["candidates"][0]["score"] < 8
    assert comparison.status_code == 200
    assert comparison.json()["baseline"]["overall_accuracy"] == 0.6
    assert comparison.json()["improved"]["overall_accuracy"] == 1.0
