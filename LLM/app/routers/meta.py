"""주제 분류 / 채팅방 이름 / 헬스체크 라우터."""

from __future__ import annotations

from fastapi import APIRouter

from app.config import get_settings
from app.domain import TOPIC_CATEGORIES, TOPIC_MAX_LEN
from app.providers.registry import SUPPORTED
from app.schemas import (
    ChatroomNameRequest,
    ChatroomNameResponse,
    HealthResponse,
    TopicRequest,
    TopicResponse,
)
from app.services import rag_client
from app.services.naming import generate_name
from app.services.topic import classify

router = APIRouter(tags=["meta"])


@router.post("/v1/topic", response_model=TopicResponse, summary="주제 분류")
async def topic(req: TopicRequest) -> TopicResponse:
    """`chat.topic` 용. 항상 고정 카테고리 중 하나만 반환한다.

    `/v1/chat` 응답에 이미 topic 이 들어 있으므로 보통은 부를 필요가 없다.
    과거 데이터 일괄 분류/재분류용.
    """
    result, cached = await classify(req.message, req.source_files, req.provider)
    return TopicResponse(topic=result[:TOPIC_MAX_LEN], cached=cached)


@router.post(
    "/v1/chatroom-name", response_model=ChatroomNameResponse, summary="채팅방 이름 생성"
)
async def chatroom_name(req: ChatroomNameRequest) -> ChatroomNameResponse:
    """`chatroom.chatroom_name` 용. 첫 질문으로 20자 내외 제목을 만든다."""
    return ChatroomNameResponse(name=await generate_name(req.message, req.provider))


@router.get("/health", response_model=HealthResponse, summary="헬스체크")
async def health() -> HealthResponse:
    settings = get_settings()
    providers = {name: settings.is_configured(name) for name in SUPPORTED}
    return HealthResponse(
        status="ok" if any(providers.values()) else "degraded",
        providers=providers,
        default_provider=settings.default_provider,
        rag=await rag_client.health(),
        topic_categories=list(TOPIC_CATEGORIES),
    )
