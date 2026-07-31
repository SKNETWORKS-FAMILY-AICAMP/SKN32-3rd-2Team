# LLM 서비스 API 명세서 (제공)

> Smart HR — Member D (LLM 파트) 산출물
> **받는 사람: 챗봇 서버 / 프론트 담당 (WEB 파트, port 8000)**
>
> 이 문서는 **LLM 서비스가 제공하는** API입니다.
> 제가 RAG 담당자에게 **요청드리는** 명세는 → [RAG_REQUIRED_API.md](RAG_REQUIRED_API.md)

- **Base URL**: `http://localhost:8001`
- **Swagger (자동 생성, 항상 최신)**: `http://localhost:8001/docs`
- 모든 요청/응답 `Content-Type: application/json`, 인코딩 UTF-8

---

## 0. 이 서비스의 위치

```
웹 프론트엔드 → 챗봇 서버(8000) → [LLM 서비스(8001)] → RAG 서비스(8002)
                      ↓
                     MySQL
```

**LLM 서비스는 DB에 직접 쓰지 않습니다.** 시퀀스다이어그램(PPT 17p)대로 DB 저장은 챗봇 서버가 담당합니다.
이 서비스는 답변 본문·주제·근거 문서를 JSON으로 돌려줄 뿐이고, 그걸 `chat` / `chatroom` 테이블에 넣는 건 챗봇 서버 몫입니다.

### DB 매핑 요약

| 이 API의 응답 필드 | 저장 위치 | 컬럼 제약 |
|---|---|---|
| `ChatResponse.answer` | `chat.message` (speaker=`llm`) | TEXT |
| `ChatResponse.topic` | `chat.topic` (사용자 발화 행) | VARCHAR(100) — 서버가 보장 |
| `ChatroomNameResponse.name` | `chatroom.chatroom_name` | VARCHAR(100) — 서버가 보장 |

길이 제한은 **LLM 서비스 쪽에서 이미 자르고 보내므로** 챗봇 서버가 추가로 truncate 할 필요 없습니다.

---

## 1. `POST /v1/chat` — 답변 생성

### Request

```json
{
  "chatroom_id": "3f1c...-uuid",
  "message": "연차 며칠까지 쓸 수 있나요?",
  "history": [
    { "speaker": "user", "message": "안녕하세요" },
    { "speaker": "llm",  "message": "무엇을 도와드릴까요?" }
  ],
  "provider": "openai",
  "use_rag": true
}
```

| 필드 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `chatroom_id` | string | ✅ | `chatroom.chatroom_id` (UUID) |
| `message` | string | ✅ | 사용자 질문 |
| `history` | array | ❌ | 이전 대화. **최근 몇 턴만** 보내면 됩니다(전체 X) |
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
  "usage": {
    "provider": "openai",
    "model": "gpt-4o-mini",
    "prompt_tokens": 1523,
    "completion_tokens": 210,
    "latency_ms": 2140,
    "ttft_ms": null,
    "rag_ms": 180
  }
}
```

- `sources` → 스토리보드 13p "AI 답변 하단에 근거 문서명 노출"에 그대로 쓰면 됩니다.
- `rag_degraded: true` 면 RAG 검색에 실패해 문서 없이 생성된 답변입니다. **에러가 아니라 정상 200**이고, `sources`는 빈 배열입니다. UI에서 "근거 문서를 찾지 못했습니다" 정도로 표시하면 됩니다.
- `topic` 은 `/v1/topic` 을 따로 부를 필요 없이 여기에 이미 들어 있습니다.

---

## 2. `POST /v1/chat/stream` — 답변 생성 (SSE 스트리밍)

스토리보드 13p "실시간 스트리밍 대화 UI/UX"용. Request 형식은 `/v1/chat` 과 동일합니다.

`Content-Type: text/event-stream` 으로 아래 순서로 내려옵니다.

```
event: sources
data: {"sources":[{"doc_id":12,"original_file_name":"5.근로기준법(법률).pdf", ...}],"rag_degraded":false}

event: token
data: {"delta":"연차유급"}

event: token
data: {"delta":"휴가는 "}

... (반복) ...

event: done
data: {"topic":"휴가/휴직","usage":{"provider":"openai","model":"gpt-4o-mini","latency_ms":2140,"ttft_ms":410, ...}}
```

에러가 나면 마지막에 `done` 대신 `error` 이벤트가 옵니다.

```
event: error
data: {"error_code":"LLM_TIMEOUT","message":"일시적인 오류입니다. 잠시 후 다시 시도해주세요."}
```

> `sources` 가 **토큰보다 먼저** 오므로, 근거 문서 영역을 답변 생성 전에 미리 그릴 수 있습니다.

---

## 3. `POST /v1/topic` — 주제 분류

`chat.topic` 채우기용. `/v1/chat` 응답에 이미 포함되므로 **보통은 따로 부를 필요가 없고**, 과거 데이터 일괄 분류나 재분류 때 씁니다.

### Request
```json
{ "message": "연차 며칠까지 쓸 수 있나요?", "source_files": ["5.근로기준법(법률).pdf"] }
```

`source_files` 는 선택입니다. RAG가 찾은 문서명을 넣으면 분류 정확도가 올라갑니다.

### Response `200`
```json
{ "topic": "휴가/휴직", "cached": false }
```

### 카테고리 목록 (8종) — ⚠️ 대시보드 담당자 확인 필요

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

**바꾸고 싶으면 말씀해 주세요.** `app/domain.py` 의 `TOPIC_CATEGORIES` 상수 한 줄이라 반영은 즉시 됩니다. 확정 전까지는 위 8종으로 동작합니다.

카테고리 목록은 `GET /health` 의 `topic_categories` 로도 읽을 수 있으니, 대시보드에서 차트 축을 하드코딩하지 말고 이걸 받아 쓰면 목록이 바뀌어도 자동으로 맞습니다.

---

## 4. `POST /v1/chatroom-name` — 채팅방 이름 생성

`chatroom.chatroom_name` 의 기본값은 `'새 대화'` 입니다. 사용자가 첫 질문을 보낸 시점에 이 API를 불러 이름을 갱신하면 사이드바가 읽기 좋아집니다.

### Request
```json
{ "message": "연차 며칠까지 쓸 수 있나요?" }
```

### Response `200`
```json
{ "name": "연차 사용 일수 문의" }
```

20자 내외 한국어. 100자를 넘지 않음이 보장됩니다.

---

## 5. `GET /health`

```json
{
  "status": "ok",
  "providers": { "openai": true, "gemini": true },
  "default_provider": "openai",
  "rag": "mock",
  "topic_categories": ["휴가/휴직", "근태/근무형태", "..."]
}
```

`rag` 값: `up`(실제 RAG 연결됨) / `down`(연결 실패) / `mock`(개발용 고정 응답 모드)

---

## 6. 에러 규약

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

**RAG 실패는 에러가 아닙니다.** `200` + `rag_degraded: true` + `sources: []` 로 내려갑니다. 챗봇이 문서 없이라도 답하는 게 낫다는 판단입니다.

---

## 7. LLM 서비스가 RAG에 요청하는 계약

이 문서는 **LLM 서비스가 제공하는** API 명세입니다.
LLM 서비스가 거꾸로 RAG 서비스(8002)에 **요구하는** 계약은 별도 문서로 분리했습니다.

→ [RAG_REQUIRED_API.md](RAG_REQUIRED_API.md) (수신자: Member C)

챗봇 서버 입장에서는 알 필요가 없는 내용이지만, RAG가 죽었을 때 이 서비스가
`500` 대신 `200 + rag_degraded: true` 로 응답한다는 점만 기억하시면 됩니다.

---

## 8. 로컬 실행

```bash
cd LLM
pip install -r requirements.txt
cp .env.example .env      # API 키 채우기
uvicorn app.main:app --reload --port 8001
```

`http://localhost:8001/docs` 에서 바로 눌러볼 수 있습니다.
