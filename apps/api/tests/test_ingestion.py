import json
import zipfile

import duckdb

from app.ingestion import ingest_aihub_directory


def payload(qa_id: str, question: str) -> dict:
    return {
        "source": {
            "source_id": f"source-{qa_id}",
            "consulting_summary": "자동이체 문의",
        },
        "consulting": {
            "consulting_category": "은행",
            "consulting_topic": "자동이체조회",
        },
        "qa_data": {
            "qa_id": qa_id,
            "consulting_purpose": "자동이체 조회",
            "input": {"question": question},
            "output": "공식 메뉴를 확인하세요.",
        },
    }


def insurance_payload(qa_id: str, question: str) -> dict:
    item = payload(qa_id, question)
    item["consulting"]["consulting_category"] = "보험"
    return item


def qa_list_payload() -> dict:
    item = payload("qa-1", "자동이체 조회")
    second_qa = dict(item["qa_data"])
    second_qa["qa_id"] = "qa-2"
    second_qa["input"] = {"question": "자동이체 변경"}
    second_qa["output"] = "변경 메뉴를 확인하세요."
    item["qa_data"] = [item["qa_data"], second_qa]
    return item


def test_ingestion_batches_masks_and_deduplicates(tmp_path) -> None:
    data_dir = tmp_path / "source"
    data_dir.mkdir()
    (data_dir / "001.json").write_text(
        json.dumps(payload("qa-1", "010-1234-5678로 연락해 주세요."), ensure_ascii=False),
        encoding="utf-8",
    )
    (data_dir / "002.json").write_text(
        json.dumps(payload("qa-2", "자동이체를 확인하고 싶어요."), ensure_ascii=False),
        encoding="utf-8",
    )
    (data_dir / "003-duplicate.json").write_text(
        json.dumps(payload("qa-1", "중복 상담입니다."), ensure_ascii=False),
        encoding="utf-8",
    )
    (data_dir / "004-invalid.json").write_text("{invalid", encoding="utf-8")

    database_path = tmp_path / "analytics.duckdb"
    parquet_path = tmp_path / "consultations.parquet"
    report_path = tmp_path / "ingestion_report.json"
    report = ingest_aihub_directory(
        data_dir,
        database_path,
        parquet_output=parquet_path,
        report_output=report_path,
        batch_size=2,
    )

    assert report.scanned_files == 4
    assert report.parsed_records == 3
    assert report.inserted_records == 2
    assert report.duplicate_records == 1
    assert report.invalid_files == 1
    assert report.pii_masked_records == 1
    assert report.database_records == 2
    assert parquet_path.exists()
    assert report_path.exists()

    connection = duckdb.connect(str(database_path), read_only=True)
    try:
        question, pii_masked = connection.execute(
            """
            SELECT question, pii_masked
            FROM consultations
            WHERE consultation_id = 'qa-1'
            """
        ).fetchone()
    finally:
        connection.close()

    assert question == "[전화번호]로 연락해 주세요."
    assert pii_masked is True


def test_ingestion_is_idempotent(tmp_path) -> None:
    data_dir = tmp_path / "source"
    data_dir.mkdir()
    (data_dir / "001.json").write_text(
        json.dumps(payload("qa-1", "자동이체 조회"), ensure_ascii=False),
        encoding="utf-8",
    )
    database_path = tmp_path / "analytics.duckdb"

    first = ingest_aihub_directory(
        data_dir,
        database_path,
        parquet_output=None,
        report_output=None,
        batch_size=1,
    )
    second = ingest_aihub_directory(
        data_dir,
        database_path,
        parquet_output=None,
        report_output=None,
        batch_size=1,
    )

    assert first.inserted_records == 1
    assert second.inserted_records == 0
    assert second.duplicate_records == 1
    assert second.database_records == 1


def test_ingestion_reads_json_inside_zip_without_extracting(tmp_path) -> None:
    data_dir = tmp_path / "source"
    data_dir.mkdir()
    archive_path = data_dir / "training.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr(
            "bank/001.json",
            json.dumps(payload("qa-1", "자동이체 조회"), ensure_ascii=False),
        )
        archive.writestr(
            "bank/002.json",
            json.dumps(payload("qa-2", "카드 분실"), ensure_ascii=False),
        )
        archive.writestr("bank/003-invalid.json", "{invalid")
        archive.writestr(
            "insurance/004.json",
            json.dumps(insurance_payload("qa-3", "보험 문의"), ensure_ascii=False),
        )
        archive.writestr("bank/readme.txt", "not a consultation")

    database_path = tmp_path / "analytics.duckdb"
    report = ingest_aihub_directory(
        data_dir,
        database_path,
        parquet_output=None,
        report_output=None,
        batch_size=2,
    )

    assert report.scanned_files == 4
    assert report.parsed_records == 2
    assert report.inserted_records == 2
    assert report.invalid_files == 1
    assert report.archive_files == 1
    assert report.compressed_json_records == 4
    assert report.filtered_records == 1
    assert report.database_records == 2


def test_ingestion_expands_qa_list_and_skips_source_only_json(tmp_path) -> None:
    data_dir = tmp_path / "source"
    data_dir.mkdir()
    archive_path = data_dir / "training.zip"
    source_only = qa_list_payload()
    source_only.pop("qa_data")
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr(
            "bank/labeled.json",
            json.dumps(qa_list_payload(), ensure_ascii=False),
        )
        archive.writestr(
            "bank/source.json",
            json.dumps(source_only, ensure_ascii=False),
        )

    database_path = tmp_path / "analytics.duckdb"
    report = ingest_aihub_directory(
        data_dir,
        database_path,
        parquet_output=None,
        report_output=None,
        batch_size=2,
    )

    assert report.parsed_records == 2
    assert report.inserted_records == 2
    assert report.source_only_records == 1
    assert report.missing_question_records == 0
    assert report.reference_answer_records == 2
    assert report.database_records == 2

    connection = duckdb.connect(str(database_path), read_only=True)
    try:
        rows = connection.execute(
            """
            SELECT consultation_id, source_id, reference_answer
            FROM consultations
            ORDER BY consultation_id
            """
        ).fetchall()
    finally:
        connection.close()

    assert rows == [
        ("qa-1", "source-qa-1", "공식 메뉴를 확인하세요."),
        ("qa-2", "source-qa-1", "변경 메뉴를 확인하세요."),
    ]
