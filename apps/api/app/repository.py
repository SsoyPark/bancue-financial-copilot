import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

from .models import Consultation, ConsultationStatus, RiskLevel


@dataclass(frozen=True)
class LoadResult:
    items: list[Consultation]
    loaded_files: int
    skipped_files: int
    scanned_files: int = 0
    duplicate_files: int = 0
    invalid_files: int = 0
    total_bytes: int = 0
    reached_limit: bool = False


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _string(value: Any, default: str = "") -> str:
    return value.strip() if isinstance(value, str) and value.strip() else default


def iter_json_paths(data_dir: Path) -> Iterator[Path]:
    """JSON 경로 전체 목록을 메모리에 만들지 않고 디렉터리별로 순회한다."""
    if not data_dir.exists():
        return

    for root, directories, files in os.walk(data_dir):
        directories.sort()
        for filename in sorted(files):
            if filename.lower().endswith(".json"):
                yield Path(root) / filename


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


def parse_aihub_consultations(
    payload: dict[str, Any],
    fallback_id: str,
) -> list[Consultation]:
    """JSON 한 파일의 `qa_data` 목록을 개별 상담 QA로 펼친다."""
    raw_qa_data = payload.get("qa_data")
    if isinstance(raw_qa_data, dict):
        qa_items = [raw_qa_data]
    elif isinstance(raw_qa_data, list):
        qa_items = [item for item in raw_qa_data if isinstance(item, dict)]
    else:
        qa_items = []

    consultations: list[Consultation] = []
    for index, qa_item in enumerate(qa_items, start=1):
        item_payload = dict(payload)
        item_payload["qa_data"] = qa_item
        consultations.append(
            parse_aihub_consultation(
                item_payload,
                f"{fallback_id}_{index:03d}",
            )
        )
    return consultations


def load_aihub_directory(data_dir: Path, limit: int = 200) -> LoadResult:
    """화면용 JSON을 제한된 수만큼 스트리밍 탐색한다."""
    if not data_dir.exists():
        return LoadResult(items=[], loaded_files=0, skipped_files=0)

    items: list[Consultation] = []
    seen_ids: set[str] = set()
    scanned = 0
    duplicates = 0
    invalid = 0
    total_bytes = 0
    reached_limit = False

    for path in iter_json_paths(data_dir):
        if len(items) >= limit:
            reached_limit = True
            break
        scanned += 1
        try:
            total_bytes += path.stat().st_size
            with path.open(encoding="utf-8-sig") as source:
                payload = json.load(source)
            if not isinstance(payload, dict):
                raise ValueError("JSON root must be an object")
            consultations = parse_aihub_consultations(payload, path.stem)
            if not consultations:
                invalid += 1
                continue
            for consultation in consultations:
                if len(items) >= limit:
                    reached_limit = True
                    break
                if consultation.id in seen_ids:
                    duplicates += 1
                    continue
                seen_ids.add(consultation.id)
                items.append(consultation)
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError, TypeError):
            invalid += 1

    return LoadResult(
        items=items,
        loaded_files=len(items),
        skipped_files=duplicates + invalid,
        scanned_files=scanned,
        duplicate_files=duplicates,
        invalid_files=invalid,
        total_bytes=total_bytes,
        reached_limit=reached_limit,
    )
