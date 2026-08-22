from dataclasses import dataclass


@dataclass(frozen=True)
class QueryExpansionRule:
    rule_id: str
    required_phrases: tuple[str, ...]
    added_terms: tuple[str, ...]


@dataclass(frozen=True)
class NormalizedQuery:
    original: str
    expanded: str
    added_terms: tuple[str, ...]
    rule_ids: tuple[str, ...]


QUERY_EXPANSION_RULES = (
    QueryExpansionRule(
        rule_id="QUERY-AUTO-001",
        required_phrases=("매달", "빠져나가"),
        added_terms=("자동이체", "자동납부"),
    ),
    QueryExpansionRule(
        rule_id="QUERY-AUTO-002",
        required_phrases=("다른 통장", "나가"),
        added_terms=("출금계좌", "변경"),
    ),
    QueryExpansionRule(
        rule_id="QUERY-CARD-001",
        required_phrases=("잃어버",),
        added_terms=("분실",),
    ),
    QueryExpansionRule(
        rule_id="QUERY-CARD-002",
        required_phrases=("하지 않은 결제",),
        added_terms=("부정사용",),
    ),
    QueryExpansionRule(
        rule_id="QUERY-LOAN-001",
        required_phrases=("일찍 갚",),
        added_terms=("중도상환",),
    ),
    QueryExpansionRule(
        rule_id="QUERY-REMIT-001",
        required_phrases=("해외로", "송금"),
        added_terms=("해외송금",),
    ),
)


def normalize_query(query: str) -> NormalizedQuery:
    """일상 표현을 설명 가능한 금융 용어로 확장한다."""
    normalized = query.casefold()
    added_terms: list[str] = []
    rule_ids: list[str] = []

    for rule in QUERY_EXPANSION_RULES:
        if not all(phrase.casefold() in normalized for phrase in rule.required_phrases):
            continue
        rule_ids.append(rule.rule_id)
        for term in rule.added_terms:
            if term.casefold() not in normalized and term not in added_terms:
                added_terms.append(term)

    expanded = " ".join([query, *added_terms]).strip()
    return NormalizedQuery(
        original=query,
        expanded=expanded,
        added_terms=tuple(added_terms),
        rule_ids=tuple(rule_ids),
    )
