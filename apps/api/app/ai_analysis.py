"""Gemini 기반 상담 구조화 분석과 규칙 기반 안전장치."""

from __future__ import annotations

import json
from dataclasses import dataclass

from .llm import DraftLLM, LLMGenerationError
from .models import Consultation, ConsultationStatus, RiskLevel
from .pii import sanitize_consultation


ANALYSIS_PROMPT_VERSION = "triage-v1"
ANALYSIS_SYSTEM_INSTRUCTION = """당신은 은행 상담 접수 내용을 구조화하는 AI입니다.
반드시 제공된 고객 문의만 분석하고 JSON 객체 하나만 반환하세요.
개인정보를 복원하거나 추측하지 마세요.
위험도를 낮게 판단해 자동 처리하도록 유도하지 마세요.
허용 위험도는 Critical, High, Medium, Low, Unknown입니다."""


RISK_ORDER = {
    RiskLevel.UNKNOWN: 0,
    RiskLevel.LOW: 1,
    RiskLevel.MEDIUM: 2,
    RiskLevel.HIGH: 3,
    RiskLevel.CRITICAL: 4,
}


@dataclass(frozen=True)
class StructuredAnalysis:
    summary: str
    intent: str
    risk: RiskLevel
    confidence: float
    required_checks: list[str]
    rationale: list[str]


def build_analysis_prompt(consultation: Consultation) -> str:
    return "\n".join(
        [
            f"프롬프트 버전: {ANALYSIS_PROMPT_VERSION}",
            f"문의 주제: {consultation.topic}",
            f"고객 문의: {consultation.question}",
            "다음 스키마로만 응답하세요:",
            '{"summary":"한 줄 요약","intent":"고객 의도","risk":"Low",'
            '"confidence":0.0,"required_checks":["확인 항목"],'
            '"rationale":["판단 근거"]}',
            "summary와 intent는 각각 80자 이내, 배열은 각 5개 이하로 작성하세요.",
        ]
    )


def _json_object(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    try:
        value = json.loads(cleaned)
    except (json.JSONDecodeError, TypeError) as error:
        raise LLMGenerationError("상담 분석 응답이 올바른 JSON이 아닙니다.") from error
    if not isinstance(value, dict):
        raise LLMGenerationError("상담 분석 응답이 JSON 객체가 아닙니다.")
    return value


def _limited_strings(value: object, *, maximum: int = 5) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip()[:100] for item in value if str(item).strip()][:maximum]


def parse_structured_analysis(text: str) -> StructuredAnalysis:
    value = _json_object(text)
    try:
        risk = RiskLevel(str(value.get("risk", "Unknown")).strip().title())
        confidence = max(0.0, min(1.0, float(value.get("confidence", 0))))
    except (ValueError, TypeError) as error:
        raise LLMGenerationError("상담 분석의 위험도 또는 신뢰도 형식이 잘못되었습니다.") from error

    summary = str(value.get("summary", "")).strip()[:80]
    intent = str(value.get("intent", "")).strip()[:80]
    if not summary or not intent:
        raise LLMGenerationError("상담 분석에 요약 또는 의도가 없습니다.")
    return StructuredAnalysis(
        summary=summary,
        intent=intent,
        risk=risk,
        confidence=confidence,
        required_checks=_limited_strings(value.get("required_checks")),
        rationale=_limited_strings(value.get("rationale")),
    )


def _safer_risk(current: RiskLevel, proposed: RiskLevel) -> RiskLevel:
    return current if RISK_ORDER[current] >= RISK_ORDER[proposed] else proposed


def _status_for(risk: RiskLevel, current: ConsultationStatus) -> ConsultationStatus:
    if current == ConsultationStatus.COMPLETED:
        return current
    if risk in {RiskLevel.CRITICAL, RiskLevel.HIGH}:
        return ConsultationStatus.ESCALATED
    if risk == RiskLevel.MEDIUM:
        return ConsultationStatus.NEEDS_INFO
    return ConsultationStatus.READY


def _merge_checks(current: list[str], proposed: list[str]) -> list[str]:
    merged: list[str] = []
    for item in [*proposed, *current]:
        if item and item not in merged and item != "공식 근거 검색":
            merged.append(item)
    return merged[:7]


def analyze_consultation_with_llm(
    consultation: Consultation,
    client: DraftLLM,
) -> Consultation:
    safe = sanitize_consultation(consultation)
    if not client.configured:
        return safe.model_copy(
            update={
                "analysis_engine": "rules-fallback-v1",
                "analysis_model": client.model,
                "analysis_latency_ms": None,
                "analysis_confidence": None,
                "analysis_prompt_version": ANALYSIS_PROMPT_VERSION,
                "analysis_rationale": ["API 키가 없어 기존 규칙 분석을 유지했습니다."],
            }
        )

    try:
        response = client.generate(
            ANALYSIS_SYSTEM_INSTRUCTION,
            build_analysis_prompt(safe),
        )
        result = parse_structured_analysis(response.text)
    except LLMGenerationError as error:
        return safe.model_copy(
            update={
                "analysis_engine": "rules-fallback-v1",
                "analysis_model": client.model,
                "analysis_latency_ms": None,
                "analysis_confidence": None,
                "analysis_prompt_version": ANALYSIS_PROMPT_VERSION,
                "analysis_rationale": [f"LLM 분석 실패로 규칙 결과를 유지했습니다: {error}"],
            }
        )

    final_risk = _safer_risk(safe.risk, result.risk)
    rationale = [*result.rationale]
    if final_risk != result.risk:
        rationale.append("규칙 기반 안전장치가 더 높은 기존 위험도를 유지했습니다.")
    restriction = safe.restriction_reason
    if final_risk in {RiskLevel.CRITICAL, RiskLevel.HIGH}:
        restriction = "고위험 상담은 자동 승인을 제한하고 관리자 검토가 필요합니다."
    elif final_risk == RiskLevel.MEDIUM:
        restriction = "거래정보를 추가로 확인한 뒤 답변을 검토해야 합니다."

    return safe.model_copy(
        update={
            "summary": result.summary,
            "intent": result.intent,
            "risk": final_risk,
            "status": _status_for(final_risk, safe.status),
            "required_checks": _merge_checks(safe.required_checks, result.required_checks),
            "analysis_engine": "gemini-structured-triage-v1",
            "analysis_model": response.model,
            "analysis_latency_ms": response.latency_ms,
            "analysis_confidence": result.confidence,
            "analysis_prompt_version": ANALYSIS_PROMPT_VERSION,
            "analysis_rationale": rationale[:6],
            "restriction_reason": restriction,
        }
    )
