from app.models import Consultation, ConsultationStatus, RiskLevel
from app.pii import mask_text, sanitize_consultation


def consultation(question: str, draft: str | None = None) -> Consultation:
    return Consultation(
        id="test-pii-1",
        customer="고객",
        topic="개인정보 테스트",
        summary="연락처 확인",
        question=question,
        risk=RiskLevel.UNKNOWN,
        status=ConsultationStatus.RECEIVED,
        waiting_time="00:00",
        intent="연락처 확인",
        draft=draft,
    )


def test_masks_multiple_pii_types() -> None:
    original = (
        "연락처는 010-1234-5678, 이메일은 test.user@example.com, "
        "주민번호는 900101-1234567입니다."
    )
    result = mask_text(original)

    assert result.text == "연락처는 [전화번호], 이메일은 [이메일], 주민번호는 [주민등록번호]입니다."
    assert set(result.detected_types) == {"전화번호", "이메일", "주민등록번호"}


def test_masks_labeled_account_number() -> None:
    result = mask_text("환불받을 계좌번호는 110-123-456789입니다.")
    assert result.text == "환불받을 계좌번호는 [계좌번호]입니다."
    assert result.detected_types == ("계좌번호",)


def test_sanitizes_question_and_draft() -> None:
    result = sanitize_consultation(
        consultation("010-1234-5678로 연락해 주세요.", "sample@example.com으로 안내했습니다.")
    )

    assert result.question == "[전화번호]로 연락해 주세요."
    assert result.draft == "[이메일]으로 안내했습니다."
    assert result.pii_masked is True
    assert result.pii_types == ["전화번호", "이메일"]


def test_masks_email_followed_by_korean_particle() -> None:
    result = mask_text("sample@example.com으로 안내했습니다.")
    assert result.text == "[이메일]으로 안내했습니다."
    assert result.detected_types == ("이메일",)


def test_keeps_non_pii_numbers() -> None:
    result = mask_text("처리 예정일은 2026-08-21이고 수수료는 3회 분할입니다.")
    assert result.text == "처리 예정일은 2026-08-21이고 수수료는 3회 분할입니다."
    assert result.detected_types == ()
