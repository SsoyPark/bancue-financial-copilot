import json

from app.analytics import profile_database
from app.ingestion import ingest_aihub_directory


def test_profiles_ingested_consultation_data(tmp_path) -> None:
    data_dir = tmp_path / "source"
    data_dir.mkdir()
    payload = {
        "source": {"source_id": "source-1"},
        "consulting": {
            "consulting_category": "은행",
            "consulting_topic": "자동이체조회",
            "consulting_summary": "자동이체 문의",
        },
        "qa_data": [
            {
                "qa_id": "qa-1",
                "consulting_purpose": "자동이체 조회",
                "input": {"question": "자동이체를 조회하고 싶어요."},
                "output": "조회 메뉴를 확인하세요.",
            },
            {
                "qa_id": "qa-2",
                "consulting_purpose": "자동이체 변경",
                "input": {"question": "010-1234-5678로 연락해 주세요."},
                "output": "변경 메뉴를 확인하세요.",
            },
        ],
    }
    (data_dir / "bank.json").write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )
    database_path = tmp_path / "analytics.duckdb"
    ingest_aihub_directory(
        data_dir,
        database_path,
        parquet_output=None,
        report_output=None,
    )

    profile = profile_database(database_path, top_n=5)

    assert profile.total_records == 2
    assert profile.unique_sources == 1
    assert profile.average_qa_per_source == 2.0
    assert profile.maximum_qa_per_source == 2
    assert profile.missing_questions == 0
    assert profile.missing_reference_answers == 0
    assert profile.pii_masked_records == 1
    assert profile.pii_masked_rate == 50.0
    assert profile.question_length.maximum > 0
    assert profile.answer_length.maximum > 0
    assert profile.top_topics[0].topic == "자동이체조회"
    assert profile.top_topics[0].records == 2
