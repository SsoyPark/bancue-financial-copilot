import re
from dataclasses import dataclass

from .models import Consultation


@dataclass(frozen=True)
class MaskingRule:
    pii_type: str
    placeholder: str
    pattern: re.Pattern[str]


@dataclass(frozen=True)
class MaskingResult:
    text: str
    detected_types: tuple[str, ...]


# 더 구체적인 형식을 먼저 처리해 다른 숫자 규칙이 가로채지 않게 한다.
MASKING_RULES = (
    MaskingRule(
        pii_type="주민등록번호",
        placeholder="[주민등록번호]",
        pattern=re.compile(r"(?<!\d)\d{6}-?[1-4]\d{6}(?!\d)"),
    ),
    MaskingRule(
        pii_type="이메일",
        placeholder="[이메일]",
        # \b는 영문과 한국어를 모두 단어 문자로 보므로 example.com으로 같은
        # 표현에서 경계를 찾지 못한다. 이메일에 허용되는 문자만 경계로 검사한다.
        pattern=re.compile(
            r"(?<![A-Z0-9._%+-])"
            r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}"
            r"(?![A-Z0-9-])",
            re.IGNORECASE,
        ),
    ),
    MaskingRule(
        pii_type="전화번호",
        placeholder="[전화번호]",
        pattern=re.compile(r"(?<!\d)(?:01[016789]|02|0[3-6][1-5])[- ]?\d{3,4}[- ]?\d{4}(?!\d)"),
    ),
    MaskingRule(
        pii_type="계좌번호",
        placeholder="[계좌번호]",
        pattern=re.compile(
            r"(?P<label>계좌(?:번호)?\s*(?:는|은|:)?\s*)"
            r"(?P<value>\d{2,6}(?:[- ]\d{2,6}){1,4})"
        ),
    ),
)


def mask_text(text: str) -> MaskingResult:
    """문자열의 개인정보를 유형별 자리표시자로 치환한다."""
    masked = text
    detected: list[str] = []

    for rule in MASKING_RULES:
        if not rule.pattern.search(masked):
            continue

        if rule.pii_type == "계좌번호":
            masked = rule.pattern.sub(
                lambda match: f"{match.group('label')}{rule.placeholder}", masked
            )
        else:
            masked = rule.pattern.sub(rule.placeholder, masked)
        detected.append(rule.pii_type)

    return MaskingResult(text=masked, detected_types=tuple(detected))


def sanitize_consultation(consultation: Consultation) -> Consultation:
    """상담의 자유 입력 텍스트를 마스킹한 새 객체를 반환한다."""
    text_fields = ("topic", "summary", "question", "intent", "draft")
    updates: dict[str, str | None | bool | list[str]] = {}
    detected: list[str] = []

    for field_name in text_fields:
        value = getattr(consultation, field_name)
        if value is None:
            continue
        result = mask_text(value)
        updates[field_name] = result.text
        for pii_type in result.detected_types:
            if pii_type not in detected:
                detected.append(pii_type)

    updates["pii_masked"] = bool(detected)
    updates["pii_types"] = detected
    return consultation.model_copy(update=updates)
