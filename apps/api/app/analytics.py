"""DuckDB에 적재된 상담 QA의 품질과 분포를 집계한다."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import duckdb

from .ingestion import DEFAULT_DATABASE_PATH, DEFAULT_RUNTIME_DIR


DEFAULT_PROFILE_PATH = DEFAULT_RUNTIME_DIR / "data_profile_v2.json"


@dataclass(frozen=True)
class TopicProfile:
    topic: str
    records: int
    share_percent: float


@dataclass(frozen=True)
class LengthProfile:
    average: float
    median: float
    percentile_95: float
    maximum: int


@dataclass(frozen=True)
class DataProfile:
    database: str
    total_records: int
    unique_sources: int
    source_files: int
    average_qa_per_source: float
    maximum_qa_per_source: int
    missing_questions: int
    missing_reference_answers: int
    pii_masked_records: int
    pii_masked_rate: float
    question_length: LengthProfile
    answer_length: LengthProfile
    top_topics: list[TopicProfile] = field(default_factory=list)

    def model_dump(self) -> dict[str, Any]:
        return asdict(self)


def _length_profile(
    connection: duckdb.DuckDBPyConnection,
    column: str,
) -> LengthProfile:
    average, median, percentile_95, maximum = connection.execute(
        f"""
        SELECT
            COALESCE(AVG(LENGTH({column})), 0),
            COALESCE(MEDIAN(LENGTH({column})), 0),
            COALESCE(QUANTILE_CONT(LENGTH({column}), 0.95), 0),
            COALESCE(MAX(LENGTH({column})), 0)
        FROM consultations
        WHERE {column} IS NOT NULL AND {column} != ''
        """
    ).fetchone()
    return LengthProfile(
        average=round(float(average), 2),
        median=round(float(median), 2),
        percentile_95=round(float(percentile_95), 2),
        maximum=int(maximum),
    )


def profile_database(database_path: Path, top_n: int = 10) -> DataProfile:
    if top_n < 1:
        raise ValueError("top_n must be at least 1")
    if not database_path.exists():
        raise FileNotFoundError(f"database not found: {database_path}")

    connection = duckdb.connect(str(database_path), read_only=True)
    try:
        (
            total_records,
            unique_sources,
            source_files,
            missing_questions,
            missing_answers,
            pii_masked_records,
        ) = connection.execute(
            """
            SELECT
                COUNT(*),
                COUNT(DISTINCT source_id),
                COUNT(DISTINCT source_file),
                SUM(CASE WHEN question = '' OR question = '질문 내용 없음' THEN 1 ELSE 0 END),
                SUM(CASE WHEN reference_answer IS NULL OR reference_answer = '' THEN 1 ELSE 0 END),
                SUM(CASE WHEN pii_masked THEN 1 ELSE 0 END)
            FROM consultations
            """
        ).fetchone()

        maximum_qa_per_source = connection.execute(
            """
            SELECT COALESCE(MAX(qa_count), 0)
            FROM (
                SELECT source_id, COUNT(*) AS qa_count
                FROM consultations
                GROUP BY source_id
            )
            """
        ).fetchone()[0]

        topic_rows = connection.execute(
            """
            SELECT topic, COUNT(*) AS records
            FROM consultations
            GROUP BY topic
            ORDER BY records DESC, topic
            LIMIT ?
            """,
            [top_n],
        ).fetchall()
        top_topics = [
            TopicProfile(
                topic=str(topic),
                records=int(records),
                share_percent=(
                    round(int(records) / int(total_records) * 100, 2)
                    if total_records
                    else 0.0
                ),
            )
            for topic, records in topic_rows
        ]

        return DataProfile(
            database=str(database_path),
            total_records=int(total_records),
            unique_sources=int(unique_sources),
            source_files=int(source_files),
            average_qa_per_source=(
                round(int(total_records) / int(unique_sources), 2)
                if unique_sources
                else 0.0
            ),
            maximum_qa_per_source=int(maximum_qa_per_source),
            missing_questions=int(missing_questions),
            missing_reference_answers=int(missing_answers),
            pii_masked_records=int(pii_masked_records),
            pii_masked_rate=(
                round(int(pii_masked_records) / int(total_records) * 100, 4)
                if total_records
                else 0.0
            ),
            question_length=_length_profile(connection, "question"),
            answer_length=_length_profile(connection, "reference_answer"),
            top_topics=top_topics,
        )
    finally:
        connection.close()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="BANCUE DuckDB 상담 데이터의 품질과 분포를 분석합니다."
    )
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_PROFILE_PATH)
    parser.add_argument("--top-n", type=int, default=10)
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    profile = profile_database(args.database, top_n=args.top_n)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(profile.model_dump(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(profile.model_dump(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
