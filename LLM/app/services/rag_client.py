"""RAG 서비스(port 8002, Member C 담당) HTTP 클라이언트.

설계 원칙: **RAG 실패로 챗봇이 죽지 않는다.**
검색이 안 되면 문서 없이라도 답하는 편이 500을 던지는 것보다 사용자에게 낫다.
따라서 이 모듈은 예외를 밖으로 던지지 않고 (검색결과, degraded) 튜플을 돌려준다.
"""

from __future__ import annotations

import logging
import time

import httpx

from app.config import get_settings
from app.schemas import Source

logger = logging.getLogger(__name__)

_client: httpx.AsyncClient | None = None

# RAG_MODE=mock 일 때 쓰는 고정 응답. 실제 코퍼스(RAG/res/pdf)에 있는 파일명을 쓴다.
_MOCK_RESULTS: list[dict] = [
    {
        "doc_id": 1,
        "original_file_name": "5.근로기준법(법률).pdf",
        "content": (
            "제60조(연차 유급휴가) ① 사용자는 1년간 80퍼센트 이상 출근한 근로자에게 "
            "15일의 유급휴가를 주어야 한다."
        ),
        "score": 0.87,
        "page": 23,
    },
    {
        "doc_id": 2,
        "original_file_name": "복무규정.pdf",
        "content": "제12조(휴가의 신청) 직원이 휴가를 사용하려는 경우 사전에 결재권자의 승인을 받아야 한다.",
        "score": 0.72,
        "page": 5,
    },
]


def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        settings = get_settings()
        _client = httpx.AsyncClient(
            base_url=settings.rag_base_url,
            timeout=settings.rag_timeout_sec,
        )
    return _client


async def close_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


def _to_sources(results: list[dict]) -> list[Source]:
    sources: list[Source] = []
    for r in results:
        name = r.get("original_file_name") or r.get("file_name")
        if not name:
            continue  # 문서명이 없으면 출처로 표시할 수 없다
        sources.append(
            Source(
                doc_id=r.get("doc_id"),
                original_file_name=str(name),
                page=r.get("page"),
                snippet=r.get("content"),
                score=r.get("score"),
            )
        )
    return sources


async def search(query: str, top_k: int | None = None) -> tuple[list[Source], bool, int]:
    """관련 문서를 검색한다.

    Returns:
        (sources, degraded, elapsed_ms) — degraded=True 면 검색 실패로 문서 없이 진행해야 함.
    """
    settings = get_settings()
    k = top_k or settings.rag_top_k
    started = time.perf_counter()

    if settings.rag_mode == "mock":
        return _to_sources(_MOCK_RESULTS[:k]), False, 0

    try:
        resp = await get_client().post("/v1/search", json={"query": query, "top_k": k})
        resp.raise_for_status()
        payload = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        # 로그만 남기고 degraded 로 계속 간다.
        logger.warning("RAG 검색 실패 — 문서 없이 응답합니다: %s", exc)
        return [], True, int((time.perf_counter() - started) * 1000)

    results = payload.get("results", []) if isinstance(payload, dict) else []
    return _to_sources(results), False, int((time.perf_counter() - started) * 1000)


async def health() -> str:
    """/health 표시용: up | down | mock"""
    settings = get_settings()
    if settings.rag_mode == "mock":
        return "mock"
    try:
        resp = await get_client().get("/health", timeout=1.0)
        return "up" if resp.status_code < 500 else "down"
    except httpx.HTTPError:
        return "down"
