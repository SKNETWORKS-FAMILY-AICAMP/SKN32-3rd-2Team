"""API 계약의 단일 출처.

여기 정의된 모델이 그대로 FastAPI 자동 문서(/docs)와 docs/API.md 가 된다.
챗봇 서버(Member B, port 8000)가 이 스키마에 맞춰 붙는다.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.domain import TOPIC_CATEGORIES

ProviderName = Literal["openai", "gemini"]
Speaker = Literal["user", "llm"]


class HistoryTurn(BaseModel):
    """이전 대화 한 턴. `chat` 테이블 행과 1:1 대응."""

    speaker: Speaker
    message: str


class Source(BaseModel):
    """답변의 근거 문서. 스토리보드 13p '답변 하단 근거 문서명 노출'용."""

    doc_id: int | None = Field(None, description="document.doc_id. RAG가 알려주지 않으면 null")
    original_file_name: str = Field(..., description="document.original_file_name")
    page: int | None = Field(None, description="근거가 위치한 페이지")
    snippet: str | None = Field(None, description="인용 구간 일부")
    score: float | None = Field(None, description="검색 유사도 점수")


class Usage(BaseModel):
    """계측값. 성능 보고서 입력이자 디버깅용."""

    provider: ProviderName
    model: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    latency_ms: int
    ttft_ms: int | None = Field(None, description="첫 토큰까지 걸린 시간. 스트리밍에서만 측정")
    rag_ms: int | None = Field(None, description="RAG 검색에 걸린 시간")


class ChatRequest(BaseModel):
    chatroom_id: str = Field(..., description="chatroom.chatroom_id (UUID)")
    message: str = Field(..., min_length=1, description="사용자 질문")
    history: list[HistoryTurn] = Field(
        default_factory=list,
        description="이전 대화. 최근 N턴만 보내면 된다(전체를 보낼 필요 없음).",
    )
    provider: ProviderName | None = Field(
        None, description="미지정 시 서버 기본값(DEFAULT_PROVIDER) 사용"
    )
    use_rag: bool = Field(True, description="false면 문서 검색 없이 답변")
    generate_name: bool = Field(
        False,
        description=(
            "채팅방의 첫 질문일 때 true. 응답의 chatroom_name 으로 "
            "chatroom.chatroom_name 을 갱신하면 된다. "
            "답변 생성과 병렬로 처리되므로 지연이 늘지 않는다."
        ),
    )


class ChatResponse(BaseModel):
    answer: str = Field(..., description="chat.message 에 그대로 저장")
    sources: list[Source] = Field(
        default_factory=list,
        description="근거 문서. RAG 실패 시에도 500 대신 빈 배열로 응답한다.",
    )
    topic: str = Field(
        ...,
        description=f"chat.topic 에 그대로 저장. 항상 다음 중 하나: {', '.join(TOPIC_CATEGORIES)}",
    )
    rag_degraded: bool = Field(
        False, description="true면 RAG 검색에 실패해 문서 없이 생성된 답변"
    )
    chatroom_name: str | None = Field(
        None,
        description=(
            "요청에 generate_name=true 를 넣었을 때만 채워진다. "
            "chatroom.chatroom_name 에 그대로 저장 (100자 이내 보장). "
            "generate_name 을 안 넣었으면 null 이며, 채팅방 이름은 건드리지 않으면 된다."
        ),
    )
    usage: Usage


class TopicRequest(BaseModel):
    message: str = Field(..., min_length=1)
    source_files: list[str] = Field(
        default_factory=list,
        description="선택. RAG가 찾은 문서명을 넣으면 분류 힌트로 쓴다.",
    )
    provider: ProviderName | None = None


class TopicResponse(BaseModel):
    topic: str = Field(..., description=f"항상 다음 중 하나: {', '.join(TOPIC_CATEGORIES)}")
    cached: bool = Field(False, description="동일 질문 캐시 적중 여부")


class ChatroomNameRequest(BaseModel):
    message: str = Field(..., min_length=1, description="해당 채팅방의 첫 질문")
    provider: ProviderName | None = None


class ChatroomNameResponse(BaseModel):
    name: str = Field(..., description="chatroom.chatroom_name 에 그대로 저장 (100자 이내)")


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    providers: dict[str, bool] = Field(..., description="프로바이더별 API 키 설정 여부")
    default_provider: ProviderName
    rag: Literal["up", "down", "mock"]
    topic_categories: list[str] = Field(
        ..., description="현재 서버가 쓰는 카테고리 목록. 대시보드가 이걸 읽어 차트 축을 맞출 수 있다."
    )


class ErrorResponse(BaseModel):
    """에러는 항상 이 형태. `message` 는 프론트가 그대로 출력 가능한 한국어."""

    error_code: Literal[
        "LLM_TIMEOUT",
        "LLM_UNAVAILABLE",
        "PROVIDER_NOT_CONFIGURED",
        "INVALID_REQUEST",
        "INTERNAL_ERROR",
    ]
    message: str
