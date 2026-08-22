from pathlib import Path

from app.evaluation import compare_retrieval, evaluate_retrieval, load_retrieval_cases
from app.knowledge import load_knowledge_directory


API_ROOT = Path(__file__).resolve().parents[1]


def test_loads_retrieval_evaluation_cases() -> None:
    cases = load_retrieval_cases(
        API_ROOT / "data" / "evaluation" / "retrieval_cases.json"
    )
    assert len(cases) == 15
    assert cases[-1].case_id == "NEG-005"
    assert cases[-1].expected_document_ids == []


def test_baseline_retrieval_metrics_expose_keyword_search_limit() -> None:
    cases = load_retrieval_cases(
        API_ROOT / "data" / "evaluation" / "retrieval_cases.json"
    )
    documents = load_knowledge_directory(API_ROOT / "data" / "knowledge").documents
    report = evaluate_retrieval(
        cases,
        documents,
        use_query_expansion=False,
        minimum_score=0,
    )

    assert report.mode == "baseline-keyword-v1"
    assert report.recall_at_1 == 0.9
    assert report.recall_at_3 == 0.9
    assert report.mrr == 0.9
    assert report.passed_cases == 9
    assert report.failed_cases == 6
    assert report.no_answer_accuracy == 0.0
    assert report.overall_accuracy == 0.6
    assert report.false_positive_cases == 5


def test_query_expansion_recovers_indirect_expression() -> None:
    cases = load_retrieval_cases(
        API_ROOT / "data" / "evaluation" / "retrieval_cases.json"
    )
    documents = load_knowledge_directory(API_ROOT / "data" / "knowledge").documents
    report = evaluate_retrieval(cases, documents, use_query_expansion=True)

    assert report.mode == "query-expansion-confidence-v1"
    assert report.recall_at_1 == 1.0
    assert report.recall_at_3 == 1.0
    assert report.mrr == 1.0
    assert report.passed_cases == 15
    assert report.no_answer_accuracy == 1.0
    assert report.overall_accuracy == 1.0
    recovered = next(item for item in report.results if item.case_id == "RET-010")
    assert recovered.hit_rank == 1
    assert recovered.retrieved_document_ids[0] == "KB-AUTO-001"
    assert recovered.added_terms == ["자동이체", "자동납부", "출금계좌", "변경"]
    assert recovered.query_rule_ids == ["QUERY-AUTO-001", "QUERY-AUTO-002"]
    abstentions = [item for item in report.results if item.expected_no_answer]
    assert len(abstentions) == 5
    assert all(item.outcome == "correct-abstention" for item in abstentions)
    assert all(item.retrieved_document_ids == [] for item in abstentions)


def test_comparison_reports_metric_delta() -> None:
    cases = load_retrieval_cases(
        API_ROOT / "data" / "evaluation" / "retrieval_cases.json"
    )
    documents = load_knowledge_directory(API_ROOT / "data" / "knowledge").documents
    comparison = compare_retrieval(cases, documents)

    assert comparison.baseline.recall_at_1 == 0.9
    assert comparison.improved.recall_at_1 == 1.0
    assert comparison.recall_at_1_delta == 0.1
    assert comparison.recall_at_3_delta == 0.1
    assert comparison.mrr_delta == 0.1
    assert comparison.baseline.no_answer_accuracy == 0.0
    assert comparison.improved.no_answer_accuracy == 1.0
    assert comparison.no_answer_accuracy_delta == 1.0
    assert comparison.baseline.overall_accuracy == 0.6
    assert comparison.improved.overall_accuracy == 1.0
    assert comparison.overall_accuracy_delta == 0.4


def test_empty_evaluation_returns_zero_metrics() -> None:
    report = evaluate_retrieval([], [])
    assert report.mode == "query-expansion-confidence-v1"
    assert report.total_cases == 0
    assert report.recall_at_1 == 0.0
    assert report.recall_at_3 == 0.0
    assert report.mrr == 0.0
    assert report.no_answer_accuracy == 0.0
    assert report.overall_accuracy == 0.0
