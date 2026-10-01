from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["data_source"] in {"aihub-json", "built-in-seed"}
    assert response.json()["consultation_count"] >= 1
    assert response.json()["risk_engine"] == "rules-v1"
    assert response.json()["pii_masker"] == "regex-v1"
    assert response.json()["retrieval_engine"] == "keyword-score-v3-confidence-gate"
    assert response.json()["query_expansion"] == "rules-v1"
    assert response.json()["retrieval_minimum_score"] == 8
    assert response.json()["explainability_engine"] == "retrieval-trace-v1"
    assert response.json()["knowledge_count"] == 9
    assert response.json()["official_knowledge_count"] == 9
    assert response.json()["synthetic_knowledge_count"] == 0
    assert response.json()["knowledge_review_required_count"] == 1
    assert response.json()["draft_engine"] == "grounded-template-v1"
    assert response.json()["llm_engine"] == "gemini-rest-rag-v1"
    assert response.json()["llm_model"]
    assert response.json()["llm_configured"] in {0, 1}
    assert response.json()["analysis_engine"] == "gemini-structured-triage-v1"
    assert response.json()["quality_guardrail"] == "deterministic-guardrail-v1"
    assert response.json()["workflow_engine"] == "sqlite-v1"
    assert response.json()["persisted_state_count"] >= 0
    assert response.json()["feedback_engine"] == "sqlite-score-masked-v2"
    assert response.json()["feedback_count"] >= 0
    assert response.json()["evaluation_case_count"] == 15


def test_consultation_list_and_detail() -> None:
    response = client.get("/api/consultations")
    assert response.status_code == 200
    assert response.json()["total"] >= 1

    consultation_id = response.json()["items"][0]["id"]
    detail = client.get(f"/api/consultations/{consultation_id}")
    assert detail.status_code == 200
    assert detail.json()["id"] == consultation_id
    assert "pii_masked" in detail.json()
    assert "pii_types" in detail.json()
    assert detail.json()["draft_generated"] is True
    assert detail.json()["draft_source_ids"]
    assert detail.json()["retrieval_trace"]["decision"] == "grounded"


def test_knowledge_search() -> None:
    response = client.get("/api/knowledge/search", params={"q": "자동이체 조회"})
    assert response.status_code == 200
    assert response.json()[0]["document_id"] == "KB-AUTO-001"
    assert "자동이체" in response.json()[0]["matched_terms"]
    assert response.json()[0]["source_type"] == "official-public"
    assert response.json()[0]["source_organization"] == "금융결제원"
    assert response.json()[0]["source_url"].startswith("https://")


def test_knowledge_source_registry_api() -> None:
    response = client.get("/api/knowledge/sources")

    assert response.status_code == 200
    assert len(response.json()) == 9
    assert sum(
        item["review_status"] == "Review Required" for item in response.json()
    ) == 1
    assert all(item["source_type"] == "official-public" for item in response.json())
    loan_extension = next(
        item
        for item in response.json()
        if item["document_id"] == "KB-LOAN-EXT-001"
    )
    assert "우리은행" in loan_extension["applicability_scope"]


def test_llm_draft_endpoint_uses_safe_fallback_without_api_key(monkeypatch) -> None:
    from app import main

    class MissingKeyClient:
        model = "gemini-test"
        configured = False

        def generate(self, system_instruction: str, prompt: str):
            raise AssertionError("API 키가 없으면 호출하면 안 됩니다.")

    monkeypatch.setattr(main, "GEMINI_CLIENT", MissingKeyClient())
    consultation_id = client.get("/api/consultations").json()["items"][0]["id"]

    response = client.post(f"/api/consultations/{consultation_id}/draft/llm")

    assert response.status_code == 200
    assert response.json()["draft_engine"] == "grounded-template-fallback-v1"
    assert response.json()["draft_generated"] is True
    assert response.json()["draft_source_ids"]


def test_llm_analysis_endpoint_uses_safe_fallback_without_api_key(monkeypatch) -> None:
    from app import main

    class MissingKeyClient:
        model = "gemini-test"
        configured = False

        def generate(self, system_instruction: str, prompt: str):
            raise AssertionError("API 키가 없으면 호출하면 안 됩니다.")

    monkeypatch.setattr(main, "GEMINI_CLIENT", MissingKeyClient())
    consultation_id = client.get("/api/consultations").json()["items"][0]["id"]

    response = client.post(f"/api/consultations/{consultation_id}/analysis/llm")

    assert response.status_code == 200
    assert response.json()["analysis_engine"] == "rules-fallback-v1"
    assert response.json()["analysis_prompt_version"] == "triage-v1"


def test_knowledge_search_abstains_when_confidence_is_low() -> None:
    response = client.get(
        "/api/knowledge/search",
        params={"q": "해외송금 회사에 취업하려면 필요한 자격증"},
    )

    assert response.status_code == 200
    assert response.json() == []


def test_knowledge_explain_api_shows_acceptance_and_abstention() -> None:
    accepted = client.get(
        "/api/knowledge/explain",
        params={"q": "자동이체 조회"},
    )
    abstained = client.get(
        "/api/knowledge/explain",
        params={"q": "해외송금 회사에 취업하려면 어떤 자격증이 필요한가요?"},
    )

    assert accepted.status_code == 200
    assert accepted.json()["decision"] == "grounded"
    assert accepted.json()["candidates"][0]["accepted"] is True
    assert abstained.status_code == 200
    assert abstained.json()["decision"] == "abstained"
    assert abstained.json()["candidates"][0]["accepted"] is False


def test_consultation_feedback_masks_note_and_updates_summary() -> None:
    consultation_id = "21-1_bk_03_000001_001"
    response = client.post(
        f"/api/consultations/{consultation_id}/feedback",
        json={
            "intent_score": 2,
            "draft_score": 3,
            "issue_types": ["wrong_evidence"],
            "note": "sample@example.com으로 잘못 안내될 수 있습니다.",
            "actor": "박소영 상담사",
        },
    )

    assert response.status_code == 200
    assert response.json()["note"] == "[이메일]으로 잘못 안내될 수 있습니다."
    assert response.json()["rating"] == "needs_improvement"
    assert response.json()["intent_score"] == 2
    assert response.json()["draft_score"] == 3
    assert response.json()["pii_masked"] is True
    assert response.json()["pii_types"] == ["이메일"]

    summary = client.get("/api/feedback/summary")
    assert summary.status_code == 200
    assert summary.json()["total"] >= 1
    assert summary.json()["needs_improvement"] >= 1
    assert summary.json()["scored_feedback"] >= 1
    assert summary.json()["average_intent_score"] == 2.0
    assert summary.json()["average_draft_score"] == 3.0
    assert summary.json()["issue_counts"]["wrong_evidence"] >= 1


def test_feedback_rejects_unknown_consultation() -> None:
    response = client.post(
        "/api/consultations/unknown-id/feedback",
        json={"intent_score": 5, "draft_score": 5},
    )

    assert response.status_code == 404


def test_low_feedback_score_requires_issue_type() -> None:
    response = client.post(
        "/api/consultations/21-1_bk_03_000001_001/feedback",
        json={"intent_score": 3, "draft_score": 5, "issue_types": []},
    )

    assert response.status_code == 422


def test_retrieval_evaluation_api() -> None:
    response = client.get("/api/evaluation/retrieval")
    assert response.status_code == 200
    assert response.json()["total_cases"] == 15
    assert response.json()["mode"] == "query-expansion-confidence-v1"
    assert response.json()["recall_at_1"] == 1.0
    assert response.json()["no_answer_accuracy"] == 1.0
    assert response.json()["overall_accuracy"] == 1.0
    assert response.json()["failed_cases"] == 0


def test_retrieval_comparison_api() -> None:
    response = client.get("/api/evaluation/retrieval/comparison")

    assert response.status_code == 200
    assert response.json()["baseline"]["recall_at_1"] == 0.9
    assert response.json()["improved"]["recall_at_1"] == 1.0
    assert response.json()["recall_at_1_delta"] == 0.1
    assert response.json()["baseline"]["overall_accuracy"] == 0.6
    assert response.json()["improved"]["overall_accuracy"] == 1.0
    assert response.json()["no_answer_accuracy_delta"] == 1.0


def test_consultation_action_requires_checks_then_approves() -> None:
    consultation_id = "21-1_bk_03_000001_001"
    detail = client.get(f"/api/consultations/{consultation_id}").json()

    blocked = client.post(
        f"/api/consultations/{consultation_id}/actions",
        json={"action": "approve", "confirmed_checks": []},
    )
    assert blocked.status_code == 409

    approved = client.post(
        f"/api/consultations/{consultation_id}/actions",
        json={
            "action": "approve",
            "actor": "박소영 상담사",
            "confirmed_checks": detail["required_checks"],
        },
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "Completed"
    assert approved.json()["action_history"][-1]["action"] == "approve"
