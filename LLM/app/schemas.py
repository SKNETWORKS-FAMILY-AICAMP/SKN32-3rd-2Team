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


class ChatRequest(BaseModel):
    chatroom_id: str = Field(..., description="chatroom.chatroom_id (UUID)")
    message: str = Field(..., min_length=1, description="사용자 질문")
    history: list[HistoryTurn] = Field(
        default_factory=list,
        description=(
            "이전 대화. 최근 2~3턴만 보내면 된다(전체를 보낼 필요 없음). "
            "생략하거나 빈 배열로 두면 이 질문을 앞뒤 맥락 없는 독립 질문으로 처리한다. "
            "채워 보내면 '그럼 반차는?' 같은 후속 질문의 답변과 문서 검색이 함께 정확해진다. "
            "서버는 상태를 저장하지 않으므로, 필요한 맥락은 매 요청에 실어 보내야 한다."
        ),
    )
    provider: ProviderName | None = Field(
        None, description="미지정 시 서버 기본값(DEFAULT_PROVIDER) 사용"
    )
    use_rag: bool = Field(True, description="false면 문서 검색 없이 답변")


class ChatResponse(BaseModel):
    """WEB 이 실제로 쓰는 값만 담는다.

    지연·토큰·모델명 같은 계측값은 응답에 넣지 않는다. DB 컬럼도 없고 화면에
    쓸 일도 없어서, 서버 로그 파일(`METRICS_PATH`)에만 남긴다.
    """

    answer: str = Field(..., description="chat.message 에 그대로 저장 (speaker='llm')")
    topic: str = Field(
        ...,
        description=(
            "chat.topic 에 그대로 저장 (사용자 발화 행). "
            f"항상 다음 중 하나: {', '.join(TOPIC_CATEGORIES)}"
        ),
    )
    sources: list[Source] = Field(
        default_factory=list,
        description=(
            "근거 문서. 답변 하단에 문서명을 노출하는 데 쓴다(스토리보드 13p). "
            "RAG 실패 시에도 500 대신 빈 배열로 응답한다."
        ),
    )
    rag_degraded: bool = Field(
        False,
        description="true면 RAG 검색에 실패해 문서 없이 생성된 답변. 저장 불필요, UI 안내용",
    )


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
