# LLM 서비스 (Smart HR)

사내 HR 규정 질의응답 시스템의 **LLM 파트**. 답변 생성 / 주제 분류 / 채팅방 이름 생성을 담당한다.

> 담당: Member D · 브랜치 `LLM` · 포트 `8002`

## 명세서 두 종류

| 문서 | 방향 | 받는 사람 |
|---|---|---|
| [docs/API.md](docs/API.md) | **제공** — 이 서비스가 노출하는 API | WEB 파트 (챗봇 서버 / 프론트, 8000) |
| [docs/RAG_REQUIRED_API.md](docs/RAG_REQUIRED_API.md) | **요청** — 이 서비스가 필요로 하는 API | RAG 파트 (Member C, 8001) |

---

## 아키텍처에서의 위치

```
웹 프론트엔드 → 챗봇 서버(8000) → [LLM 서비스(8002)] → RAG 서비스(8001)
                      ↓
                    MySQL
```

**이 서비스는 DB에 쓰지 않는다.** 시퀀스다이어그램대로 `chat` / `chatroom` 테이블 저장은 챗봇 서버가 담당하고,
여기서는 답변 본문·주제·근거 문서를 JSON으로 돌려주기만 한다. 덕분에 DB 커넥션이 없고 팀원 작업과 충돌하지 않는다.

---

## 실행

```bash
cd LLM
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux
pip install -r requirements.txt

cp .env.example .env            # 값 채우기
uvicorn app.main:app --reload --port 8002
```

> ⚠️ **반드시 가상환경에서 설치하세요.** 전역 환경에 바로 설치하면 다른 프로젝트의 패키지 버전을 깨뜨릴 수 있습니다.

- Swagger: <http://localhost:8002/docs>
- 헬스체크: <http://localhost:8002/health>

### API 키 없이 돌려보기

키 발급 전에도 화면을 붙여볼 수 있도록 고정 응답 모드를 넣어 두었다.

```bash
# .env
LLM_MODE=mock     # LLM API 호출 안 함
RAG_MODE=mock     # RAG 서비스 호출 안 함
```

**공개 API 계약은 live 모드와 완전히 동일하다.** 요청 body 로는 선택할 수 없고 환경변수로만 켜지므로,
프론트 코드는 mock 여부를 알 필요가 없다.

### Qwen(로컬 모델)은 설치하지 않아도 된다

이 저장소는 프로바이더를 셋 지원한다 — `openai`, `gemini`, `qwen`.
이 중 **Qwen 만 로컬에 [Ollama](https://ollama.com) 가 떠 있어야** 동작한다.

**Ollama 를 설치하지 않아도 서비스는 정상적으로 돈다.** 기본 프로바이더가
`openai` 라 평소 경로는 Qwen 을 전혀 타지 않는다. 다른 PC 에서 받아 실행할 때
따로 할 일은 없다.

- 서버 기동: 정상 (예열 실패 경고만 로그에 남는다)
- `POST /v1/chat`: 정상
- `GET /health`: `"qwen": false` 로 표시된다
- `provider: "qwen"` 을 **명시해서** 부른 경우에만 `503 LLM_UNAVAILABLE`

굳이 Qwen 을 써보려면 Ollama 설치 후 아래를 실행하면 된다. 4.7GB 를 내려받고
실행 중에 VRAM 을 계속 점유하므로, 필요할 때만 하면 된다.

```bash
ollama pull qwen2.5:7b
```

Qwen 을 왜 넣었는지와 실측 성능은 [docs/PERFORMANCE_REPORT.md](docs/PERFORMANCE_REPORT.md)
4절 참조 — 요약하면 **주제 분류에는 쓸 만하지만(정확도 94%, 무료) 답변 생성에는
쓸 수 없다**(한국어 질문에 중국어로 답하는 경우가 있다).

---

## 환경변수

| 키 | 기본값 | 설명 |
|---|---|---|
| `LLM_MODE` | `live` | `mock` 이면 LLM API 호출 없이 고정 응답 |
| `DEFAULT_PROVIDER` | `openai` | `openai` \| `gemini`. 요청별로 덮어쓸 수 있음 |
| `LLM_TIMEOUT_SEC` | `5.0` | 초과 시 504 + 한국어 안내 (스토리보드 13p 요구사항) |
| `OPENAI_API_KEY` / `OPENAI_MODEL` | — / `gpt-4o-mini` | |
| `GEMINI_API_KEY` / `GEMINI_MODEL` | — / `gemini-3.5-flash` | |
| `RAG_MODE` | `mock` | `live` 면 실제 RAG 서비스 호출 |
| `RAG_BASE_URL` | `http://localhost:8001` | |
| `RAG_TIMEOUT_SEC` / `RAG_TOP_K` | `3.0` / `5` | |
| `METRICS_ENABLED` / `METRICS_PATH` | `true` / `logs/metrics.jsonl` | 계측 로그. 성능 보고서 입력 |

`.env` 는 `.gitignore` 에 있으므로 **API 키가 커밋될 일은 없다.**

`config.py` 에 설정을 추가했으면 `.env.example` 갱신을 잊지 않도록 아래로 확인한다.

```bash
python scripts/check_env_example.py
```

---

## 폴더 구조

```
app/
├── main.py              FastAPI 앱, 예외 → 에러 규약 변환
├── config.py            .env 로딩
├── domain.py            ★ TOPIC_CATEGORIES — 카테고리 바꿀 땐 여기만
├── schemas.py           API 계약의 단일 출처
├── prompts.py           시스템 프롬프트 (튜닝은 여기서만)
├── errors.py            한국어 메시지를 담은 예외
├── metrics.py           지연/토큰 JSONL 기록
├── routers/             chat.py, meta.py
├── providers/           base(Protocol) / openai / gemini / mock / registry
└── services/            rag_client, answer, topic, naming
```

---

## 설계 메모

### 주제(topic)를 '생성'이 아니라 '분류'로 다루는 이유

대시보드 도넛 차트가 `chat.topic` 을 `GROUP BY` 하기 때문에, LLM이 매번 다른 문구를 뱉으면 차트가 조각난다.
그래서 **디코딩 단계에서 enum 제약**을 건다 — OpenAI는 Structured Outputs(`strict: true`), Gemini는 `response_schema` 의 enum.
목록 밖 값이 *생성 자체가 불가능*해진다.

`seed` 고정은 쓰지 않는다. 두 벤더 모두 best-effort 라 보장되지 않고, 무엇보다 입력 문장이 조금만 달라지면
("연차 며칠?" vs "휴가 얼마나 남았어요?") 아무 효과가 없다.

그 위에 방어층 2개를 더 둔다.
1. 화이트리스트 검증 → 목록 밖이면 `기타`
2. 질문 정규화 후 해시 캐시 → 같은 질문은 항상 같은 결과 (시연 재현성 + 호출비 절감)

카테고리 8종은 임의로 정한 게 아니라 `RAG/res/pdf/` 의 실제 규정·법령 PDF 28건을 묶어 도출했다. 근거표는 [docs/API.md](docs/API.md) 3절.

### RAG 실패는 에러가 아니다

검색이 안 되면 `500` 대신 `200 + rag_degraded: true + sources: []` 로 응답한다.
문서 없이라도 답하는 편이 사용자에게 낫다는 판단.

### 답변 생성과 주제 분류는 동시에 돈다

서로 의존하지 않으므로 `asyncio.gather` 로 병렬 실행한다. 순차로 하면 분류 지연이 그대로 사용자 대기 시간에 더해진다.

### 계측값은 응답이 아니라 로그로 나간다

지연·토큰·모델명은 API 응답에 넣지 않는다. 대응하는 DB 컬럼이 없고 화면에 쓸 일도 없어서,
`METRICS_PATH` 의 JSONL 파일과 콘솔 로그에만 남긴다. WEB 이 받는 건 실제로 저장·표시할 값뿐이다.

```
2026-07-31 15:08:16 INFO [llm.metrics] chat room=r topic=휴가/휴직 docs=2 | openai/gpt-4o-mini 2140ms rag=180ms tok=1523/210
```

성능 보고서(`bench/report.py`)는 이 JSONL 을 읽어 집계한다.
한국어 Windows 콘솔이 cp949 라 로그를 파일로 리다이렉트하면 한글이 깨지므로, 출력 스트림을 UTF-8 로 고정해 두었다.

---

## 검증 완료 항목

`LLM_MODE=mock` 기준으로 아래를 확인했다.

| 항목 | 결과 |
|---|---|
| 5개 엔드포인트 OpenAPI 등록 | ✅ |
| `/v1/chat` 응답이 `answer` / `topic` / `sources` / `rag_degraded` 4개뿐 | ✅ |
| 계측값이 응답에 없고 `logs/metrics.jsonl` + 콘솔에만 기록 | ✅ |
| 로그 파일이 UTF-8 로 읽힘 (cp949 깨짐 없음) | ✅ |
| `/v1/chat/stream` 이벤트 순서 `sources → token×N → done` | ✅ |
| 패러프레이즈 7종이 모두 enum 8종 안으로 분류 | ✅ |
| 정규화 캐시 적중 (`"연차 며칠?"` == `"  연차 며칠???  "`) | ✅ |
| `chatroom_name` 100자 제한 준수 | ✅ |
| RAG 다운 → `200 rag_degraded=true`, `/health rag=down` | ✅ |
| 타임아웃 → `504 LLM_TIMEOUT` + 한국어 메시지 | ✅ |
| 키 미설정 → `503 PROVIDER_NOT_CONFIGURED`, `/health degraded` | ✅ |
| 스키마 위반 → `422 INVALID_REQUEST` | ✅ |

**실제 LLM API 호출(live 모드)은 아직 검증 전** — API 키가 필요하다.

---

## 남은 작업

- [ ] `live` 모드 실제 호출 검증 (OpenAI / Gemini 키 필요)
- [ ] RAG 서비스 실연동 (Member C 와 `/v1/search` 계약 확정)
- [ ] 카테고리 8종 팀 확정 (Member B)
- [ ] `bench/` 벤치마크 + `docs/PERFORMANCE_REPORT.md`
