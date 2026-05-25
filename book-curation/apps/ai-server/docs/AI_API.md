## 작업 내용

- FastAPI 기반 AI 도서 추천 API 구현
- Qdrant 벡터 검색 연동
- CLOVA 기반 기존 임베딩 검색 및 추천 응답 생성 구조 유지
- KURE-v1 기반 별도 Qdrant 컬렉션/검색기 추가
- 추천 후보 중복 제거 및 프로필 리랭킹 구조 개선
- GitLab CI/CD에 AI 서버 자동배포 job 추가
- dev 브랜치 merge 시 AI FastAPI 서버 자동 재배포

---

## 호출 구조

프론트에서 FastAPI를 직접 호출하지 않습니다.

```txt
Frontend
→ Spring Backend
→ FastAPI AI Server
→ Qdrant
   ├─ books: CLOVA 임베딩 기반 기존 컬렉션
   └─ books_kure: KURE-v1 임베딩 기반 별도 컬렉션
→ CLOVA Chat
→ Spring Backend
→ Frontend
```

본 FastAPI는 외부 공개 API가 아니라 Spring Backend에서 내부 호출하는 AI 추천 API입니다.

---

## AI Recommendation API

### Base URL

#### 내부 (Spring → FastAPI)

```txt
http://book-curation-ai:8001
```

#### 외부 테스트용 (개발용)

```txt
http://<SERVER_IP>:18001
```

---

### 도서 추천

```http
POST /api/v1/chat/recommend
Content-Type: application/json
```

인증 필요 여부: 아니오 (내부 API)

설명:

- FastAPI 기반 AI 추천 서비스
- Spring Backend에서 내부적으로 호출
- 사용자 질의를 기반으로 Qdrant 벡터 검색 수행
- 기존 CLOVA 임베딩 기반 `books` 컬렉션 검색 구조 유지
- KURE-v1 임베딩 기반 `books_kure` 별도 검색 컬렉션 추가
- 검색된 후보 도서를 기반으로 CLOVA Chat이 최종 추천 응답 생성
- CLOVA는 기존 임베딩 검색 구조 및 최종 답변 생성에 사용
- KURE는 별도 임베딩/검색 실험 및 전환 후보로 사용

---

## 추천 처리 흐름

```txt
사용자 질문
→ Spring Backend
→ FastAPI AI Server
→ 질문 intent 분류
→ Qdrant 후보 검색
   ├─ 기본: CLOVA 임베딩 기반 books 컬렉션
   └─ 실험/전환용: KURE-v1 임베딩 기반 books_kure 컬렉션
→ 후보 도서 필터링 및 중복 제거
→ 로그인 사용자의 경우 온보딩 프로필 기반 리랭킹
→ CLOVA Chat으로 최종 추천 문장 생성
→ Spring Backend
→ Frontend
```

- CLOVA 임베딩 기반 기존 검색 구조는 유지합니다.
- KURE-v1은 기존 검색 구조를 대체하지 않고, 별도 컬렉션과 검색기로 추가됩니다.
- CLOVA Chat은 최종 추천 문장 생성에 계속 사용합니다.

---

## 임베딩 / 검색 구조

### CLOVA 기반 검색

기존 운영 검색 구조입니다.

```txt
Collection: books
Embedding: CLOVA Embedding
Vector size: 1024
Distance: Cosine
```

### KURE 기반 검색

KURE-v1 임베딩으로 별도 컬렉션을 생성해 테스트/전환용으로 사용할 수 있습니다.

```txt
Collection: books_kure
Embedding: nlpai-lab/KURE-v1
Vector size: 1024
Distance: Cosine
```

KURE 컬렉션은 기존 CLOVA 기반 `books` 컬렉션을 삭제하거나 대체하지 않습니다.

---

## 요청 body

| 필드 | 타입 | 필수 | 설명 |
|---|---|---:|---|
| query | string | O | 사용자 도서 추천 요청 문장 |
| personalized | boolean | X | 로그인 사용자 개인화 추천 적용 여부 |
| user_id | string | X | 로그인 사용자 식별자 |
| history | array | X | 멀티턴 대화 이력 |
| user_profile | object | X | 온보딩/사용자 프로필 정보 |
| guest | boolean | X | 비로그인 사용자 여부 |

요청 예시:

```json
{
  "query": "과학 책 추천해줘"
}
```

로그인 개인화 요청 예시:

```json
{
  "user_id": "1",
  "query": "나한테 맞는 책 추천해줘",
  "personalized": true,
  "guest": false,
  "user_profile": {
    "preferred_genres": ["소설", "판타지", "추리"],
    "preferred_books": [
      {
        "title": "달러구트 꿈 백화점",
        "author": "이미예"
      }
    ],
    "disliked_books": []
  }
}
```

---

## 응답

응답 예시:

```json
{
  "query": "과학 책 추천해줘",
  "answer": "추천 문장...",
  "guest": false,
  "personalized": false,
  "profile_applied": false,
  "intent": "recommend",
  "intent_source": "llm",
  "requires_history": false,
  "recommend_mode": "balanced",
  "candidates": [
    {
      "title": "지켜줘서 고마워!",
      "author": "편집부 저",
      "ori_cover_s": "https://...",
      "cover_url": "https://...",
      "simple_intro": "..."
    }
  ]
}
```

---

## 응답 필드

| 필드 | 타입 | 설명 |
|---|---|---|
| query | string | 사용자 입력 |
| answer | string | 추천 응답 |
| guest | boolean | 비로그인 여부 |
| personalized | boolean | 개인화 요청 여부 |
| profile_applied | boolean | 실제 프로필 적용 여부 |
| intent | string | 1차 intent 분류 결과 |
| intent_source | string | intent 분류 출처 |
| requires_history | boolean | 이전 대화 참조 여부 |
| recommend_mode | string | 추천 방식 분류 결과 |
| candidates | array | 추천 후보 도서 |
| candidates[].title | string | 도서명 |
| candidates[].author | string | 저자 |
| candidates[].publisher | string | 출판사 |
| candidates[].ori_cover_s | string | 원본 표지 이미지 URL |
| candidates[].cover_url | string | 표지 이미지 URL |
| candidates[].simple_intro | string | 도서 소개 |
| candidates[].description | string | 도서 설명 |
| candidates[].categories | array | 카테고리 |
| candidates[].score_detail | object | 개인화 리랭킹 점수 상세 정보 |

---

## 추천 intent / mode

### 1차 intent

사용자 질문은 먼저 아래 셋 중 하나로 분류합니다.

| intent | 설명 |
|---|---|
| recommend | 도서 추천 요청 |
| service | 서비스 사용법, 추천 기준 설명, 인사, 독서 관련 일반 질문 |
| unsupported | 도서 추천 서비스 범위 밖 질문 |

### 2차 recommend mode

`recommend`로 분류된 경우, 추천 방식을 추가로 분류합니다.

| recommend_mode | 설명 |
|---|---|
| specific | 작가, 제목, ISBN, 제외 조건, 학습 목적 등 현재 query 조건을 우선 |
| personalized | “나한테 맞는 책”, “내 취향”처럼 온보딩 프로필을 우선 |
| balanced | 장르, 분위기, 감정 조건과 사용자 취향을 함께 반영 |

예시:

```txt
수학 올림피아드 문제집 추천해줘 → specific
나한테 맞는 책 추천해줘 → personalized
잔잔한 소설 추천해줘 → balanced
```

---

## KURE 인덱싱

KURE-v1 기반 Qdrant 컬렉션을 생성하려면 아래 명령을 사용합니다.

```bash
python3 -m app.services.kure_qdrant_indexer /path/books_sample_100000.json
```

기존 `books_kure` 컬렉션을 강제로 재생성하려면:

```bash
python3 -m app.services.kure_qdrant_indexer /path/books_sample_100000.json --recreate
```

---

## KURE 검색 구조

KURE 검색기는 다음 순서로 검색합니다.

```txt
1. 사용자 질문에서 keyword 추출
2. 제목/저자/ISBN 검색이면 payload filter 우선 검색
3. payload filter 실패 시 scroll fallback
4. keyword 검색 결과가 없으면 vector search 수행
5. strict keyword query는 keyword miss 시 vector fallback 방지
```

검색 대상 컬렉션:

```txt
books_kure
```

payload index 대상:

```txt
isbn
title
author
publisher
categories
cate_depth1
kcid
embedding_model
```

---

## 에러 응답

```json
{
  "message": "에러 메시지"
}
```

| HTTP Status | 설명 |
|---:|---|
| 400 | 잘못된 요청 |
| 500 | 서버 오류 |

---

## 참고

- CLOVA는 기존 임베딩 검색 구조와 최종 추천 문장 생성에 사용됩니다.
- KURE-v1은 별도 Qdrant 컬렉션 기반 검색 실험/전환용으로 추가되었습니다.
- 현재 구조에서 KURE는 CLOVA Chat을 대체하지 않습니다.
- 추천 후보는 Qdrant 검색 결과 안에서만 선택합니다.
- 로그인 사용자는 `personalized=true`와 `user_profile`이 전달될 때 프로필 기반 리랭킹이 적용됩니다.
- 비로그인 사용자는 프로필 리랭킹 없이 query 기반 추천을 수행합니다.
- 외부 API(CLOVA) 호출로 인해 간헐적으로 응답 지연 또는 실패가 발생할 수 있습니다.
- KURE 임베딩은 로컬 모델 로딩이 필요하므로 최초 실행 시 모델 다운로드/로딩 시간이 발생할 수 있습니다.

---

## 테스트

NAS 서버 내부에서 테스트:

```bash
curl -X POST http://localhost:18001/api/v1/chat/recommend \
  -H "Content-Type: application/json" \
  -d '{"query":"과학 책 추천해줘"}'
```

외부 개발 환경에서 테스트:

```bash
curl -X POST http://<SERVER_IP>:18001/api/v1/chat/recommend \
  -H "Content-Type: application/json" \
  -d '{"query":"과학 책 추천해줘"}'
```

개인화 추천 테스트:

```bash
curl -X POST http://localhost:18001/api/v1/chat/recommend \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "1",
    "query": "나한테 맞는 책 추천해줘",
    "personalized": true,
    "guest": false,
    "user_profile": {
      "preferred_genres": ["소설", "판타지", "추리"],
      "preferred_books": [
        {
          "title": "달러구트 꿈 백화점",
          "author": "이미예"
        }
      ],
      "disliked_books": []
    }
  }'
```

확인 항목:

- FastAPI 정상 실행 확인
- Qdrant 검색 정상 확인
- 기존 CLOVA 기반 `books` 컬렉션 검색 구조 유지 확인
- KURE 기반 `books_kure` 컬렉션 검색 정상 확인
- CLOVA Chat 응답 생성 확인
- 추천 후보 중복 제거 확인
- 로그인 사용자 프로필 리랭킹 확인
- `recommend_mode` 분류 확인

---

## CI/CD

다음 경로 변경 시 배포 실행

- apps/ai-server/**/*
- packages/prompts/**/*
- .gitlab-ci.yml