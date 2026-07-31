"""API 키 없이 서비스를 돌리기 위한 고정 응답 프로바이더 (`LLM_MODE=mock`).

목적은 두 가지다.
- 팀원(챗봇 UI 담당)이 키 발급을 기다리지 않고 화면을 붙여볼 수 있게
- 배선/스키마/에러 규약을 실제 API 호출 없이 검증할 수 있게

공개 API 계약은 live 모드와 완전히 동일하다. 요청 body 로는 선택할 수 없고
환경변수로만 켜지므로, 프론트 코드가 mock 을 알 필요가 없다.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Sequence

from app.providers.base import GenerationResult, LLMProvider, Message

# classify 용 키워드 규칙. live 모드의 LLM 분류를 흉내내되 완전히 결정적이다.
_KEYWORD_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("휴가/휴직", ("연차", "휴가", "휴직", "육아", "출산", "병가", "월차")),
    ("근태/근무형태", ("근무", "출근", "지각", "재택", "유연", "시차", "출장", "국외여행", "근로시간")),
    ("급여/보수", ("급여", "월급", "임금", "수당", "보수", "연봉", "퇴직금", "상여")),
    ("채용/임용", ("채용", "임용", "입사", "계약직", "기간제", "신규")),
    ("인사/승진", ("승진", "인사", "평가", "전보", "발령", "시험")),
    ("복리후생", ("복리", "후생", "지원금", "치료비", "복지", "경조사")),
    ("복무/징계", ("징계", "복무", "행동강령", "비위", "음주운전", "감사", "고발")),
)

_MOCK_ANSWER = (
    "[MOCK 응답] 실제 LLM API를 호출하지 않는 개발 모드입니다.\n\n"
    "질문하신 내용은 사내 인사 규정에 따라 처리됩니다. "
    "정확한 기준은 아래 근거 문서를 확인해주세요.\n\n"
    "※ 실제 답변을 받으려면 .env 에 API 키를 넣고 LLM_MODE=live 로 실행하세요."
)

# 채팅방 이름 생성 프롬프트를 알아보기 위한 표식 (app/prompts.py CHATROOM_NAME_SYSTEM).
# mock 은 요청 종류를 모르므로 system 프롬프트로 구분한다.
_NAMING_MARKER = "채팅방 제목"


class MockProvider(LLMProvider):
    name = "mock"

    def __init__(self, alias: str) -> None:
        # /v1/chat 응답의 usage.provider 는 요청자가 고른 이름을 그대로 보여준다.
        self.name = alias
        self.model = f"mock-{alias}"

    async def generate(
        self,
        *,
        system: str,
        messages: Sequence[Message],
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> GenerationResult:
        await asyncio.sleep(0.05)
        if _NAMING_MARKER in system:
            # 채팅방 이름 요청 — 답변 본문을 제목으로 쓰면 안 되므로 질문을 요약해 돌려준다.
            last_user = next((m.content for m in reversed(messages) if m.role == "user"), "")
            text = " ".join(last_user.split())[:20] or "새 대화"
        else:
            text = _MOCK_ANSWER
        return GenerationResult(
            text=text,
            model=self.model,
            prompt_tokens=len(system) // 4,
            completion_tokens=len(text) // 4,
        )

    async def stream(
        self,
        *,
        system: str,
        messages: Sequence[Message],
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        for i in range(0, len(_MOCK_ANSWER), 12):
            await asyncio.sleep(0.02)
            yield _MOCK_ANSWER[i : i + 12]

    async def classify(
        self,
        *,
        system: str,
        user_content: str,
        allowed: Sequence[str],
    ) -> str:
        for category, keywords in _KEYWORD_RULES:
            if category in allowed and any(k in user_content for k in keywords):
                return category
        return "기타"
