import os
import time
from dataclasses import dataclass
from typing import Any, Protocol

import httpx


DEFAULT_GEMINI_MODEL = "gemini-3.6-flash"
DEFAULT_GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta"


class LLMGenerationError(RuntimeError):
    """LLM 응답을 안전한 답변 초안으로 사용할 수 없을 때 발생한다."""


@dataclass(frozen=True)
class LLMTextResponse:
    text: str
    model: str
    latency_ms: int
    finish_reason: str = "STOP"


class DraftLLM(Protocol):
    model: str

    @property
    def configured(self) -> bool: ...

    def generate(self, system_instruction: str, prompt: str) -> LLMTextResponse: ...


class GeminiClient:
    """추가 SDK 없이 Gemini generateContent REST API를 호출한다."""

    def __init__(
        self,
        api_key: str = "",
        model: str = DEFAULT_GEMINI_MODEL,
        endpoint: str = DEFAULT_GEMINI_ENDPOINT,
        timeout_seconds: float = 30.0,
    ) -> None:
        self.api_key = api_key.strip()
        self.model = model.strip() or DEFAULT_GEMINI_MODEL
        self.endpoint = endpoint.rstrip("/")
        self.timeout_seconds = timeout_seconds

    @classmethod
    def from_env(cls) -> "GeminiClient":
        return cls(
            api_key=os.getenv("GEMINI_API_KEY", ""),
            model=os.getenv("BANCUE_GEMINI_MODEL", DEFAULT_GEMINI_MODEL),
            endpoint=os.getenv("BANCUE_GEMINI_ENDPOINT", DEFAULT_GEMINI_ENDPOINT),
            timeout_seconds=float(os.getenv("BANCUE_LLM_TIMEOUT_SECONDS", "30")),
        )

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def generate(self, system_instruction: str, prompt: str) -> LLMTextResponse:
        if not self.configured:
            raise LLMGenerationError("GEMINI_API_KEY가 설정되지 않았습니다.")

        payload = {
            "systemInstruction": {"parts": [{"text": system_instruction}]},
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": prompt}],
                }
            ],
            "generationConfig": {
                "maxOutputTokens": 2048,
                "thinkingConfig": {"thinkingLevel": "MINIMAL"},
            },
        }
        started = time.perf_counter()
        try:
            response = httpx.post(
                f"{self.endpoint}/models/{self.model}:generateContent",
                headers={
                    "Content-Type": "application/json",
                    "x-goog-api-key": self.api_key,
                },
                json=payload,
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            body: dict[str, Any] = response.json()
        except (httpx.HTTPError, ValueError, TypeError) as error:
            raise LLMGenerationError(f"Gemini 호출 실패: {error}") from error

        try:
            candidate = body["candidates"][0]
            finish_reason = str(candidate.get("finishReason", "")).upper()
            parts = candidate["content"]["parts"]
            text = "\n".join(
                part["text"].strip()
                for part in parts
                if isinstance(part, dict) and isinstance(part.get("text"), str)
            ).strip()
        except (KeyError, IndexError, TypeError) as error:
            raise LLMGenerationError("Gemini 응답에서 텍스트를 찾지 못했습니다.") from error
        if not text:
            raise LLMGenerationError("Gemini가 빈 답변을 반환했습니다.")
        if finish_reason and finish_reason != "STOP":
            raise LLMGenerationError(
                f"Gemini 응답이 완결되지 않았습니다: {finish_reason}"
            )

        return LLMTextResponse(
            text=text,
            model=self.model,
            latency_ms=round((time.perf_counter() - started) * 1000),
            finish_reason=finish_reason or "STOP",
        )
