# RAG 문서 관리 시스템

이 프로젝트는 FastAPI + MySQL + FAISS + sentence-transformers 기반의 문서 관리 및 RAG 검색 웹앱입니다.

## 디렉터리 구조

```text
RAG/
├── admin_doc.html          # 문서 관리 메인 화면
├── app.py                  # FastAPI 백엔드 서버
├── config.py               # 서버/DB/RAG 관련 설정
├── rag_pipeline.py         # 전처리, 청킹, 임베딩, 벡터 검색 로직
├── requirements.txt        # Python 패키지 목록
├── sql/
│   ├── rag_chatbot_schema.sql  # 테이블 스키마
│   └── rag_document.sql        # 초기 문서 샘플 데이터
├── res/
│   ├── css/rag.css         # UI 스타일
│   ├── js/rag.js           # 문서 목록/업로드/선택 UI
│   ├── img/                # 이미지 리소스
│   └── pdf/                # 업로드 PDF 및 delete 폴더
└── vector_store/          # 문서별 FAISS 인덱스 저장 위치
```

## 1. 사전 준비

- Python 3.10 이상 권장
- MySQL Server 실행 중
- PDF 파일 저장 경로가 접근 가능해야 함

## 2. 데이터베이스 설정

MySQL에서 스키마를 먼저 생성합니다.

```bash
mysql -u root -p < sql/rag_chatbot_schema.sql
```

그다음 초기 문서 샘플 데이터를 넣습니다.

```bash
mysql -u root -p < sql/rag_document.sql
```

> `rag_document.sql`은 `document` 테이블을 비우고 샘플 문서 레코드를 다시 삽입합니다.

## 3. Python 환경 설정

Windows 기준 예시입니다.

```bash
cd RAG
py -3.11 -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

## 4. 설정값 확인

`config.py`에서 다음 값을 확인하세요.

- `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`
- `API_PORT` 기본값은 `8001`

예시:

```python
DB_PASSWORD = "1234"
DB_NAME = "rag_chatbot"
```

## 5. 실행

```bash
python app.py
```

서버는 다음 주소에서 실행됩니다.

- http://localhost:8001

브라우저에서 다음 페이지를 열면 됩니다.

- http://localhost:8001/admin_doc.html

## 6. 주요 API

- `GET /api/documents` : 문서 목록 조회
- `GET /api/documents/{doc_id}` : 특정 문서 조회
- `POST /api/documents/upload` : PDF 업로드
- `DELETE /api/documents/{doc_id}` : 문서 삭제(soft delete)
- `PUT /api/documents/{doc_id}/load` : 문서를 벡터 DB에 적재
- `POST /api/search` : 질의 기반 검색

## 7. 현재 구현 기능

- 문서 업로드/삭제
- 문서 목록 표기 및 선택
- 리스트/큐브 뷰 전환
- 섹션 아코디언 접기/펼치기
- PDF 텍스트 추출 및 청크 분할
- FAISS 기반 벡터 검색
- BM25 키워드 보강 검색
- reranker 기반 결과 재정렬

## 8. 참고

- 업로드된 PDF는 `res/pdf/` 아래에 저장됩니다.
- 삭제된 PDF는 `res/pdf/delete/`로 이동됩니다.
- 벡터 인덱스는 `vector_store/<doc_id>/` 아래에 생성됩니다.
- 모델 로딩이 처음 실행 시 다소 오래 걸릴 수 있습니다.

## 9. Windows 유용 명령

```bash
netstat -ano | findstr :8001
taskkill /PID 12345 /F
```

