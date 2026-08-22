import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .models import (
    Consultation,
    Evidence,
    RetrievalCandidateTrace,
    RetrievalTrace,
)
from .query import normalize_query


@dataclass(frozen=True)
class KnowledgeDocument:
    document_id: str
    title: str
    section: str
    status: str
    effective_date: str
    keywords: tuple[str, ...]
    content: str
    source_type: str = "synthetic"
    source_organization: str = ""
    source_url: str = ""
    source_published_at: str = ""
    verified_at: str = ""
    review_status: str = "Verified"
    summary_method: str = "synthetic"


@dataclass(frozen=True)
class KnowledgeMatch:
    document: KnowledgeDocument
    score: int
    matched_terms: tuple[str, ...]
    query_expansions: tuple[str, ...] = ()
    query_rule_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class KnowledgeLoadResult:
    documents: list[KnowledgeDocument]
    loaded_files: int
    skipped_files: int
    official_documents: int = 0
    synthetic_documents: int = 0
    review_required_documents: int = 0


TOKEN_PATTERN = re.compile(r"[가-힣A-Z0-9]{2,}", re.IGNORECASE)
DEFAULT_MINIMUM_SCORE = 8


def _string(value: Any, default: str = "") -> str:
    return value.strip() if isinstance(value, str) and value.strip() else default


def _parse_document(payload: dict[str, Any], fallback_id: str) -> KnowledgeDocument:
    keywords = payload.get("keywords", [])
    if not isinstance(keywords, list):
        raise ValueError("keywords must be a list")

    document = KnowledgeDocument(
        document_id=_string(payload.get("document_id"), fallback_id),
        title=_string(payload.get("title")),
        section=_string(payload.get("section")),
        status=_string(payload.get("status"), "Valid"),
        effective_date=_string(payload.get("effective_date")),
        keywords=tuple(_string(keyword) for keyword in keywords if _string(keyword)),
        content=_string(payload.get("content")),
        source_type=_string(payload.get("source_type"), "synthetic"),
        source_organization=_string(payload.get("source_organization")),
        source_url=_string(payload.get("source_url")),
        source_published_at=_string(payload.get("source_published_at")),
        verified_at=_string(payload.get("verified_at")),
        review_status=_string(payload.get("review_status"), "Verified"),
        summary_method=_string(payload.get("summary_method"), "synthetic"),
    )
    if not document.title or not document.section or not document.content:
        raise ValueError("required knowledge fields are missing")
    if document.source_type == "official-public":
        if not document.source_organization or not document.verified_at:
            raise ValueError("official source metadata is missing")
        if not document.source_url.startswith("https://"):
            raise ValueError("official source URL must use HTTPS")
    return document


def load_knowledge_directory(data_dir: Path) -> KnowledgeLoadResult:
    """폴더의 업무지침 JSON을 읽고 잘못된 파일은 건너뛴다."""
    if not data_dir.exists():
        return KnowledgeLoadResult(documents=[], loaded_files=0, skipped_files=0)

    documents: list[KnowledgeDocument] = []
    seen_ids: set[str] = set()
    skipped = 0

    for path in sorted(data_dir.rglob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
            if not isinstance(payload, dict):
                raise ValueError("JSON root must be an object")
            document = _parse_document(payload, path.stem)
            if document.document_id in seen_ids:
                skipped += 1
                continue
            seen_ids.add(document.document_id)
            documents.append(document)
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError, TypeError):
            skipped += 1

    return KnowledgeLoadResult(
        documents=documents,
        loaded_files=len(documents),
        skipped_files=skipped,
        official_documents=sum(
            document.source_type == "official-public" for document in documents
        ),
        synthetic_documents=sum(
            document.source_type == "synthetic" for document in documents
        ),
        review_required_documents=sum(
            document.review_status != "Verified" for document in documents
        ),
    )


def _tokens(text: str) -> set[str]:
    return {token.casefold() for token in TOKEN_PATTERN.findall(text)}


def _non_overlapping_keyword_matches(
    keywords: tuple[str, ...],
    normalized_query: str,
) -> tuple[str, ...]:
    """`해외송금`과 그 안의 `송금`을 같은 증거로 중복 계산하지 않는다."""
    raw_matches = [
        keyword for keyword in keywords if keyword.casefold() in normalized_query
    ]
    return tuple(
        keyword
        for keyword in raw_matches
        if not any(
            keyword.casefold() != other.casefold()
            and keyword.casefold() in other.casefold()
            for other in raw_matches
        )
    )


def _rank_knowledge_candidates(
    query: str,
    documents: list[KnowledgeDocument],
    use_query_expansion: bool = True,
) -> list[KnowledgeMatch]:
    """최소 점수 적용 전의 검증된 키워드 후보를 점수순으로 반환한다."""
    normalized = normalize_query(query) if use_query_expansion else None
    search_query = normalized.expanded if normalized else query
    normalized_query = search_query.casefold()
    query_tokens = _tokens(search_query)
    matches: list[KnowledgeMatch] = []

    for document in documents:
        if document.status.casefold() != "valid":
            continue
        if document.review_status.casefold() != "verified":
            continue

        matched_terms = _non_overlapping_keyword_matches(
            document.keywords,
            normalized_query,
        )
        if not matched_terms:
            continue

        document_tokens = _tokens(
            f"{document.title} {document.section} {document.content}"
        )
        token_overlap = query_tokens & document_tokens
        score = len(matched_terms) * 5 + min(len(token_overlap), 5)
        matches.append(
            KnowledgeMatch(
                document=document,
                score=score,
                matched_terms=matched_terms,
                query_expansions=normalized.added_terms if normalized else (),
                query_rule_ids=normalized.rule_ids if normalized else (),
            )
        )

    return sorted(
        matches,
        key=lambda match: (-match.score, match.document.document_id),
    )


def search_knowledge(
    query: str,
    documents: list[KnowledgeDocument],
    limit: int = 3,
    use_query_expansion: bool = True,
    minimum_score: int = DEFAULT_MINIMUM_SCORE,
) -> list[KnowledgeMatch]:
    """질의 확장과 최소 점수 게이트를 적용해 검증된 근거를 검색한다."""
    candidates = _rank_knowledge_candidates(
        query,
        documents,
        use_query_expansion=use_query_expansion,
    )
    return [
        candidate for candidate in candidates if candidate.score >= minimum_score
    ][:limit]


def explain_knowledge_search(
    query: str,
    documents: list[KnowledgeDocument],
    limit: int = 3,
    use_query_expansion: bool = True,
    minimum_score: int = DEFAULT_MINIMUM_SCORE,
) -> RetrievalTrace:
    """검색 후보와 점수 게이트의 최종 판단을 사람이 읽을 수 있게 설명한다."""
    normalized = normalize_query(query) if use_query_expansion else None
    candidates = _rank_knowledge_candidates(
        query,
        documents,
        use_query_expansion=use_query_expansion,
    )
    accepted = [candidate for candidate in candidates if candidate.score >= minimum_score]

    if accepted:
        top = accepted[0]
        decision = "grounded"
        reason = (
            f"상위 후보 {top.document.document_id}의 점수 {top.score}점이 "
            f"최소 기준 {minimum_score}점 이상이어서 근거로 연결했습니다."
        )
    elif candidates:
        top = candidates[0]
        decision = "abstained"
        reason = (
            f"최고 후보 {top.document.document_id}의 점수 {top.score}점이 "
            f"최소 기준 {minimum_score}점보다 낮아 검색을 중단했습니다."
        )
    else:
        decision = "abstained"
        reason = "일치하는 검증 금융 업무 키워드가 없어 검색을 중단했습니다."

    return RetrievalTrace(
        original_query=query,
        expanded_query=normalized.expanded if normalized else query,
        query_expansions=list(normalized.added_terms) if normalized else [],
        query_rule_ids=list(normalized.rule_ids) if normalized else [],
        minimum_score=minimum_score,
        decision=decision,
        reason=reason,
        candidates=[
            RetrievalCandidateTrace(
                document_id=candidate.document.document_id,
                title=candidate.document.title,
                score=candidate.score,
                matched_terms=list(candidate.matched_terms),
                accepted=candidate.score >= minimum_score,
            )
            for candidate in candidates[:limit]
        ],
    )


def evidence_from_match(match: KnowledgeMatch) -> Evidence:
    document = match.document
    return Evidence(
        document_id=document.document_id,
        title=document.title,
        section=document.section,
        status=document.status,
        effective_date=document.effective_date,
        score=match.score,
        matched_terms=list(match.matched_terms),
        query_expansions=list(match.query_expansions),
        query_rule_ids=list(match.query_rule_ids),
        source_type=document.source_type,
        source_organization=document.source_organization,
        source_url=document.source_url,
        source_published_at=document.source_published_at,
        verified_at=document.verified_at,
        review_status=document.review_status,
        summary_method=document.summary_method,
        excerpt=document.content,
    )


def source_registry(documents: list[KnowledgeDocument]) -> list[dict[str, str]]:
    """지식 문서의 출처와 검증 상태를 화면에 제공한다."""
    return [
        {
            "document_id": document.document_id,
            "title": document.title,
            "section": document.section,
            "status": document.status,
            "effective_date": document.effective_date,
            "source_type": document.source_type,
            "source_organization": document.source_organization,
            "source_url": document.source_url,
            "source_published_at": document.source_published_at,
            "verified_at": document.verified_at,
            "review_status": document.review_status,
            "summary_method": document.summary_method,
        }
        for document in sorted(documents, key=lambda item: item.document_id)
    ]


def attach_evidence(
    consultation: Consultation,
    documents: list[KnowledgeDocument],
) -> Consultation:
    """상담 문맥으로 지침을 검색해 상위 근거를 상담에 연결한다."""
    query = " ".join(
        [
            consultation.topic,
            consultation.summary,
            consultation.question,
            consultation.intent,
        ]
    )
    trace = explain_knowledge_search(query, documents, limit=3)
    matches = search_knowledge(query, documents, limit=2)
    if not matches:
        return consultation.model_copy(update={"retrieval_trace": trace})

    required_checks = [
        item for item in consultation.required_checks if item != "공식 근거 검색"
    ]
    if "근거 문서 유효일 확인" not in required_checks:
        required_checks.append("근거 문서 유효일 확인")

    return consultation.model_copy(
        update={
            "evidence": [evidence_from_match(match) for match in matches],
            "retrieval_trace": trace,
            "required_checks": required_checks,
        }
    )
