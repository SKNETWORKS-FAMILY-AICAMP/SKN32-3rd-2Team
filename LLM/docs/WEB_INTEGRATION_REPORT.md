# WEB ↔ LLM 연동 확인 결과

> 작성: Member D (LLM) · 최종 갱신 2026-08-03
> **결론: 연동 완료. 정상 동작 확인했습니다.**

## 확인 방법

WEB 브랜치(`ca83706`)를 **별도 폴더에 클론**해 격리 실행했습니다. 원본 브랜치 파일은 수정하지 않았습니다.

```
C:\Dev_Tools\web_test\web_only\     WEB 브랜치 격리 복제본
  :8000  WEB  (SQLite + 테스트 계정)
  :8002  LLM  (live, OpenAI gpt-4o-mini)
```

MySQL 자격증명을 몰라 **SQLite** 로 띄웠습니다. `app/database.py` 에 sqlite 분기가 있어 코드 수정 없이 됩니다.

```
CHAT_API_BASE_URL=http://127.0.0.1:8002
CHAT_API_TIMEOUT_SECONDS=60
```

---

# 연동 결과

## 정상 동작합니다

```
[1] 연차 며칠까지 쓸 수 있나요?      (1.7초)
    sources  : 5.근로기준법(법률).pdf p.23 / 복무규정.pdf p.5
    degraded : False

[2] 그럼 반차는 어떻게 되나요?       (1.4초)   ← history 로 맥락 유지
    sources  : (동일)

채팅방 제목: '연차 사용 가능 일수 문의'         ← LLM 요약
```

**1.7초.** `httpx.Client` 싱글턴 + `warm_up()` 으로 커넥션 생성 비용을 서버 기동 시점에 미리 내는 구조라, 첫 요청부터 빠릅니다.

## WEB 쪽에서 이미 처리된 것

명세서(`docs/API.md`)대로 붙어 있습니다.

| 항목 | 상태 |
|---|---|
| `POST /v1/chat` 호출 | ✅ `chatroom_id` + `message` + `history` |
| `sources` 반환 | ✅ `send_message()` 가 `{answer, sources, rag_degraded}` dict 반환 |
| 채팅방 이름 LLM 요약 | ✅ `POST /v1/chatroom-name` |
| **병렬 호출** | ✅ `ThreadPoolExecutor` 로 두 요청 동시 실행 |
| 에러 규약 | ✅ `error_code` 5종 그대로, `message` 화면 출력 |
| `history` | ✅ 최근 3쌍(최대 6개 메시지) 전달 |
| 실패 시 대화 보존 | ✅ 에러가 나도 질문·안내문구를 DB에 남김 |

`history` 를 실제로 보내고 있어서 **후속 질문 인식이 이미 켜져 있습니다.** LLM 서비스는 직전 질문을 검색어 앞에 붙이는 로직이 자동으로 동작합니다.

---

# 합의 사항

## 1. 주제 카테고리 — **8종으로 확정** ✅

```
휴가/휴직 · 근태/근무형태 · 급여/보수 · 채용/임용 · 인사/승진 · 복리후생 · 복무/징계 · 기타
```

`RAG/res/pdf/` 의 실제 규정·법령 PDF 28건을 묶어 도출했습니다. 근거표는 `docs/API.md` 4절.

### ⚠️ WEB 에 남은 작업 — 차트 색상 맵

`static/js/admin_stats.js` 가 아직 옛 5종 기준입니다.

```js
const CATEGORY_COLORS = {
  "휴가/근태": "#2a78d6", "급여/보험": "#eb6834",
  "복지제도": "#1baf7a", "채용/인사": "#eda100", "기타": "#898781",
};
const colors = items.map(i => CATEGORY_COLORS[i.category] || CATEGORY_COLORS["기타"]);
```

8종 중 `기타` 만 매칭되고 **나머지 7개가 전부 회색**으로 칠해집니다. 8종용 색상 맵으로 교체가 필요합니다.

> 하드코딩 대신 `GET /health` 의 `topic_categories` 를 받아 쓰면, 나중에 목록이 바뀌어도 자동으로 맞습니다.

집계 로직(`Counter(chat.topic)`)은 DB 값을 그대로 세는 동적 방식이라 **데이터는 이미 정상**입니다.

### 기존 데이터 정리

더미 시절 5종으로 쌓인 `chat.topic` 이 남아 있으면 차트가 최대 13조각이 됩니다.
비우거나, `POST /v1/topic` 으로 일괄 재분류하면 됩니다. (LLM 서비스가 질문만 받아 8종으로 재분류)

## 2. RAG 속도 — Member C 담당

현재 검색에 **30초** 가 걸립니다. LLM 서비스의 RAG 타임아웃은 3초라, 지금 붙이면 매번 타임아웃 → 문서 없이 답변하게 됩니다.

유력한 병목은 요청마다 FAISS 인덱스 28개를 `load_local` 하는 부분으로 보입니다. 서버 시작 시 한 번만 메모리에 올리면 크게 줄어들 것으로 예상됩니다.

---

# 참고: LLM 서비스 쪽 실측

| | |
|---|---|
| OpenAI `gpt-4o-mini` | 1.7초 |
| Gemini `gemini-3.5-flash` | 4.0초 |
| RAG (Member C) | **30초** |

응답 시간 목표(스토리보드 13p "5초")는 **RAG 속도가 해결되어야 달성 가능**합니다.

Gemini 무료 티어는 **분당 20회** 제한이 있어, 시연 중 동시 접속이 많으면 429 가 날 수 있습니다.
기본 프로바이더는 OpenAI 로 두었습니다.

---

# 확인 안 된 것

- **MySQL 환경** — SQLite 로만 확인했습니다. `speaker` 컬럼이 `Enum("user","llm")` 이라 MySQL 에서도 문제없을 것으로 보이나 실제 확인은 못 했습니다.
- **RAG 실연동** — mock 으로만 확인했습니다.
- **동시 사용** — 여러 명이 동시에 질문할 때의 동작은 확인하지 않았습니다.

---

# 사소한 메모

`chat_service.send_message()` 는 `answer` 키로 반환하는데 라우터가 `message` 로 바꿔 내보냅니다.
LLM 서비스(`answer`) → chat_service(`answer`) → 라우터(`message`) 로 계층마다 이름이 달라져,
나중에 디버깅할 때 헷갈릴 수 있습니다. 동작에는 문제 없습니다.
