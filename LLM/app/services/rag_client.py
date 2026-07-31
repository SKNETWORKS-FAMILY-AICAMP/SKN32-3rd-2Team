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
from app.domain import RetrievedChunk

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


def _to_chunks(results: list[dict]) -> list[RetrievedChunk]:
    """RAG 응답을 내부 모델로 바꾸면서 중복을 제거한다.

    RAG 가 돌려주는 단위는 '문서'가 아니라 '청크'라, 한 페이지에서 인접한 청크가
    여러 개 걸리면 같은 (파일, 페이지)가 중복으로 온다. 그대로 두면 답변 하단에
    "복무규정.pdf p.5"가 두 번 표시되므로 여기서 합친다.
    페이지가 다르면 서로 다른 근거이므로 남긴다. 순서(유사도 순)는 유지한다.
    """
    chunks: list[RetrievedChunk] = []
    seen: set[tuple[str, int | None]] = set()
    for r in results:
        name = r.get("original_file_name") or r.get("file_name")
        if not name:
            continue  # 문서명이 없으면 출처로 표시할 수 없다
        key = (str(name), r.get("page"))
        if key in seen:
            continue
        seen.add(key)
        chunks.append(
            RetrievedChunk(
                original_file_name=str(name),
                content=str(r.get("content") or ""),
                doc_id=r.get("doc_id"),
                page=r.get("page"),
                score=r.get("score"),
            )
        )
    return chunks


async def search(query: str, top_k: int | None = None) -> tuple[list[RetrievedChunk], bool, int]:
    """관련 문서 조각을 검색한다.

    Returns:
        (chunks, degraded, elapsed_ms) — degraded=True 면 검색 실패로 문서 없이 진행해야 함.
    """
    settings = get_settings()
    k = top_k or settings.rag_top_k
    started = time.perf_counter()

    if settings.rag_mode == "mock":
        return _to_chunks(_MOCK_RESULTS[:k]), False, 0

    try:
        resp = await get_client().post("/v1/search", json={"query": query, "top_k": k})
        resp.raise_for_status()
        payload = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        # 로그만 남기고 degraded 로 계속 간다.
        logger.warning("RAG 검색 실패 — 문서 없이 응답합니다: %s", exc)
        return [], True, int((time.perf_counter() - started) * 1000)

    results = payload.get("results", []) if isinstance(payload, dict) else []
    return _to_chunks(results), False, int((time.perf_counter() - started) * 1000)


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
