export type RiskLevel = 'Critical' | 'High' | 'Medium' | 'Low' | 'Unknown'
export type WorkflowAction = 'approve' | 'reject' | 'escalate'
export type FeedbackRating = 'helpful' | 'needs_improvement'
export type FeedbackIssue = 'wrong_evidence' | 'missing_evidence' | 'draft_quality' | 'other'
export type ConsultationStatus =
  | 'Received'
  | 'Needs Info'
  | 'Ready for Review'
  | 'Escalated'
  | 'Completed'

export interface Evidence {
  document_id?: string
  title: string
  section: string
  status: string
  effective_date: string
  score?: number | null
  matched_terms?: string[]
  query_expansions?: string[]
  query_rule_ids?: string[]
  source_type?: string
  source_organization?: string
  source_url?: string
  source_published_at?: string
  verified_at?: string
  review_status?: string
  summary_method?: string
  excerpt?: string | null
}

export interface ActionRecord {
  action: WorkflowAction
  actor: string
  note: string | null
  confirmed_checks: string[]
  created_at: string
}

export interface RetrievalCandidateTrace {
  document_id: string
  title: string
  score: number
  matched_terms: string[]
  accepted: boolean
}

export interface RetrievalTrace {
  original_query: string
  expanded_query: string
  query_expansions: string[]
  query_rule_ids: string[]
  minimum_score: number
  decision: 'grounded' | 'abstained'
  reason: string
  candidates: RetrievalCandidateTrace[]
}

export interface Consultation {
  id: string
  customer: string
  topic: string
  summary: string
  question: string
  risk: RiskLevel
  status: ConsultationStatus
  waiting_time: string
  intent: string
  pii_masked: boolean
  pii_types: string[]
  risk_reasons: string[]
  rule_ids: string[]
  required_checks: string[]
  evidence: Evidence[]
  retrieval_trace?: RetrievalTrace | null
  draft: string | null
  draft_generated: boolean
  draft_source_ids: string[]
  draft_notice: string | null
  restriction_reason: string | null
  action_history: ActionRecord[]
}

export interface ConsultationListResponse {
  items: Consultation[]
  total: number
}

export interface FeedbackRequest {
  intent_score: number
  draft_score: number
  issue_types: FeedbackIssue[]
  note: string | null
  actor: string
}

export interface FeedbackRecord extends FeedbackRequest {
  id: number | null
  consultation_id: string
  rating: FeedbackRating
  pii_masked: boolean
  pii_types: string[]
  created_at: string
}

export interface FeedbackSummary {
  total: number
  helpful: number
  needs_improvement: number
  helpful_rate: number
  scored_feedback: number
  average_intent_score: number
  average_draft_score: number
  issue_counts: Record<string, number>
  recent: FeedbackRecord[]
}

export interface RetrievalCaseResult {
  case_id: string
  query: string
  expanded_query: string
  added_terms: string[]
  query_rule_ids: string[]
  description: string
  expected_document_ids: string[]
  expected_no_answer: boolean
  retrieved_document_ids: string[]
  hit_rank: number | null
  outcome: 'hit' | 'miss' | 'correct-abstention' | 'false-positive'
  passed: boolean
}

export interface RetrievalEvaluation {
  mode: string
  total_cases: number
  positive_cases: number
  no_answer_cases: number
  passed_cases: number
  failed_cases: number
  false_positive_cases: number
  recall_at_1: number
  recall_at_3: number
  mrr: number
  no_answer_accuracy: number
  overall_accuracy: number
  results: RetrievalCaseResult[]
}

export interface RetrievalEvaluationComparison {
  baseline: RetrievalEvaluation
  improved: RetrievalEvaluation
  recall_at_1_delta: number
  recall_at_3_delta: number
  mrr_delta: number
  no_answer_accuracy_delta: number
  overall_accuracy_delta: number
}

export interface KnowledgeSource {
  document_id: string
  title: string
  section: string
  status: string
  effective_date: string
  source_type: string
  source_organization: string
  source_url: string
  source_published_at: string
  verified_at: string
  review_status: string
  summary_method: string
}
