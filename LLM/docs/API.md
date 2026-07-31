# LLM 서비스 API 명세서 (제공)

> Smart HR — Member D (LLM 파트) 산출물
> **받는 사람: 챗봇 서버 / 프론트 담당 (WEB 파트, port 8000)**
>
> 이 문서는 **LLM 서비스가 제공하는** API입니다.
> 제가 RAG 담당자에게 **요청드리는** 명세는 → [RAG_REQUIRED_API.md](RAG_REQUIRED_API.md)

- **Base URL**: `http://localhost:8001`
- **Swagger (자동 생성, 항상 최신)**: `http://localhost:8001/docs`
- 모든 요청/응답 `Content-Type: application/json`, 인코딩 UTF-8

## WEB 파트가 쓸 엔드포인트는 사실상 `/v1/chat` 하나입니다

| | 엔드포인트 | 언제 부르나 |
|---|---|---|
| ✅ | `POST /v1/chat` | **사용자가 질문할 때마다.** 답변·출처·주제·(첫 질문이면)채팅방 이름이 **한 번에** 나옵니다 |
| ✅ | `GET /health` | 상태 확인, 대시보드 카테고리 목록 조회 |
| 🔧 | `POST /v1/chatroom-name` | **평상시 호출 불필요.** 이름만 다시 뽑고 싶을 때 (6절) |
| 🔧 | `POST /v1/topic` | **평상시 호출 불필요.** 운영/시연 준비용 (6절) |
| ⏸ | `POST /v1/chat/stream` | **당장은 안 씁니다.** 나중에 타이핑 효과가 필요해지면 (5절) |

> 같은 `message` 를 여러 엔드포인트에 나눠 보낼 필요가 없도록 **`/v1/chat` 하나에 다 넣었습니다.**
> 내부적으로 답변 생성 · 주제 분류 · 이름 생성을 **병렬로** 돌리기 때문에 지연도 늘지 않습니다.

---

## 0. 이 서비스의 위치

```
웹 프론트엔드 → 챗봇 서버(8000) → [LLM 서비스(8001)] → RAG 서비스(8002)
                      ↓
                     MySQL
```

**LLM 서비스는 DB에 직접 쓰지 않습니다.** 시퀀스다이어그램(PPT 17p)대로 DB 저장은 챗봇 서버가 담당합니다.
이 서비스는 답변 본문·주제·근거 문서를 JSON으로 돌려줄 뿐입니다.

### DB 매핑 요약

| 이 API의 응답 필드 | 저장 위치 | 컬럼 제약 |
|---|---|---|
| `ChatResponse.answer` | `chat.message` (speaker=`llm`) | TEXT |
| `ChatResponse.topic` | `chat.topic` (**사용자 발화 행**) | VARCHAR(100) — 서버가 보장 |
| `ChatResponse.chatroom_name` | `chatroom.chatroom_name` | VARCHAR(100) — 서버가 보장 |

길이 제한은 **LLM 서비스 쪽에서 이미 자르고 보내므로** 챗봇 서버가 추가로 truncate 할 필요 없습니다.

> `topic` 은 **사용자 질문 행**에 저장해주세요. 대시보드 집계 쿼리가 `WHERE speaker='user'` 기준입니다.

---

## 1. `POST /v1/chat` — 답변 생성 ⭐ 기본 엔드포인트

### Request

```json
{
  "chatroom_id": "3f1c...-uuid",
  "message": "연차 며칠까지 쓸 수 있나요?",
  "history": [
    { "speaker": "user", "message": "안녕하세요" },
    { "speaker": "llm",  "message": "무엇을 도와드릴까요?" }
  ],
  "generate_name": true,
  "provider": "openai",
  "use_rag": true
}
```

| 필드 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `chatroom_id` | string | ✅ | `chatroom.chatroom_id` (UUID) |
| `message` | string | ✅ | 사용자 질문 |
| `history` | array | ❌ | 이전 대화. **최근 몇 턴만** 보내면 됩니다(전체 X) |
| `generate_name` | boolean | ❌ | **채팅방의 첫 질문일 때만 `true`.** 응답에 `chatroom_name` 이 함께 옵니다 |
| `provider` | `"openai"` \| `"gemini"` | ❌ | 미지정 시 서버 기본값 |
| `use_rag` | boolean | ❌ | 기본 `true`. `false`면 문서 검색 없이 답변 |

### Response `200`

```json
{
  "answer": "연차유급휴가는 근로기준법 제60조에 따라 ...",
  "sources": [
    {
      "doc_id": 12,
      "original_file_name": "5.근로기준법(법률).pdf",
      "page": 23,
      "snippet": "사용자는 1년간 80퍼센트 이상 출근한 근로자에게 ...",
      "score": 0.87
    }
  ],
  "topic": "휴가/휴직",
  "rag_degraded": false,
  "chatroom_name": "연차 사용 일수 문의",
  "usage": {
    "provider": "openai", "model": "gpt-4o-mini",
    "prompt_tokens": 1523, "completion_tokens": 210,
    "latency_ms": 2140, "ttft_ms": null, "rag_ms": 180
  }
}
```

### 응답 필드를 어떻게 처리하면 되나

| 필드 | 무엇 | 할 일 |
|---|---|---|
| `answer` | 답변 본문 | **DB 저장** → `chat.message` (speaker=`llm`) |
| `topic` | 주제 분류 결과 (8종 중 하나) | **DB 저장** → `chat.topic` (사용자 발화 행) |
| `chatroom_name` | 채팅방 제목 | **DB 저장** → `chatroom.chatroom_name`. `generate_name` 을 안 보냈으면 `null` 이니 그냥 두면 됩니다 |
| `sources` | 근거 문서 | **화면 표시.** 답변 하단 "근거 문서" 영역 (스토리보드 13p) |
| `rag_degraded` | 문서 검색 실패 여부 | **UI 분기.** `true`면 "근거 문서를 찾지 못했습니다" 안내. 저장 불필요 |
| `usage` | 계측값 (모델·토큰·지연) | **무시해도 됩니다.** 성능 보고서/디버깅용 |

**이 한 번의 호출로 저장에 필요한 값이 전부 나옵니다.** 같은 `message` 를 `/v1/topic` 이나 `/v1/chatroom-name` 에 다시 보낼 필요가 없습니다.

내부적으로 **답변 생성 · 주제 분류 · 이름 생성을 병렬로** 처리하므로 `generate_name: true` 를 넣어도 응답 시간이 늘지 않습니다. (mock 기준 측정: `true` 61ms / `false` 60ms)

`rag_degraded: true` 는 **에러가 아니라 정상 200** 입니다. `sources` 만 빈 배열입니다.

### 호출 패턴 요약

```
채팅방 첫 질문   → POST /v1/chat  { ..., "generate_name": true }
                   → answer + topic + chatroom_name 저장
두번째 질문부터  → POST /v1/chat  { ..., "history": [...] }
                   → answer + topic 저장 (chatroom_name 은 null)
```

---

## 2. `GET /health`

```json
{
  "status": "ok",
  "providers": { "openai": true, "gemini": true },
  "default_provider": "openai",
  "rag": "mock",
  "topic_categories": ["휴가/휴직", "근태/근무형태", "..."]
}
```

`rag` 값: `up`(RAG 연결됨) / `down`(연결 실패) / `mock`(개발용 고정 응답)

---

## 3. 주제(topic) 카테고리 — ⚠️ 대시보드 담당자 확인 필요

`chat.topic` 은 **항상 아래 8개 중 하나**입니다. 자유 문자열이 절대 나오지 않습니다.

```
휴가/휴직 · 근태/근무형태 · 급여/보수 · 채용/임용 · 인사/승진 · 복리후생 · 복무/징계 · 기타
```

그래서 대시보드 도넛 차트는 안심하고 이렇게 쓰면 됩니다.

```sql
SELECT topic, COUNT(*) AS cnt
FROM chat
WHERE speaker = 'user' AND topic IS NOT NULL
GROUP BY topic;
```

**이 목록은 임의로 정한 게 아니라** `RAG/res/pdf/` 의 실제 규정·법령 PDF 28건을 묶어 도출했습니다.

| 카테고리 | 근거 문서 |
|---|---|
| 휴가/휴직 | 휴직자 복무관리 지침 · 남녀고용평등법(법률/시행령/시행규칙) · 근로기준법 일부 |
| 근태/근무형태 | 복무규정 · 유연근무제 운영지침 · 시간선택제 직원에 관한 규칙 · 국외여행에관한규칙 · 근로기준법 일부 |
| 급여/보수 | 공무직 직원 인사 및 보수에 관한 규칙 · 근로기준법 일부 |
| 채용/임용 | 계약직직원임용지침 · 교육공무원임용령 · 별정직직원인사관리지침 · 기간제 및 단시간근로자 보호법(법률/시행령/시행규칙) |
| 인사/승진 | 직원인사규정 · 직원인사규정 시행규칙 · 직원승진시험시행 지침 · 교육공무원법 |
| 복리후생 | 교직원특수병치료비지원지침 |
| 복무/징계 | 교직원행동강령 · 직무범죄고발지침 · 교직원 음주운전 비위행위 확인에 관한 지침 |
| 기타 | 공공기관의 운영에 관한 법률(법률/시행령) |

> 이 표는 "문서 = 카테고리" 매핑이 **아닙니다.** 법령 하나에 여러 주제가 섞여 있어서(근로기준법 = 임금 + 근로시간 + 연차 + 해고) 분류기에 주는 힌트로만 쓰고, 최종 판단은 질문 의도 기준입니다.

**바꾸고 싶으면 말씀해 주세요.** `app/domain.py` 의 `TOPIC_CATEGORIES` 상수 한 줄이라 반영은 즉시 됩니다.

차트 축은 하드코딩하지 말고 `GET /health` 의 `topic_categories` 를 받아 쓰면, 목록이 바뀌어도 자동으로 맞습니다.

---

## 4. 에러 규약

에러는 HTTP 상태코드와 함께 **항상** 아래 형태로 옵니다.

```json
{ "error_code": "LLM_TIMEOUT", "message": "일시적인 오류입니다. 잠시 후 다시 시도해주세요." }
```

`message` 는 **프론트에 그대로 출력해도 되는 한국어**입니다. 별도 매핑 테이블을 만들 필요 없습니다.

| HTTP | `error_code` | 상황 |
|---|---|---|
| 504 | `LLM_TIMEOUT` | 생성이 `LLM_TIMEOUT_SEC`(기본 5초) 초과. 스토리보드 13p 요구사항 대응 |
| 503 | `LLM_UNAVAILABLE` | 프로바이더 API 호출 실패 (장애/쿼터) |
| 503 | `PROVIDER_NOT_CONFIGURED` | 해당 프로바이더 API 키 미설정 |
| 422 | `INVALID_REQUEST` | 요청 스키마 위반 |
| 500 | `INTERNAL_ERROR` | 그 외 |

**RAG 실패는 에러가 아닙니다.** `200` + `rag_degraded: true` + `sources: []` 로 내려갑니다.

---

## 5. ⏸ `POST /v1/chat/stream` — 지금은 쓰지 않음

구현은 되어 있으나 **1차 구현에서는 `/v1/chat` 만 씁니다.** 나중에 타이핑 효과가 필요해지면 그때 붙이면 됩니다.

Request 형식은 `/v1/chat` 과 완전히 동일하므로, 나중에 바꿔도 요청 코드는 그대로 두면 됩니다.

`Content-Type: text/event-stream` 으로 `sources` → `token`×N → `done` 순서로 내려옵니다.

```
event: sources
data: {"sources":[...],"rag_degraded":false}

event: token
data: {"delta":"연차유급"}

event: done
data: {"topic":"휴가/휴직","usage":{...,"ttft_ms":410}}
```

실패 시 `done` 대신 `error` 이벤트가 옵니다.

붙일 때 주의할 점 2가지:
- **브라우저 내장 `EventSource` 로는 못 씁니다.** GET 전용이라 body를 못 보냅니다. `fetch` + `response.body.getReader()` 를 쓰세요.
- **챗봇 서버가 중계할 때 버퍼링하면 안 됩니다.** 전부 받았다가 넘기면 스트리밍 효과가 사라집니다.

---

## 6. 🔧 단독 엔드포인트 — 평상시 호출 불필요

아래 둘은 **일반 대화 흐름에서는 부르지 마세요.** `/v1/chat` 이 이미 같은 값을 응답에 실어 보내므로,
따로 부르면 같은 `message` 를 두 번 보내면서 LLM 호출만 한 번 더 나갑니다.

일회성 배치나 예외 상황용으로만 남겨둔 것이라 **화면 코드가 아니라 스크립트에서 부르는 용도**입니다.

### `POST /v1/topic` — 주제 분류

**Request** `{ "message": "...", "source_files": ["복무규정.pdf"] }` (`source_files` 는 선택, 분류 힌트)
**Response** `{ "topic": "휴가/휴직", "cached": false }`

남겨둔 이유:
1. **카테고리 목록이 바뀌었을 때 과거 데이터 재분류.** 3절 8종은 아직 팀 확정 전이라, 바뀌면 기존 `chat` 행의 `topic` 이 옛 기준으로 남습니다. 도넛 차트를 일관되게 그리려면 과거 질문을 다시 분류해야 합니다.
2. **발표용 더미 데이터 채우기.** 대시보드 시연에 데이터가 필요한데, 답변까지 생성하면 시간·비용이 듭니다. 질문만 넣어 `topic` 만 뽑는 게 훨씬 쌉니다.

### `POST /v1/chatroom-name` — 채팅방 이름 생성

**Request** `{ "message": "연차 며칠까지 쓸 수 있나요?" }`
**Response** `{ "name": "연차 사용 일수 문의" }`

남겨둔 이유: 이미 있는 채팅방의 이름만 다시 뽑고 싶을 때 (예: 사용자가 "이름 다시 지어줘" 를 누르는 기능).
**첫 질문 때는 `/v1/chat` 에 `generate_name: true` 를 넣는 쪽을 쓰세요.**

두 엔드포인트 모두 LLM 호출이 실패해도 500이 아니라 폴백 값을 돌려줍니다
(`topic` → `기타`, `name` → 질문 앞부분).

---

## 7. LLM 서비스가 RAG에 요청하는 계약

이 문서는 **LLM 서비스가 제공하는** API 명세입니다.
거꾸로 RAG 서비스(8002)에 **요구하는** 계약은 별도 문서로 분리했습니다.

→ [RAG_REQUIRED_API.md](RAG_REQUIRED_API.md) (수신자: Member C)

챗봇 서버 입장에서는 알 필요가 없지만, RAG가 죽어도 이 서비스가 `500` 대신
`200 + rag_degraded: true` 로 응답한다는 점만 기억하시면 됩니다.

---

## 8. 로컬 실행

```bash
cd LLM
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env      # API 키 채우기
uvicorn app.main:app --reload --port 8001
```

`http://localhost:8001/docs` 에서 바로 눌러볼 수 있습니다.
API 키가 아직 없으면 `.env` 에 `LLM_MODE=mock` 을 넣으면 고정 응답으로 화면을 붙여볼 수 있습니다. **응답 형식은 실제와 동일합니다.**
