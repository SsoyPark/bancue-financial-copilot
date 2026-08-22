import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .models import Consultation, ConsultationStatus, RiskLevel


@dataclass(frozen=True)
class LoadResult:
    items: list[Consultation]
    loaded_files: int
    skipped_files: int


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _string(value: Any, default: str = "") -> str:
    return value.strip() if isinstance(value, str) and value.strip() else default


def parse_aihub_consultation(payload: dict[str, Any], fallback_id: str) -> Consultation:
    """AI Hub 금융 상담 JSON 한 건을 BANCUE 화면 모델로 변환한다."""
    source = _dict(payload.get("source"))
    consulting = _dict(payload.get("consulting"))
    qa_data = _dict(payload.get("qa_data"))
    input_data = _dict(qa_data.get("input"))

    consultation_id = _string(
        qa_data.get("qa_id"), _string(source.get("source_id"), fallback_id)
    )
    topic = _string(
        consulting.get("consulting_topic"),
        _string(qa_data.get("qa_topic"), "유형 미분류"),
    )
    summary = _string(
        consulting.get("consulting_summary"),
        _string(source.get("consulting_summary"), topic),
    )
    question = _string(
        input_data.get("question"),
        _string(source.get("consulting_content"), "질문 내용 없음"),
    )
    intent = _string(qa_data.get("consulting_purpose"), summary)
    draft = _string(qa_data.get("output")) or None

    return Consultation(
        id=consultation_id,
        customer="고객",
        topic=topic,
        summary=summary,
        question=question,
        risk=RiskLevel.UNKNOWN,
        status=ConsultationStatus.RECEIVED,
        waiting_time="00:00",
        intent=intent,
        required_checks=["상담 유형 확인", "위험도 판정", "공식 근거 검색"],
        evidence=[],
        draft=draft,
        restriction_reason="AI Hub 원천 데이터로, 아직 위험도와 공식 근거를 검증하지 않았습니다.",
    )


def load_aihub_directory(data_dir: Path, limit: int = 200) -> LoadResult:
    """폴더 아래 JSON을 재귀 탐색한다. 잘못된 파일은 건너뛴다."""
    if not data_dir.exists():
        return LoadResult(items=[], loaded_files=0, skipped_files=0)

    items: list[Consultation] = []
    seen_ids: set[str] = set()
    skipped = 0

    for path in sorted(data_dir.rglob("*.json")):
        if len(items) >= limit:
            break
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
            if not isinstance(payload, dict):
                raise ValueError("JSON root must be an object")
            consultation = parse_aihub_consultation(payload, path.stem)
            if consultation.id in seen_ids:
                skipped += 1
                continue
            seen_ids.add(consultation.id)
            items.append(consultation)
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError, TypeError):
            skipped += 1

    return LoadResult(items=items, loaded_files=len(items), skipped_files=skipped)

