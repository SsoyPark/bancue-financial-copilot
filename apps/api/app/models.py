from enum import StrEnum

from pydantic import BaseModel, Field, model_validator


class RiskLevel(StrEnum):
    CRITICAL = "Critical"
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"
    UNKNOWN = "Unknown"


class ConsultationStatus(StrEnum):
    RECEIVED = "Received"
    NEEDS_INFO = "Needs Info"
    READY = "Ready for Review"
    ESCALATED = "Escalated"
    COMPLETED = "Completed"


class WorkflowAction(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"
    ESCALATE = "escalate"


class FeedbackRating(StrEnum):
    HELPFUL = "helpful"
    NEEDS_IMPROVEMENT = "needs_improvement"


class FeedbackIssue(StrEnum):
    WRONG_EVIDENCE = "wrong_evidence"
    MISSING_EVIDENCE = "missing_evidence"
    DRAFT_QUALITY = "draft_quality"
    OTHER = "other"


class ActionRequest(BaseModel):
    action: WorkflowAction
    actor: str = Field(default="local-counselor", max_length=80)
    note: str | None = Field(default=None, max_length=500)
    confirmed_checks: list[str] = Field(default_factory=list)


class ActionRecord(BaseModel):
    action: WorkflowAction
    actor: str
    note: str | None = None
    confirmed_checks: list[str] = Field(default_factory=list)
    created_at: str


class FeedbackRequest(BaseModel):
    intent_score: int = Field(ge=1, le=5)
    draft_score: int = Field(ge=1, le=5)
    issue_types: list[FeedbackIssue] = Field(default_factory=list)
    note: str | None = Field(default=None, max_length=500)
    actor: str = Field(default="local-counselor", max_length=80)

    @model_validator(mode="after")
    def require_issue_for_low_score(self) -> "FeedbackRequest":
        if min(self.intent_score, self.draft_score) <= 3 and not self.issue_types:
            raise ValueError("3점 이하 평가에는 개선 사유가 필요합니다.")
        return self


class FeedbackRecord(BaseModel):
    id: int | None = None
    consultation_id: str
    rating: FeedbackRating
    intent_score: int = 0
    draft_score: int = 0
    issue_types: list[FeedbackIssue] = Field(default_factory=list)
    note: str | None = None
    pii_masked: bool = False
    pii_types: list[str] = Field(default_factory=list)
    actor: str
    created_at: str


class FeedbackSummary(BaseModel):
    total: int
    helpful: int
    needs_improvement: int
    helpful_rate: float
    scored_feedback: int
    average_intent_score: float
    average_draft_score: float
    issue_counts: dict[str, int] = Field(default_factory=dict)
    recent: list[FeedbackRecord] = Field(default_factory=list)


class Evidence(BaseModel):
    document_id: str = ""
    title: str
    section: str
    status: str = "Valid"
    effective_date: str
    score: int | None = None
    matched_terms: list[str] = Field(default_factory=list)
    query_expansions: list[str] = Field(default_factory=list)
    query_rule_ids: list[str] = Field(default_factory=list)
    source_type: str = "synthetic"
    source_organization: str = ""
    source_url: str = ""
    source_published_at: str = ""
    verified_at: str = ""
    review_status: str = "Verified"
    summary_method: str = "synthetic"
    excerpt: str | None = None


class RetrievalCandidateTrace(BaseModel):
    document_id: str
    title: str
    score: int
    matched_terms: list[str] = Field(default_factory=list)
    accepted: bool


class RetrievalTrace(BaseModel):
    original_query: str
    expanded_query: str
    query_expansions: list[str] = Field(default_factory=list)
    query_rule_ids: list[str] = Field(default_factory=list)
    minimum_score: int
    decision: str
    reason: str
    candidates: list[RetrievalCandidateTrace] = Field(default_factory=list)


class Consultation(BaseModel):
    id: str
    customer: str
    topic: str
    summary: str
    question: str
    risk: RiskLevel
    status: ConsultationStatus
    waiting_time: str
    intent: str
    pii_masked: bool = False
    pii_types: list[str] = Field(default_factory=list)
    risk_reasons: list[str] = Field(default_factory=list)
    rule_ids: list[str] = Field(default_factory=list)
    required_checks: list[str] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    retrieval_trace: RetrievalTrace | None = None
    draft: str | None = None
    draft_generated: bool = False
    draft_source_ids: list[str] = Field(default_factory=list)
    draft_notice: str | None = None
    restriction_reason: str | None = None
    action_history: list[ActionRecord] = Field(default_factory=list)


class ConsultationListResponse(BaseModel):
    items: list[Consultation]
    total: int
