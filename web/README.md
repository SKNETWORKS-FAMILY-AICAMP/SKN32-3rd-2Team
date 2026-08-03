# RAG 챗봇 - 로그인 / 회원가입 / 메인 화면

## 실행 방법

```bash
pip install -r requirements.txt
python run.py
```

브라우저에서 http://localhost:8000/login 접속

## 환경변수

| 변수 | 설명                                                                                                                       | 기본값                    |
|---|--------------------------------------------------------------------------------------------------------------------------|------------------------|
| `DATABASE_URL` | MySQL 연결 문자열. 예: `mysql+pymysql://change-user:change-pw@change-ip:change-port/rag_chatbot?charset=utf8mb4`               | 미설정 시 에러               |
| `SESSION_SECRET_KEY` | 세션 쿠키 서명 키 (운영 배포 시 반드시 변경)                                                                                              | `dev-secret-change-me` |
| `CHAT_API_BASE_URL` | Chat API 서버 주소. 예: `https://chat-api.example.com`. 미설정 시 채팅 응답 요청이 `PROVIDER_NOT_CONFIGURED` 오류로 즉시 실패합니다 (서버 자체는 정상 기동됨) | 미설정 |
| `CHAT_API_TIMEOUT_SECONDS` | Chat API 응답 대기 타임아웃(초). Chat API 서버의 자체 생성 타임아웃(5초)보다 넉넉하게 잡아야 서버가 준 504 응답을 우리 쪽 타임아웃이 가로채지 않습니다                        | `15` |
| `DOC_API_BASE_URL` | RAG API 서버 주소. 예: `https://chat-api.example.com`.  | 미설정 |

## 화면 구성

- `GET /login` : 로그인 화면 (회원가입 버튼 클릭 시 모달 오픈)
- `POST /auth/login` : 로그인 처리, 성공 시 `/main`으로 리다이렉트
- `POST /auth/signup` : 회원가입 처리 (fetch로 비동기 호출, 모달 내에서 완료)
- `GET /main` : 로그인 후 메인 화면 (상단 헤더 + 좌측 사이드 메뉴). 미로그인 시 `/login`으로 리다이렉트
- `POST /auth/logout` : 로그아웃

## 세션 정책

- 로그인 성공 시 서버 사이드 세션(서명 쿠키)에 `user_id`, `name`, `is_admin`, `login_at`을 저장합니다.
- 세션 유효 시간은 3시간(`app/auth.py`의 `SESSION_MAX_AGE_SECONDS`)이며, 쿠키 자체의 만료 시간과 서버 측 `login_at` 검증을 이중으로 적용합니다.
- 관리자 계정(`is_admin=True`)으로 로그인하면 사이드 메뉴에 통계 / RAG 문서관리 / 사용자 관리 그룹이 추가로 노출됩니다. 현재는 메뉴만 노출되며 각 화면은 이후 단계에서 구현합니다.