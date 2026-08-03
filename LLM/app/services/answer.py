"""답변 생성 오케스트레이션.

순서: RAG 검색 → (답변 생성 ∥ 주제 분류) → 응답 조립

답변 생성과 주제 분류는 서로 의존하지 않으므로 `asyncio.gather` 로 동시에 돌린다.
순차로 하면 분류 지연이 그대로 사용자 대기 시간에 더해진다.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from collections.abc import AsyncIterator, Sequence

from app import metrics
from app.config import get_settings
from app.domain import FALLBACK_TOPIC, TOPIC_MAX_LEN, RetrievedChunk
from app.errors import (
    LLMServiceError,
    ProviderRateLimited,
    ProviderTimeout,
    ProviderUnavailable,
)
from app.prompts import ANSWER_SYSTEM, build_answer_context
from app.providers.base import Message
from app.providers.registry import get_provider
from app.schemas import ChatRequest, ChatResponse, HistoryTurn
from app.services import rag_client
from app.services.topic import classify

logger = logging.getLogger(__name__)

# 임베딩 모델 입력 길이를 고려한 검색어 상한.
SEARCH_QUERY_MAX_CHARS = 500


def _to_messages(req: ChatRequest, chunks: Sequence[RetrievedChunk]) -> list[Message]:
    """대화 이력 + 이번 질문. 참고 문서는 마지막 사용자 턴에 붙인다."""
    messages = [
        Message(role="assistant" if turn.speaker == "llm" else "user", content=turn.message)
        for turn in req.history
    ]
    context = build_answer_context(chunks)
    messages.append(Message(role="user", content=f"{context}\n\n[질문]\n{req.message}"))
    return messages


def build_search_query(message: str, history: Sequence[HistoryTurn] = ()) -> str:
    """RAG 에 보낼 검색어를 만든다.

    `history` 가 비어 있으면 질문 원문을 그대로 쓴다. 즉 WEB 이 대화 이력을
    보내지 않는 동안은 '질문을 각각 독립으로 취급'하는 동작이 된다.

    이력이 오기 시작하면 직전 사용자 질문을 앞에 붙인다. "그럼 반차는?" 처럼
    그 문장만으로는 의미가 서지 않는 후속 질문이 엉뚱한 문서를 물어오는 것을 막는다.
    임베딩 모델 입력 길이가 있으므로 전체 길이를 제한하되, **현재 질문은 절대
    자르지 않고** 앞에 붙는 이전 질문 쪽을 줄인다.
    """
    message = message.strip()
    previous = next(
        (t.message.strip() for t in reversed(history) if t.speaker == "user" and t.message.strip()),
        None,
    )
    if not previous:
        return message[:SEARCH_QUERY_MAX_CHARS]

    budget = SEARCH_QUERY_MAX_CHARS - len(message) - 1
    if budget <= 0:
        return message[:SEARCH_QUERY_MAX_CHARS]
    return f"{previous[:budget]} {message}"


async def _retrieve(req: ChatRequest) -> tuple[list[RetrievedChunk], bool, int]:
    if not req.use_rag:
        return [], False, 0
    return await rag_client.search(build_search_query(req.message, req.history))


_RETRY_AFTER_RE = re.compile(r"retry in ([\d.]+)\s*s", re.I)


def _rate_limit_of(exc: Exception) -> ProviderRateLimited | None:
    """벤더의 429 를 알아본다.

    OpenAI(`openai.RateLimitError`)는 `.status_code`, Gemini(`google.genai` ClientError)는
    `.code` 로 상태를 노출한다. SDK 를 직접 import 하지 않고 속성으로 판별해,
    한쪽 SDK 가 없는 환경에서도 동작하게 한다.
    """
    status = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    if status != 429:
        return None

    # Gemini 는 메시지에 "Please retry in 31.06s" 를 담아준다.
    m = _RETRY_AFTER_RE.search(str(exc))
    retry_after = float(m.group(1)) if m else None
    return ProviderRateLimited(retry_after=retry_after)


def _wrap_provider_error(exc: Exception) -> LLMServiceError:
    if isinstance(exc, LLMServiceError):
        return exc
    if isinstance(exc, (asyncio.TimeoutError, TimeoutError)):
        return ProviderTimeout()
    rate_limited = _rate_limit_of(exc)
    if rate_limited is not None:
        logger.warning(
            "프로바이더 호출 한도 초과 (재시도 권장 %s초)", rate_limited.retry_after or "?"
        )
        return rate_limited
    logger.exception("프로바이더 호출 실패")
    return ProviderUnavailable()


async def generate_answer(req: ChatRequest) -> ChatResponse:
    settings = get_settings()
    provider = get_provider(req.provider)
    started = time.perf_counter()

    chunks, degraded, rag_ms = await _retrieve(req)
    source_files = [c.original_file_name for c in chunks]

    # 답변 생성과 주제 분류는 서로 의존하지 않으므로 병렬로 돌린다.
    # 순차로 하면 분류 지연이 그대로 사용자 대기 시간에 더해진다.
    try:
        answer_result, (topic, _) = await asyncio.wait_for(
            asyncio.gather(
                provider.generate(
                    system=ANSWER_SYSTEM,
                    messages=_to_messages(req, chunks),
                    temperature=0.2,
                    max_tokens=settings.answer_max_tokens,
                ),
                classify(req.message, source_files, req.provider),
            ),
            timeout=settings.llm_timeout_sec,
        )
    except Exception as exc:
        err = _wrap_provider_error(exc)
        # 실패도 기록해야 성능 보고서에서 에러율/타임아웃 비율을 낼 수 있다.
        metrics.record_error(
            "chat_error",
            chatroom_id=req.chatroom_id,
            error_code=err.error_code,
            provider=provider.name,
            model=provider.model,
            latency_ms=int((time.perf_counter() - started) * 1000),
            rag_ms=rag_ms,
        )
        raise err from exc

    # 계측값은 응답에 넣지 않고 로그로만 남긴다.
    metrics.record_chat(
        "chat",
        chatroom_id=req.chatroom_id,
        topic=topic,
        rag_degraded=degraded,
        source_count=len(chunks),
        source_files=source_files,
        metrics=metrics.CallMetrics(
            provider=provider.name,
            model=answer_result.model,
            latency_ms=int((time.perf_counter() - started) * 1000),
            prompt_tokens=answer_result.prompt_tokens,
            completion_tokens=answer_result.completion_tokens,
            rag_ms=rag_ms,
        ),
    )

    return ChatResponse(
        answer=answer_result.text,
        topic=topic[:TOPIC_MAX_LEN],
        sources=[c.to_source() for c in chunks],
        rag_degraded=degraded,
    )


async def stream_answer(req: ChatRequest) -> AsyncIterator[tuple[str, dict]]:
    """`(event_name, payload)` 를 순서대로 내보낸다.

    sources → token* → done  (실패 시 done 대신 error)
    """
    settings = get_settings()
    provider = get_provider(req.provider)
    started = time.perf_counter()

    chunks, degraded, rag_ms = await _retrieve(req)
    source_files = [c.original_file_name for c in chunks]
    yield "sources", {
        "sources": [c.to_source().model_dump() for c in chunks],
        "rag_degraded": degraded,
    }

    # 토큰을 흘려보내는 동안 주제 분류를 백그라운드로 돌린다.
    topic_task = asyncio.create_task(classify(req.message, source_files, req.provider))
    ttft_ms: int | None = None

    try:
        stream = provider.stream(
            system=ANSWER_SYSTEM,
            messages=_to_messages(req, chunks),
            temperature=0.2,
            max_tokens=settings.answer_max_tokens,
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
        metrics.record_error(
            "chat_stream_error",
            chatroom_id=req.chatroom_id,
            error_code=err.error_code,
            provider=provider.name,
            model=provider.model,
            latency_ms=int((time.perf_counter() - started) * 1000),
            rag_ms=rag_ms,
        )
        yield "error", {"error_code": err.error_code, "message": err.message}
        return

    try:
        topic, _ = await topic_task
    except Exception:
        topic = FALLBACK_TOPIC

    metrics.record_chat(
        "chat_stream",
        chatroom_id=req.chatroom_id,
        topic=topic,
        rag_degraded=degraded,
        source_count=len(chunks),
        source_files=source_files,
        metrics=metrics.CallMetrics(
            provider=provider.name,
            model=provider.model,
            latency_ms=int((time.perf_counter() - started) * 1000),
            ttft_ms=ttft_ms,
            rag_ms=rag_ms,
        ),
    )
    yield "done", {"topic": topic[:TOPIC_MAX_LEN]}
