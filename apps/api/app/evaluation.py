import json
from pathlib import Path

from pydantic import BaseModel, Field

from .knowledge import KnowledgeDocument, search_knowledge
from .query import normalize_query


class RetrievalCase(BaseModel):
    case_id: str
    query: str
    expected_document_ids: list[str] = Field(default_factory=list)
    description: str = ""


class RetrievalCaseResult(BaseModel):
    case_id: str
    query: str
    expanded_query: str
    added_terms: list[str] = Field(default_factory=list)
    query_rule_ids: list[str] = Field(default_factory=list)
    description: str
    expected_document_ids: list[str]
    expected_no_answer: bool
    retrieved_document_ids: list[str]
    hit_rank: int | None
    outcome: str
    passed: bool


class RetrievalEvaluation(BaseModel):
    mode: str
    total_cases: int
    positive_cases: int
    no_answer_cases: int
    passed_cases: int
    failed_cases: int
    false_positive_cases: int
    recall_at_1: float
    recall_at_3: float
    mrr: float
    no_answer_accuracy: float
    overall_accuracy: float
    results: list[RetrievalCaseResult]


class RetrievalEvaluationComparison(BaseModel):
    baseline: RetrievalEvaluation
    improved: RetrievalEvaluation
    recall_at_1_delta: float
    recall_at_3_delta: float
    mrr_delta: float
    no_answer_accuracy_delta: float
    overall_accuracy_delta: float


def load_retrieval_cases(path: Path) -> list[RetrievalCase]:
    """JSON 정답셋에서 검색 평가 케이스를 읽는다."""
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    items = payload.get("cases", []) if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        raise ValueError("evaluation cases must be a list")
    return [RetrievalCase.model_validate(item) for item in items]


def evaluate_retrieval(
    cases: list[RetrievalCase],
    documents: list[KnowledgeDocument],
    use_query_expansion: bool = True,
    minimum_score: int = 8,
) -> RetrievalEvaluation:
    """정답 순위와 근거가 없을 때의 올바른 무응답을 함께 평가한다."""
    results: list[RetrievalCaseResult] = []
    recall_at_1_hits = 0
    recall_at_3_hits = 0
    reciprocal_rank_sum = 0.0
    no_answer_hits = 0
    false_positive_cases = 0

    for case in cases:
        normalized = normalize_query(case.query) if use_query_expansion else None
        matches = search_knowledge(
            case.query,
            documents,
            limit=3,
            use_query_expansion=use_query_expansion,
            minimum_score=minimum_score,
        )
        retrieved_ids = [match.document.document_id for match in matches]
        expected = set(case.expected_document_ids)
        expected_no_answer = not expected
        if expected_no_answer:
            hit_rank = None
            passed = not retrieved_ids
            outcome = "correct-abstention" if passed else "false-positive"
            if passed:
                no_answer_hits += 1
            else:
                false_positive_cases += 1
        else:
            hit_rank = next(
                (
                    rank
                    for rank, document_id in enumerate(retrieved_ids, start=1)
                    if document_id in expected
                ),
                None,
            )
            if hit_rank == 1:
                recall_at_1_hits += 1
            if hit_rank is not None and hit_rank <= 3:
                recall_at_3_hits += 1
                reciprocal_rank_sum += 1 / hit_rank
            passed = hit_rank is not None and hit_rank <= 3
            outcome = "hit" if passed else "miss"

        results.append(
            RetrievalCaseResult(
                case_id=case.case_id,
                query=case.query,
                expanded_query=normalized.expanded if normalized else case.query,
                added_terms=list(normalized.added_terms) if normalized else [],
                query_rule_ids=list(normalized.rule_ids) if normalized else [],
                description=case.description,
                expected_document_ids=case.expected_document_ids,
                expected_no_answer=expected_no_answer,
                retrieved_document_ids=retrieved_ids,
                hit_rank=hit_rank,
                outcome=outcome,
                passed=passed,
            )
        )

    total = len(cases)
    positive_cases = sum(bool(case.expected_document_ids) for case in cases)
    no_answer_cases = total - positive_cases
    passed = sum(result.passed for result in results)
    return RetrievalEvaluation(
        mode=(
            "query-expansion-confidence-v1"
            if use_query_expansion and minimum_score > 0
            else "baseline-keyword-v1"
        ),
        total_cases=total,
        positive_cases=positive_cases,
        no_answer_cases=no_answer_cases,
        passed_cases=passed,
        failed_cases=total - passed,
        false_positive_cases=false_positive_cases,
        recall_at_1=(
            round(recall_at_1_hits / positive_cases, 4) if positive_cases else 0.0
        ),
        recall_at_3=(
            round(recall_at_3_hits / positive_cases, 4) if positive_cases else 0.0
        ),
        mrr=(
            round(reciprocal_rank_sum / positive_cases, 4)
            if positive_cases
            else 0.0
        ),
        no_answer_accuracy=(
            round(no_answer_hits / no_answer_cases, 4) if no_answer_cases else 0.0
        ),
        overall_accuracy=round(passed / total, 4) if total else 0.0,
        results=results,
    )


def compare_retrieval(
    cases: list[RetrievalCase],
    documents: list[KnowledgeDocument],
) -> RetrievalEvaluationComparison:
    """같은 정답셋으로 기존 검색과 질의 확장 검색을 비교한다."""
    baseline = evaluate_retrieval(
        cases,
        documents,
        use_query_expansion=False,
        minimum_score=0,
    )
    improved = evaluate_retrieval(
        cases,
        documents,
        use_query_expansion=True,
        minimum_score=8,
    )
    return RetrievalEvaluationComparison(
        baseline=baseline,
        improved=improved,
        recall_at_1_delta=round(improved.recall_at_1 - baseline.recall_at_1, 4),
        recall_at_3_delta=round(improved.recall_at_3 - baseline.recall_at_3, 4),
        mrr_delta=round(improved.mrr - baseline.mrr, 4),
        no_answer_accuracy_delta=round(
            improved.no_answer_accuracy - baseline.no_answer_accuracy,
            4,
        ),
        overall_accuracy_delta=round(
            improved.overall_accuracy - baseline.overall_accuracy,
            4,
        ),
    )
