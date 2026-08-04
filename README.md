# SKN32-3rd-2Team

# SHS — RAG 기반 교내 규정 질의응답 서비스

교내 구성원이 학교 규정 및 행정 문서를 기반으로 질문하면,
**RAG(Retrieval-Augmented Generation) 기술을 활용하여 실제 문서를 검색하고 근거 기반 답변을 제공하는 AI 행정 지원 서비스**입니다.

일반적인 LLM은 공개된 지식은 알고 있지만, 학교별 내부 규정·업무 절차·행정 문서는 학습되어 있지 않습니다.

본 서비스는 교내 규정 문서를 검색 가능한 지식 데이터로 구축하고,
질문 시 관련 문서를 찾아 LLM에게 제공함으로써 **환각(Hallucination)을 줄이고 신뢰 가능한 답변**을 제공합니다.



<br><br><br>
!!!!!!!!!!!발표본 완성 후 해당 위치에 캡쳐본이 들어갑니다!!!!!!!!!!!
<br><br><br>

---

# 프로젝트 개요

## 문제 상황

학교 구성원은 다음과 같은 문의를 반복적으로 합니다.

* 휴가 및 복무 관련 규정
* 연구년 신청 조건
* 출장 및 행정 처리 절차
* 각종 학교 내부 규정 확인
* 담당 부서 및 처리 방법 문의

하지만 기존 방식은:

```
질문 발생
 ↓
규정 문서 직접 검색
 ↓
담당 부서 문의
 ↓
답변 대기
```

와 같은 비효율적인 과정을 거칩니다.

---

## 해결 방법


```
사용자 질문
      ↓
관련 규정 문서 검색 (RAG)
      ↓
검색 결과 기반 LLM 답변 생성
      ↓
답변 + 근거 문서 제공
```

방식을 통해 사용자가 자연어로 질문하고 즉시 규정 기반 답변을 받을 수 있도록 구현했습니다.

---

# 시스템 아키텍처

```text
                    교내 구성원
                         │
                         ▼
                WEB Service (8000)
        로그인 / 채팅 / 관리자 / 데이터 저장
                         │
                         ▼
                LLM Service (8002)
        답변 생성 / 주제 분류 / 채팅 제목 생성
                         │
                         ▼
                RAG Service (8001)
        문서 관리 / 임베딩 / 검색 / 재정렬
                         │
                         ▼
              MySQL + FAISS Vector Store
                         │
                         ▼
              교내 규정 및 행정 문서
```

---

# 서비스 구성

## 1. WEB Service (Port : 8000)

교내 구성원이 사용하는 웹 서비스 영역입니다.

### 담당 기능

* 사용자 인증
* 채팅 화면 제공
* 대화 이력 관리
* 관리자 기능
* 통계 화면
* 문서 관리 화면 연동

### 주요 기능

### 사용자

* 회원가입 / 로그인
* AI 규정 질의응답
* 채팅방 관리
* 답변 근거 문서 확인

### 관리자

* 사용자 관리
* 규정 문서 관리
* 문의 통계 확인

### 기술 스택

* FastAPI
* SQLAlchemy
* MySQL 8.0
* Jinja2 Server Side Rendering
* JavaScript
* CSS

---

# 2. LLM Service (Port : 8002)

AI 답변 생성과 자연어 처리 영역을 담당합니다.

사용자의 질문과 RAG 검색 결과를 기반으로 답변을 생성합니다.

## 주요 역할

* 규정 기반 답변 생성
* 문의 주제 분류
* 채팅방 제목 생성
* LLM Provider 관리

지원 모델:

* OpenAI
* Gemini
* Qwen (Ollama)

---

## 답변 생성 흐름

```text
사용자 질문
      ↓
RAG 서비스 요청
      ↓
관련 규정 검색 결과 수신
      ↓
질문 + 검색 문서 Prompt 구성
      ↓
LLM 답변 생성
      ↓
주제 분류
      ↓
WEB 서비스 반환
```

---

## 주제 분류 설계

관리자 통계 활용을 위해 LLM에게 자유롭게 주제를 생성하도록 하지 않고,
고정 카테고리 기반 분류 방식을 적용했습니다.

예:

```
"휴가 며칠 사용할 수 있나요?"
"연차 기준 알려주세요"
"휴가 규정 궁금합니다"
```

같은 질문은 모두:

```
휴가/휴직
```

으로 저장됩니다.

적용 방식:

```
Enum 제약 출력
        ↓
화이트리스트 검증
        ↓
정규화 캐시
        ↓
DB 저장
```

이를 통해 통계 데이터의 일관성을 유지합니다.

---

# 3. RAG Service (Port : 8001)

학교 규정 문서를 관리하고 검색하는 지식 기반 서비스입니다.

## 주요 역할

* PDF 문서 관리
* 문서 텍스트 추출
* Chunk 분할
* Embedding 생성
* Vector 검색
* 검색 결과 재정렬

---

## RAG Pipeline

```text
학교 규정 PDF
       ↓
텍스트 추출
       ↓
Chunk Split
       ↓
Embedding 생성
       ↓
FAISS 저장
       ↓
사용자 질문 Vector 검색
       ↓
BM25 + Vector Search
       ↓
Reranker 재정렬
       ↓
LLM 전달
```

---

## 기술 스택

* FastAPI
* MySQL
* FAISS
* sentence-transformers
* BM25
* Cross Encoder Reranker

Embedding:

```
jhgan/ko-sroberta-multitask
```

Reranker:

```
BAAI/bge-reranker-v2-m3
```

---

# RAG를 적용한 이유

일반 LLM은 학교 내부 규정을 알 수 없습니다.

예:

```
질문:
"연구년 신청 기준이 어떻게 되나요?"
```

일반 LLM:

```
학교마다 다르므로 확인이 필요합니다.
```

또는 학습 데이터 기반으로 잘못된 답변 생성 가능

RAG 적용:

```
질문
 ↓
학교 규정 검색
 ↓
실제 문서 전달
 ↓
근거 기반 답변 생성
```

따라서 학교별 규정과 절차를 반영한 정확한 답변이 가능합니다.

---

# 프로젝트 구조

```text

├── WEB/
│   ├── app/
│   ├── templates/
│   ├── static/
│   └── README.md
│
├── LLM/
│   ├── app/
│   │   ├── providers/
│   │   ├── routers/
│   │   └── services/
│   ├── bench/
│   └── README.md
│
├── RAG/
│   ├── app.py
│   ├── rag_pipeline.py
│   ├── vector_store/
│   ├── res/
│   └── README.md
│
└── README.md
```

---

# 실행 방법

서비스는 독립 서버 형태로 구성되어 있습니다.

실행 순서:

```
RAG Service
      ↓
LLM Service
      ↓
WEB Service
```

---

## 1. RAG 실행

```bash
cd RAG

python -m venv venv
venv\Scripts\activate

pip install -r requirements.txt

python app.py
```

실행:

```
http://localhost:8001
```

---

## 2. LLM 실행

```bash
cd LLM

python -m venv .venv
.venv\Scripts\activate

pip install -r requirements.txt

uvicorn app.main:app --reload --port 8002
```

실행:

```
http://localhost:8002/docs
```

---

## 3. WEB 실행

```bash
cd WEB

pip install -r requirements.txt

python run.py
```

실행:

```
http://localhost:8000
```

---

# 주요 설계 포인트

## 1. 서비스 분리 구조

WEB / LLM / RAG를 독립 서비스로 분리했습니다.

장점:

* 서비스별 독립 개발 가능
* 장애 영향 최소화
* 모델 교체 용이
* API 계약 기반 확장 가능

---

## 2. Stateless LLM 구조

LLM 서비스는 DB를 직접 관리하지 않습니다.

역할:

```
Request
 ↓
AI 처리
 ↓
JSON Response
```

저장과 관리는 WEB 서비스에서 담당합니다.

---

## 3. 검색 품질 개선

단순 Vector Search가 아닌:

```
Vector Search
+
BM25 Keyword Search
+
Reranker
```

구조를 적용하여 검색 정확도를 개선했습니다.

---

## 4. 운영 고려 사항

구현 사항:

* API Error 규격 통일
* Timeout 처리
* Provider 추상화
* Mock 모드 지원
* 성능 측정 환경 구성
* 개인정보 로그 보호
* 근거 기반 답변 처리

---

# 상세 문서

각 서비스별 상세 내용은 아래 README 참고

| 서비스 | 문서              |
| --- | --------------- |
| WEB | `WEB/README.md` | 
| LLM | `LLM/README.md` | 
| RAG | `RAG/README.md` | 

---


https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN32-3rd-2Team/blob/main/web/README.md<br>
https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN32-3rd-2Team/blob/main/LLM/README.md<br>
https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN32-3rd-2Team/blob/main/RAG/readme.md<br><br><br>

# Team Project

교내 규정과 행정 문서를 기반으로
구성원이 쉽고 빠르게 정보를 찾을 수 있도록 지원하는
RAG 기반 AI 행정 지원 서비스입니다.
