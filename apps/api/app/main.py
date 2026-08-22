import os
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .database import WorkflowStateStore
from .draft import generate_grounded_draft
from .evaluation import (
    RetrievalEvaluation,
    RetrievalEvaluationComparison,
    compare_retrieval,
    evaluate_retrieval,
    load_retrieval_cases,
)
from .knowledge import (
    attach_evidence,
    evidence_from_match,
    explain_knowledge_search,
    load_knowledge_directory,
    search_knowledge,
    source_registry,
)
from .models import (
    ActionRequest,
    Consultation,
    ConsultationListResponse,
    FeedbackRecord,
    FeedbackRequest,
    FeedbackRating,
    FeedbackSummary,
    RetrievalTrace,
    RiskLevel,
)
from .pii import mask_text, sanitize_consultation
from .repository import load_aihub_directory
from .risk import assess_risk
from .seed import CONSULTATIONS
from .workflow import WorkflowError, apply_action


DEFAULT_DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "sample"
DEFAULT_KNOWLEDGE_DIR = Path(__file__).resolve().parents[1] / "data" / "knowledge"
DEFAULT_STATE_DB = Path(__file__).resolve().parents[1] / "data" / "runtime" / "bancue.db"
DEFAULT_EVALUATION_FILE = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "evaluation"
    / "retrieval_cases.json"
)
DATA_DIR = Path(os.getenv("BANCUE_DATA_DIR", DEFAULT_DATA_DIR))
KNOWLEDGE_DIR = Path(os.getenv("BANCUE_KNOWLEDGE_DIR", DEFAULT_KNOWLEDGE_DIR))
STATE_DB_PATH = Path(os.getenv("BANCUE_STATE_DB", DEFAULT_STATE_DB))
EVALUATION_FILE = Path(os.getenv("BANCUE_EVALUATION_FILE", DEFAULT_EVALUATION_FILE))
DATA_LIMIT = int(os.getenv("BANCUE_DATA_LIMIT", "200"))
LOAD_RESULT = load_aihub_directory(DATA_DIR, limit=DATA_LIMIT)
KNOWLEDGE_RESULT = load_knowledge_directory(KNOWLEDGE_DIR)
RETRIEVAL_CASES = load_retrieval_cases(EVALUATION_FILE)
RAW_CONSULTATIONS = LOAD_RESULT.items or CONSULTATIONS
MASKED_CONSULTATIONS = [sanitize_consultation(item) for item in RAW_CONSULTATIONS]
STATE_STORE = WorkflowStateStore(STATE_DB_PATH)
GENERATED_CONSULTATIONS = [
    generate_grounded_draft(
        attach_evidence(assess_risk(item), KNOWLEDGE_RESULT.documents)
    )
    for item in MASKED_CONSULTATIONS
]
ACTIVE_CONSULTATIONS = [
    STATE_STORE.restore(item) for item in GENERATED_CONSULTATIONS
]
DATA_SOURCE = "aihub-json" if LOAD_RESULT.items else "built-in-seed"


app = FastAPI(title="BANCUE API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str | int]:
    return {
        "status": "ok",
        "service": "bancue-api",
        "data_source": DATA_SOURCE,
        "consultation_count": len(ACTIVE_CONSULTATIONS),
        "skipped_files": LOAD_RESULT.skipped_files,
        "risk_engine": "rules-v1",
        "pii_masker": "regex-v1",
        "retrieval_engine": "keyword-score-v3-confidence-gate",
        "query_expansion": "rules-v1",
        "retrieval_minimum_score": 8,
        "explainability_engine": "retrieval-trace-v1",
        "knowledge_count": KNOWLEDGE_RESULT.loaded_files,
        "official_knowledge_count": KNOWLEDGE_RESULT.official_documents,
        "synthetic_knowledge_count": KNOWLEDGE_RESULT.synthetic_documents,
        "knowledge_review_required_count": KNOWLEDGE_RESULT.review_required_documents,
        "draft_engine": "grounded-template-v1",
        "workflow_engine": "sqlite-v1",
        "persisted_state_count": STATE_STORE.count(),
        "feedback_engine": "sqlite-score-masked-v2",
        "feedback_count": STATE_STORE.feedback_count(),
        "evaluation_case_count": len(RETRIEVAL_CASES),
    }


@app.get("/api/consultations", response_model=ConsultationListResponse)
def list_consultations(
    search: str | None = Query(default=None),
    risk: RiskLevel | None = Query(default=None),
) -> ConsultationListResponse:
    items = ACTIVE_CONSULTATIONS
    if search:
        term = search.casefold()
        items = [
            item
            for item in items
            if term in item.id.casefold()
            or term in item.customer.casefold()
            or term in item.summary.casefold()
        ]
    if risk:
        items = [item for item in items if item.risk == risk]
    return ConsultationListResponse(items=items, total=len(items))


@app.get("/api/consultations/{consultation_id}", response_model=Consultation)
def get_consultation(consultation_id: str) -> Consultation:
    consultation = next(
        (item for item in ACTIVE_CONSULTATIONS if item.id == consultation_id), None
    )
    if consultation is None:
        raise HTTPException(status_code=404, detail="Consultation not found")
    return consultation


@app.post("/api/consultations/{consultation_id}/actions", response_model=Consultation)
def process_consultation_action(
    consultation_id: str,
    request: ActionRequest,
) -> Consultation:
    index = next(
        (
            index
            for index, item in enumerate(ACTIVE_CONSULTATIONS)
            if item.id == consultation_id
        ),
        None,
    )
    if index is None:
        raise HTTPException(status_code=404, detail="Consultation not found")

    try:
        updated = apply_action(ACTIVE_CONSULTATIONS[index], request)
    except WorkflowError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error

    STATE_STORE.save(updated)
    ACTIVE_CONSULTATIONS[index] = updated
    return updated


@app.post(
    "/api/consultations/{consultation_id}/feedback",
    response_model=FeedbackRecord,
)
def create_consultation_feedback(
    consultation_id: str,
    request: FeedbackRequest,
) -> FeedbackRecord:
    if not any(item.id == consultation_id for item in ACTIVE_CONSULTATIONS):
        raise HTTPException(status_code=404, detail="Consultation not found")

    masked_note = mask_text(request.note) if request.note else None
    feedback = FeedbackRecord(
        consultation_id=consultation_id,
        rating=(
            FeedbackRating.HELPFUL
            if min(request.intent_score, request.draft_score) >= 4
            else FeedbackRating.NEEDS_IMPROVEMENT
        ),
        intent_score=request.intent_score,
        draft_score=request.draft_score,
        issue_types=request.issue_types,
        note=masked_note.text if masked_note else None,
        pii_masked=bool(masked_note and masked_note.detected_types),
        pii_types=list(masked_note.detected_types) if masked_note else [],
        actor=request.actor,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    return STATE_STORE.save_feedback(feedback)


@app.get("/api/feedback/summary", response_model=FeedbackSummary)
def get_feedback_summary(
    recent_limit: int = Query(default=20, ge=1, le=100),
) -> FeedbackSummary:
    return STATE_STORE.feedback_summary(recent_limit=recent_limit)


@app.get("/api/knowledge/search")
def search_knowledge_api(
    q: str = Query(min_length=2),
    limit: int = Query(default=3, ge=1, le=5),
) -> list[dict]:
    matches = search_knowledge(q, KNOWLEDGE_RESULT.documents, limit=limit)
    return [evidence_from_match(match).model_dump() for match in matches]


@app.get("/api/knowledge/sources")
def list_knowledge_sources_api() -> list[dict[str, str]]:
    return source_registry(KNOWLEDGE_RESULT.documents)


@app.get("/api/knowledge/explain", response_model=RetrievalTrace)
def explain_knowledge_search_api(
    q: str = Query(min_length=2),
    limit: int = Query(default=3, ge=1, le=5),
) -> RetrievalTrace:
    return explain_knowledge_search(q, KNOWLEDGE_RESULT.documents, limit=limit)


@app.get("/api/evaluation/retrieval", response_model=RetrievalEvaluation)
def evaluate_retrieval_api() -> RetrievalEvaluation:
    return evaluate_retrieval(
        RETRIEVAL_CASES,
        KNOWLEDGE_RESULT.documents,
        use_query_expansion=True,
        minimum_score=8,
    )


@app.get(
    "/api/evaluation/retrieval/comparison",
    response_model=RetrievalEvaluationComparison,
)
def compare_retrieval_api() -> RetrievalEvaluationComparison:
    return compare_retrieval(RETRIEVAL_CASES, KNOWLEDGE_RESULT.documents)
