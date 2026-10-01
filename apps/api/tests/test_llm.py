import httpx
import pytest

from app.llm import GeminiClient, LLMGenerationError


class FakeResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {
            "candidates": [
                {
                    "finishReason": "STOP",
                    "content": {
                        "parts": [{"text": "검증 근거 기반 답변입니다."}]
                    }
                }
            ]
        }


def test_gemini_client_requires_api_key() -> None:
    client = GeminiClient(api_key="")

    with pytest.raises(LLMGenerationError, match="GEMINI_API_KEY"):
        client.generate("시스템", "질문")


def test_gemini_client_sends_key_in_header_and_parses_text(monkeypatch) -> None:
    captured: dict = {}

    def fake_post(url, *, headers, json, timeout):
        captured.update(
            {"url": url, "headers": headers, "json": json, "timeout": timeout}
        )
        return FakeResponse()

    monkeypatch.setattr(httpx, "post", fake_post)
    client = GeminiClient(api_key="secret-test-key", model="gemini-test")

    result = client.generate("근거만 사용", "자동이체 질문")

    assert result.text == "검증 근거 기반 답변입니다."
    assert result.model == "gemini-test"
    assert captured["headers"]["x-goog-api-key"] == "secret-test-key"
    assert "secret-test-key" not in captured["url"]
    assert captured["json"]["systemInstruction"]["parts"][0]["text"] == "근거만 사용"
    assert captured["json"]["contents"][0]["parts"][0]["text"] == "자동이체 질문"
    assert captured["json"]["generationConfig"]["maxOutputTokens"] == 2048
    assert captured["json"]["generationConfig"]["thinkingConfig"] == {
        "thinkingLevel": "MINIMAL"
    }


def test_gemini_client_rejects_incomplete_response(monkeypatch) -> None:
    class TruncatedResponse(FakeResponse):
        def json(self) -> dict:
            return {
                "candidates": [
                    {
                        "finishReason": "MAX_TOKENS",
                        "content": {"parts": [{"text": "문장이 끝나지 않은"}]},
                    }
                ]
            }

    monkeypatch.setattr(httpx, "post", lambda *args, **kwargs: TruncatedResponse())
    client = GeminiClient(api_key="secret-test-key", model="gemini-test")

    with pytest.raises(LLMGenerationError, match="MAX_TOKENS"):
        client.generate("시스템", "질문")
