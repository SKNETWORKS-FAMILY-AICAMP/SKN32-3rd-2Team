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
    llm_service_port: int = 8002
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
    gemini_model: str = "gemini-3.5-flash"

    # --- Qwen (로컬 오픈소스, Ollama 경유) ---
    # 상용 API 와의 비교용. 키가 필요 없는 대신 로컬에 Ollama 가 떠 있어야 한다.
    qwen_base_url: str = "http://localhost:11434"
    qwen_model: str = "qwen2.5:7b"
    # Ollama 는 기본 5분 미사용 시 모델을 메모리에서 내린다. 그러면 다음 호출이
    # 모델 로딩(실측 4초)을 다시 문다. 시연 중 잠깐 쉬면 그대로 드러나므로
    # 넉넉히 잡아 상주시킨다. VRAM 4.75GB 를 계속 점유한다(8GB 중).
    qwen_keep_alive: str = "30m"

    # --- 주제 분류 방법 ---
    # llm   : 현행. 프로바이더에 enum 제약 호출을 한 번 더 보낸다
    # embed : 질문 임베딩과 카테고리 임베딩의 유사도로 분류. API 호출 없음
    topic_method: Literal["llm", "embed"] = "llm"
    topic_embed_model: str = "jhgan/ko-sroberta-multitask"

    # --- RAG ---
    rag_mode: Literal["live", "mock"] = "mock"
    rag_base_url: str = "http://localhost:8001"
    rag_timeout_sec: float = 3.0
    rag_top_k: int = 5

    # --- 계측 ---
    metrics_path: str = "logs/metrics.jsonl"
    metrics_enabled: bool = True

    def is_configured(self, provider: str) -> bool:
        if self.llm_mode == "mock":
            return True
        # 로컬 프로바이더는 API 키가 없다. 키 유무로 판단하면 항상 미설정이 된다.
        from app.providers.registry import KEYLESS

        if provider in KEYLESS:
            return True
        return bool(getattr(self, f"{provider}_api_key", ""))

    @property
    def metrics_file(self) -> Path:
        p = Path(self.metrics_path)
        return p if p.is_absolute() else LLM_DIR / p


@lru_cache
def get_settings() -> Settings:
    return Settings()
