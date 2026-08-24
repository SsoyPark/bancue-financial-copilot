"""AI Hub 상담 JSON을 분석용 DuckDB와 Parquet으로 적재하는 배치 파이프라인."""

from __future__ import annotations

import argparse
import io
import json
import os
import time
import zipfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterator, Sequence

import duckdb

from .models import Consultation
from .pii import sanitize_consultation
from .repository import parse_aihub_consultations


DEFAULT_RUNTIME_DIR = Path(__file__).resolve().parents[1] / "data" / "runtime"
DEFAULT_DATABASE_PATH = DEFAULT_RUNTIME_DIR / "bancue_analytics_v2.duckdb"
DEFAULT_PARQUET_PATH = DEFAULT_RUNTIME_DIR / "consultations_v2.parquet"
DEFAULT_REPORT_PATH = DEFAULT_RUNTIME_DIR / "ingestion_report_v2.json"
MAX_RECORDED_ERRORS = 20


@dataclass(frozen=True)
class IngestionError:
    source_file: str
    error_type: str


@dataclass(frozen=True)
class JsonInput:
    source_file: str
    byte_size: int
    payload: dict[str, Any] | None
    error_type: str | None = None
    archive_file: str | None = None


@dataclass(frozen=True)
class IngestionReport:
    data_dir: str
    domain: str
    output_database: str
    parquet_output: str | None
    scanned_files: int
    parsed_records: int
    inserted_records: int
    duplicate_records: int
    invalid_files: int
    archive_files: int
    compressed_json_records: int
    filtered_records: int
    source_only_records: int
    pii_masked_records: int
    missing_question_records: int
    reference_answer_records: int
    database_records: int
    total_input_bytes: int
    batch_size: int
    limit: int | None
    reached_limit: bool
    duration_seconds: float
    records_per_second: float
    errors: list[IngestionError] = field(default_factory=list)

    def model_dump(self) -> dict[str, Any]:
        return asdict(self)


def _iter_input_paths(data_dir: Path) -> Iterator[Path]:
    """느슨한 JSON과 ZIP 경로를 전체 목록 생성 없이 순회한다."""
    for root, directories, files in os.walk(data_dir):
        directories.sort()
        for filename in sorted(files):
            path = Path(root) / filename
            if path.suffix.casefold() in {".json", ".zip"}:
                yield path


def _load_json_stream(source: Any) -> dict[str, Any]:
    payload = json.load(source)
    if not isinstance(payload, dict):
        raise ValueError("JSON root must be an object")
    return payload


def _iter_json_inputs(data_dir: Path) -> Iterator[JsonInput]:
    """압축 해제 없이 일반 JSON과 ZIP 내부 JSON을 한 건씩 읽는다."""
    for path in _iter_input_paths(data_dir):
        relative_path = str(path.relative_to(data_dir))
        if path.suffix.casefold() == ".json":
            try:
                with path.open(encoding="utf-8-sig") as source:
                    payload = _load_json_stream(source)
                yield JsonInput(
                    source_file=relative_path,
                    byte_size=path.stat().st_size,
                    payload=payload,
                )
            except (
                OSError,
                UnicodeError,
                json.JSONDecodeError,
                ValueError,
                TypeError,
            ) as error:
                yield JsonInput(
                    source_file=relative_path,
                    byte_size=0,
                    payload=None,
                    error_type=type(error).__name__,
                )
            continue

        try:
            with zipfile.ZipFile(path) as archive:
                members = sorted(
                    (
                        member
                        for member in archive.infolist()
                        if not member.is_dir()
                        and Path(member.filename).suffix.casefold() == ".json"
                    ),
                    key=lambda member: member.filename,
                )
                for member in members:
                    source_file = f"{relative_path}!/{member.filename}"
                    try:
                        with archive.open(member) as binary_source:
                            with io.TextIOWrapper(
                                binary_source,
                                encoding="utf-8-sig",
                            ) as source:
                                payload = _load_json_stream(source)
                        yield JsonInput(
                            source_file=source_file,
                            byte_size=member.file_size,
                            payload=payload,
                            archive_file=relative_path,
                        )
                    except (
                        OSError,
                        UnicodeError,
                        json.JSONDecodeError,
                        ValueError,
                        TypeError,
                        RuntimeError,
                    ) as error:
                        yield JsonInput(
                            source_file=source_file,
                            byte_size=member.file_size,
                            payload=None,
                            error_type=type(error).__name__,
                            archive_file=relative_path,
                        )
        except (OSError, zipfile.BadZipFile, RuntimeError) as error:
            yield JsonInput(
                source_file=relative_path,
                byte_size=0,
                payload=None,
                error_type=type(error).__name__,
                archive_file=relative_path,
            )


def _matches_domain(
    payload: dict[str, Any],
    source_file: str,
    domain: str,
) -> bool:
    if domain == "all":
        return True

    consulting = payload.get("consulting")
    category = (
        consulting.get("consulting_category", "")
        if isinstance(consulting, dict)
        else ""
    )
    normalized_category = str(category).strip().casefold()
    if normalized_category:
        return normalized_category in {"은행", "bank", "bk"}

    normalized_source = source_file.casefold().replace("\\", "/")
    return any(
        marker in normalized_source
        for marker in ("_bk_", "/bk/", "bank", "은행")
    )


def _create_schema(connection: duckdb.DuckDBPyConnection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS consultations (
            consultation_id VARCHAR PRIMARY KEY,
            source_id VARCHAR NOT NULL,
            topic VARCHAR NOT NULL,
            summary VARCHAR NOT NULL,
            question VARCHAR NOT NULL,
            intent VARCHAR NOT NULL,
            reference_answer VARCHAR,
            source_file VARCHAR NOT NULL,
            pii_masked BOOLEAN NOT NULL,
            pii_types VARCHAR NOT NULL,
            ingested_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def _consultation_row(
    consultation: Consultation,
    source_id: str,
    source_file: str,
) -> tuple[Any, ...]:
    return (
        consultation.id,
        source_id,
        consultation.topic,
        consultation.summary,
        consultation.question,
        consultation.intent,
        consultation.draft,
        source_file,
        consultation.pii_masked,
        json.dumps(consultation.pii_types, ensure_ascii=False),
    )


def _insert_batch(
    connection: duckdb.DuckDBPyConnection,
    rows: Sequence[tuple[Any, ...]],
) -> int:
    if not rows:
        return 0

    before = connection.execute("SELECT COUNT(*) FROM consultations").fetchone()[0]
    connection.executemany(
        """
        INSERT OR IGNORE INTO consultations (
            consultation_id,
            source_id,
            topic,
            summary,
            question,
            intent,
            reference_answer,
            source_file,
            pii_masked,
            pii_types
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    after = connection.execute("SELECT COUNT(*) FROM consultations").fetchone()[0]
    return int(after - before)


def _export_parquet(
    connection: duckdb.DuckDBPyConnection,
    parquet_path: Path,
) -> None:
    parquet_path.parent.mkdir(parents=True, exist_ok=True)
    escaped_path = str(parquet_path.resolve()).replace("'", "''")
    connection.execute(
        f"""
        COPY (
            SELECT
                consultation_id,
                source_id,
                topic,
                summary,
                question,
                intent,
                reference_answer,
                source_file,
                pii_masked,
                pii_types
            FROM consultations
            ORDER BY consultation_id
        ) TO '{escaped_path}' (FORMAT PARQUET, COMPRESSION ZSTD)
        """
    )


def ingest_aihub_directory(
    data_dir: Path,
    output_database: Path = DEFAULT_DATABASE_PATH,
    *,
    parquet_output: Path | None = DEFAULT_PARQUET_PATH,
    report_output: Path | None = DEFAULT_REPORT_PATH,
    batch_size: int = 500,
    limit: int | None = None,
    domain: str = "bank",
) -> IngestionReport:
    """JSON을 순차 마스킹하고 고정 크기 배치로 분석 저장소에 적재한다."""
    if batch_size < 1:
        raise ValueError("batch_size must be at least 1")
    if limit is not None and limit < 1:
        raise ValueError("limit must be at least 1 or None")
    if domain not in {"bank", "all"}:
        raise ValueError("domain must be 'bank' or 'all'")
    if not data_dir.exists():
        raise FileNotFoundError(f"data directory not found: {data_dir}")

    started_at = time.perf_counter()
    output_database.parent.mkdir(parents=True, exist_ok=True)
    connection = duckdb.connect(str(output_database))
    _create_schema(connection)

    scanned_files = 0
    parsed_records = 0
    inserted_records = 0
    invalid_files = 0
    archive_files: set[str] = set()
    compressed_json_records = 0
    filtered_records = 0
    source_only_records = 0
    pii_masked_records = 0
    missing_question_records = 0
    reference_answer_records = 0
    total_input_bytes = 0
    reached_limit = False
    errors: list[IngestionError] = []
    rows: list[tuple[Any, ...]] = []

    try:
        for json_input in _iter_json_inputs(data_dir):
            if limit is not None and parsed_records >= limit:
                reached_limit = True
                break

            scanned_files += 1
            total_input_bytes += json_input.byte_size
            if json_input.archive_file:
                archive_files.add(json_input.archive_file)
                compressed_json_records += 1

            if json_input.error_type or json_input.payload is None:
                invalid_files += 1
                if len(errors) < MAX_RECORDED_ERRORS:
                    errors.append(
                        IngestionError(
                            source_file=json_input.source_file,
                            error_type=json_input.error_type or "UnknownError",
                        )
                    )
                continue

            if not _matches_domain(
                json_input.payload,
                json_input.source_file,
                domain,
            ):
                filtered_records += 1
                continue

            try:
                consultations = parse_aihub_consultations(
                    json_input.payload,
                    Path(json_input.source_file).stem,
                )
                if not consultations:
                    source_only_records += 1
                    continue

                source = json_input.payload.get("source")
                source_id = (
                    str(source.get("source_id", "")).strip()
                    if isinstance(source, dict)
                    else ""
                )
                for consultation_item in consultations:
                    if limit is not None and parsed_records >= limit:
                        reached_limit = True
                        break
                    consultation = sanitize_consultation(consultation_item)
                    parsed_records += 1
                    pii_masked_records += int(consultation.pii_masked)
                    missing_question_records += int(
                        consultation.question == "질문 내용 없음"
                    )
                    reference_answer_records += int(bool(consultation.draft))
                    rows.append(
                        _consultation_row(
                            consultation,
                            source_id or consultation.id,
                            json_input.source_file,
                        )
                    )
            except (
                ValueError,
                TypeError,
            ) as error:
                invalid_files += 1
                if len(errors) < MAX_RECORDED_ERRORS:
                    errors.append(
                        IngestionError(
                            source_file=json_input.source_file,
                            error_type=type(error).__name__,
                        )
                    )
                continue

            if reached_limit:
                break

            if len(rows) >= batch_size:
                inserted_records += _insert_batch(connection, rows)
                rows.clear()

        if rows:
            inserted_records += _insert_batch(connection, rows)

        database_records = int(
            connection.execute("SELECT COUNT(*) FROM consultations").fetchone()[0]
        )
        if parquet_output is not None:
            _export_parquet(connection, parquet_output)
    finally:
        connection.close()

    duration_seconds = round(time.perf_counter() - started_at, 4)
    duplicate_records = parsed_records - inserted_records
    report = IngestionReport(
        data_dir=str(data_dir),
        domain=domain,
        output_database=str(output_database),
        parquet_output=str(parquet_output) if parquet_output else None,
        scanned_files=scanned_files,
        parsed_records=parsed_records,
        inserted_records=inserted_records,
        duplicate_records=duplicate_records,
        invalid_files=invalid_files,
        archive_files=len(archive_files),
        compressed_json_records=compressed_json_records,
        filtered_records=filtered_records,
        source_only_records=source_only_records,
        pii_masked_records=pii_masked_records,
        missing_question_records=missing_question_records,
        reference_answer_records=reference_answer_records,
        database_records=database_records,
        total_input_bytes=total_input_bytes,
        batch_size=batch_size,
        limit=limit,
        reached_limit=reached_limit,
        duration_seconds=duration_seconds,
        records_per_second=(
            round(parsed_records / duration_seconds, 2)
            if duration_seconds > 0
            else 0.0
        ),
        errors=errors,
    )

    if report_output is not None:
        report_output.parent.mkdir(parents=True, exist_ok=True)
        report_output.write_text(
            json.dumps(report.model_dump(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="AI Hub 금융 상담 JSON을 DuckDB와 Parquet으로 배치 적재합니다."
    )
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--output-db", type=Path, default=DEFAULT_DATABASE_PATH)
    parser.add_argument("--parquet-output", type=Path, default=DEFAULT_PARQUET_PATH)
    parser.add_argument("--report-output", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--domain", choices=("bank", "all"), default="bank")
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    report = ingest_aihub_directory(
        data_dir=args.data_dir,
        output_database=args.output_db,
        parquet_output=args.parquet_output,
        report_output=args.report_output,
        batch_size=args.batch_size,
        limit=args.limit,
        domain=args.domain,
    )
    print(json.dumps(report.model_dump(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
