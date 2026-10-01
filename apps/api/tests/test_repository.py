import json

from app.repository import (
    load_aihub_directory,
    parse_aihub_consultation,
    parse_aihub_consultations,
)


def sample_payload() -> dict:
    return {
        "source": {"source_id": "source-1", "consulting_summary": "자동이체 문의"},
        "consulting": {"consulting_topic": "자동이체조회"},
        "qa_data": {
            "qa_id": "qa-1",
            "consulting_purpose": "자동이체 조회",
            "input": {"question": "자동이체를 어디서 확인하나요?"},
            "output": "공식 메뉴를 확인하세요.",
        },
    }


def test_parse_aihub_consultation() -> None:
    consultation = parse_aihub_consultation(sample_payload(), "fallback")
    assert consultation.id == "qa-1"
    assert consultation.topic == "자동이체조회"
    assert consultation.risk.value == "Unknown"
    assert consultation.question == "자동이체를 어디서 확인하나요?"


def test_parse_aihub_qa_list_into_separate_consultations() -> None:
    item = sample_payload()
    second_qa = dict(item["qa_data"])
    second_qa["qa_id"] = "qa-2"
    second_qa["input"] = {"question": "자동이체를 변경하고 싶어요."}
    second_qa["output"] = "변경 메뉴를 확인하세요."
    item["qa_data"] = [item["qa_data"], second_qa]

    consultations = parse_aihub_consultations(item, "fallback")

    assert [consultation.id for consultation in consultations] == ["qa-1", "qa-2"]
    assert consultations[1].question == "자동이체를 변경하고 싶어요."
    assert consultations[1].draft == "변경 메뉴를 확인하세요."


def test_load_directory_skips_invalid_and_duplicate_files(tmp_path) -> None:
    (tmp_path / "valid.json").write_text(
        json.dumps(sample_payload(), ensure_ascii=False), encoding="utf-8"
    )
    (tmp_path / "duplicate.json").write_text(
        json.dumps(sample_payload(), ensure_ascii=False), encoding="utf-8"
    )
    (tmp_path / "invalid.json").write_text("{invalid", encoding="utf-8")

    result = load_aihub_directory(tmp_path)
    assert result.loaded_files == 1
    assert result.skipped_files == 2
    assert result.items[0].id == "qa-1"
