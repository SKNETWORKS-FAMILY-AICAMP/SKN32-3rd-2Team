"""답변 생성 오케스트레이션.

순서: RAG 검색 → (답변 생성 ∥ 주제 분류) → 응답 조립

답변 생성과 주제 분류는 서로 의존하지 않으므로 `asyncio.gather` 로 동시에 돌린다.
순차로 하면 분류 지연이 그대로 사용자 대기 시간에 더해진다.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator, Sequence

from app import metrics
from app.config import get_settings
from app.domain import FALLBACK_TOPIC, TOPIC_MAX_LEN
from app.errors import LLMServiceError, ProviderTimeout, ProviderUnavailable
from app.prompts import ANSWER_SYSTEM, build_answer_context
from app.providers.base import Message
from app.providers.registry import get_provider
from app.schemas import ChatRequest, ChatResponse, Source, Usage
from app.services import rag_client
from app.services.topic import classify

logger = logging.getLogger(__name__)


def _to_messages(req: ChatRequest, sources: Sequence[Source]) -> list[Message]:
    """대화 이력 + 이번 질문. 참고 문서는 마지막 사용자 턴에 붙인다."""
    messages = [
        Message(role="assistant" if turn.speaker == "llm" else "user", content=turn.message)
        for turn in req.history
    ]
    context = build_answer_context(sources)
    messages.append(Message(role="user", content=f"{context}\n\n[질문]\n{req.message}"))
    return messages


async def _retrieve(req: ChatRequest) -> tuple[list[Source], bool, int]:
    if not req.use_rag:
        return [], False, 0
    return await rag_client.search(req.message)


def _wrap_provider_error(exc: Exception) -> LLMServiceError:
    if isinstance(exc, LLMServiceError):
        return exc
    if isinstance(exc, (asyncio.TimeoutError, TimeoutError)):
        return ProviderTimeout()
    logger.exception("프로바이더 호출 실패")
    return ProviderUnavailable()


async def generate_answer(req: ChatRequest) -> ChatResponse:
    settings = get_settings()
    provider = get_provider(req.provider)
    started = time.perf_counter()

    sources, degraded, rag_ms = await _retrieve(req)
    source_files = [s.original_file_name for s in sources]

    try:
        answer_result, (topic, _) = await asyncio.wait_for(
            asyncio.gather(
                provider.generate(
                    system=ANSWER_SYSTEM,
                    messages=_to_messages(req, sources),
                    temperature=0.2,
                ),
                classify(req.message, source_files, req.provider),
            ),
            timeout=settings.llm_timeout_sec,
        )
    except Exception as exc:
        raise _wrap_provider_error(exc) from exc

    latency_ms = int((time.perf_counter() - started) * 1000)
    usage = Usage(
        provider=provider.name,
        model=answer_result.model,
        prompt_tokens=answer_result.prompt_tokens,
        completion_tokens=answer_result.completion_tokens,
        latency_ms=latency_ms,
        rag_ms=rag_ms,
    )
    metrics.record(
        "chat",
        chatroom_id=req.chatroom_id,
        topic=topic,
        rag_degraded=degraded,
        source_count=len(sources),
        **usage.model_dump(),
    )

    return ChatResponse(
        answer=answer_result.text,
        sources=sources,
        topic=topic[:TOPIC_MAX_LEN],
        rag_degraded=degraded,
        usage=usage,
    )


async def stream_answer(req: ChatRequest) -> AsyncIterator[tuple[str, dict]]:
    """`(event_name, payload)` 를 순서대로 내보낸다.

    sources → token* → done  (실패 시 done 대신 error)
    """
    settings = get_settings()
    provider = get_provider(req.provider)
    started = time.perf_counter()

    sources, degraded, rag_ms = await _retrieve(req)
    source_files = [s.original_file_name for s in sources]
    yield "sources", {
        "sources": [s.model_dump() for s in sources],
        "rag_degraded": degraded,
    }

    # 토큰을 흘려보내는 동안 주제 분류를 백그라운드로 돌린다.
    topic_task = asyncio.create_task(classify(req.message, source_files, req.provider))
    ttft_ms: int | None = None

    try:
        stream = provider.stream(
            system=ANSWER_SYSTEM,
            messages=_to_messages(req, sources),
            temperature=0.2,
        )
        # 첫 토큰까지만 타임아웃을 건다. 생성이 시작된 뒤에는 끊지 않는다.
        first = await asyncio.wait_for(anext(stream), timeout=settings.llm_timeout_sec)
        ttft_ms = int((time.perf_counter() - started) * 1000)
        yield "token", {"delta": first}
        async for delta in stream:
            yield "token", {"delta": delta}
    except StopAsyncIteration:
        ttft_ms = int((time.perf_counter() - started) * 1000)
    except Exception as exc:
        topic_task.cancel()
        err = _wrap_provider_error(exc)
        yield "error", {"error_code": err.error_code, "message": err.message}
        return

    try:
        topic, _ = await topic_task
    except Exception:
        topic = FALLBACK_TOPIC

    latency_ms = int((time.perf_counter() - started) * 1000)
    usage = Usage(
        provider=provider.name,
        model=provider.model,
        latency_ms=latency_ms,
        ttft_ms=ttft_ms,
        rag_ms=rag_ms,
    )
    metrics.record(
        "chat_stream",
        chatroom_id=req.chatroom_id,
        topic=topic,
        rag_degraded=degraded,
        source_count=len(sources),
        **usage.model_dump(),
    )
    yield "done", {"topic": topic[:TOPIC_MAX_LEN], "usage": usage.model_dump()}
