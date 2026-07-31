"""환경설정. 값은 전부 .env 에서만 온다 (키 하드코딩 금지)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

LLM_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=LLM_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- 서비스 ---
    llm_service_port: int = 8001
    default_provider: Literal["openai", "gemini"] = "openai"
    llm_timeout_sec: float = 5.0

    # live = 실제 API 호출 / mock = 고정 응답.
    # API 키 없이도 팀원이 UI를 붙여볼 수 있게 하는 용도. 공개 API 계약은 동일하다.
    llm_mode: Literal["live", "mock"] = "live"

    # --- OpenAI ---
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    # --- Gemini ---
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"

    # --- RAG ---
    rag_mode: Literal["live", "mock"] = "mock"
    rag_base_url: str = "http://localhost:8002"
    rag_timeout_sec: float = 3.0
    rag_top_k: int = 5

    # --- 계측 ---
    metrics_path: str = "bench/results/metrics.jsonl"
    metrics_enabled: bool = True

    def is_configured(self, provider: str) -> bool:
        if self.llm_mode == "mock":
            return True
        return bool(getattr(self, f"{provider}_api_key", ""))

    @property
    def metrics_file(self) -> Path:
        p = Path(self.metrics_path)
        return p if p.is_absolute() else LLM_DIR / p


@lru_cache
def get_settings() -> Settings:
    return Settings()
