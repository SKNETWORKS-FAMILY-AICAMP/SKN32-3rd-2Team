"""이름 → 프로바이더 인스턴스.

인스턴스는 캐시한다. HTTP 커넥션 풀을 요청마다 새로 만들면 지연이 늘어나
성능 보고서 수치가 왜곡된다.
"""

from __future__ import annotations

from app.config import get_settings
from app.errors import ProviderNotConfigured
from app.providers.base import LLMProvider

_cache: dict[str, LLMProvider] = {}

SUPPORTED = ("openai", "gemini")


def get_provider(name: str | None = None) -> LLMProvider:
    settings = get_settings()
    resolved = name or settings.default_provider

    if resolved not in SUPPORTED:
        raise ProviderNotConfigured(f"지원하지 않는 프로바이더입니다: {resolved}")

    if resolved in _cache:
        return _cache[resolved]

    if settings.llm_mode == "mock":
        from app.providers.mock_provider import MockProvider

        provider: LLMProvider = MockProvider(alias=resolved)
    elif resolved == "openai":
        from app.providers.openai_provider import OpenAIProvider

        provider = OpenAIProvider()
    else:
        from app.providers.gemini_provider import GeminiProvider

        provider = GeminiProvider()

    _cache[resolved] = provider
    return provider


def reset_cache() -> None:
    """테스트/설정 변경용."""
    _cache.clear()
