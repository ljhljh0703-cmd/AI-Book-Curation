
## 0. 문서 정보

|항목|내용|
|---|---|
|프로젝트명|북켓몬 (Bookemon)|
|버전|v2.0|
|최종 수정일|2026-04-21|
|작성 근거|기능 명세서 v1.1|

---

## 1. 기본 정보

### 1-1. Base URL

```
https://api.bookemon.com/v2
```

### 1-2. 인증

| 방식 | 위치 | 설명 |
|---|---|---|
| **Access Token** (Bearer JWT) | `Authorization` Header | 모든 인증 요청에 포함. 짧은 만료 시간 |
| **Refresh Token** | HttpOnly Cookie | Access Token 재발급 전용. 탈취 방지 |
| 예외 | — | `/auth/social`, `/auth/local`, `/auth/refresh` 는 Bearer 불필요 |

### 1-3. 공통 응답 형식

**성공**
```json
{
  "success": true,
  "data": { ... }
}
```

**실패**
```json
{
  "success": false,
  "error": {
    "code": "ERROR_CODE",
    "message": "사람이 읽을 수 있는 오류 메시지"
  }
}
```

### 1-4. 공통 에러 코드

| HTTP | 코드 | 설명 |
|---|---|---|
| 400 | `VALIDATION_ERROR` | 요청 파라미터 유효성 실패 |
| 400 | `SHELF_FULL` | 독서대 3권 초과 등록 시도 |
| 401 | `UNAUTHORIZED` | 인증 토큰 없음 또는 만료 |
| 403 | `FORBIDDEN` | 권한 없음 |
| 404 | `NOT_FOUND` | 리소스 없음 |
| 409 | `CONFLICT` | 중복 리소스 |
| 412 | `REVIEW_LOCKED` | 독서대 등록 후 72시간 미경과 |
| 429 | `RATE_LIMIT` | 일일 한도 초과 |
| 500 | `INTERNAL_ERROR` | 서버 내부 오류 |
| 503 | `EXTERNAL_API_ERROR` | 외부 API (HCX / 도서관정보나루) 응답 실패 |

---

## 2. 인증 및 계정 관리 (Auth) — F-00, F-07

### `POST /auth/social`

소셜 로그인 (Google / Kakao)

**Request Body**
```json
{
  "provider": "kakao",
  "access_token": "kakao_oauth_token_..."
}
```

| 필드 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `provider` | enum | Y | `google` / `kakao` |
| `access_token` | string | Y | 소셜 OAuth 액세스 토큰 |

**Response 200**
```json
{
  "success": true,
  "data": {
    "access_token": "eyJhbGciOiJIUzI1NiJ9...",
    "user_id": "usr_abc123",
    "is_new_user": true,
    "pending_matches": 0
  }
}
```

> `is_new_user: true` 이면 클라이언트에서 온보딩 플로우 시작  
> Refresh Token은 `HttpOnly Cookie`로 자동 설정

---

### `POST /auth/local`

자체 회원가입 (이메일 + 비밀번호 + 온보딩 데이터 저장 + 북켓몬 알 발급)

**Request Body**
```json
{
  "email": "user@example.com",
  "password": "securePassword123!",
  "nickname": "책벌레",
  "age": 25,
  "gender": "F",
  "genres": ["순문학/시", "추리/스릴러"],
  "location_consent": true,
  "library_codes": ["111004", "111005"]
}
```

| 필드 | 타입 | 필수 | 제약조건 |
|---|---|---|---|
| `email` | string | Y | 이메일 형식 |
| `password` | string | Y | 8자 이상, 영문+숫자+특수문자 |
| `nickname` | string | Y | 2~12자, 중복 불가, 특수문자 제한 |
| `age` | integer | Y | 10~99 |
| `gender` | enum | Y | `M` / `F` / `Other` |
| `genres` | array[string] | Y | 최소 1개, 최대 5개 |
| `location_consent` | boolean | Y | |
| `library_codes` | array[string] | N | 최대 3개 |

**Response 201**
```json
{
  "success": true,
  "data": {
    "user_id": "usr_abc123",
    "access_token": "eyJhbGciOiJIUzI1NiJ9...",
    "bookemon": {
      "stage": 0,
      "stage_name": "알(Egg)",
      "egg_color": "#FFD1DC"
    },
    "message": "이 알을 부화시키려면 책 한 권만 읽으면 돼요!"
  }
}
```

> Refresh Token은 `HttpOnly Cookie`로 자동 설정

---

### `GET /auth/check-nickname`

닉네임 중복 확인

**Query Parameters**

| 파라미터 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `nickname` | string | Y | 확인할 닉네임 (2~12자) |

**Response 200**
```json
{
  "success": true,
  "data": { "available": true }
}
```

**Error**

| 코드 | 조건 |
|---|---|
| `VALIDATION_ERROR` | 닉네임 2자 미만 또는 12자 초과 |
| `CONFLICT` | 닉네임 중복 |

---

### `POST /auth/refresh`

Refresh Token Rotation을 통한 Access Token 재발급

> 요청 시 Cookie의 Refresh Token을 자동으로 읽으며, 재발급 후 기존 Refresh Token은 폐기되고 새 Refresh Token이 HttpOnly Cookie로 재설정됩니다.

**Response 200**
```json
{
  "success": true,
  "data": {
    "access_token": "eyJhbGciOiJIUzI1NiJ9_new..."
  }
}
```

**Error**

| 코드 | 조건 |
|---|---|
| `UNAUTHORIZED` | Refresh Token 없음, 만료, 또는 블랙리스트 등록 |

---

### `POST /auth/logout`

로그아웃 (Redis 블랙리스트 처리)

> 현재 Access Token을 Redis 블랙리스트에 등록하고 Refresh Token Cookie를 삭제합니다.

**Response 200**
```json
{
  "success": true,
  "data": { "logged_out": true }
}
```

---

## 3. 채팅 & 추천 (Chat & Recommendation) — F-01

### `POST /chat`

자연어 질의를 받아 AI 추천 카드 3개 반환

**Request Body**

| 필드 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `query` | string | Y | 사용자 자연어 질의 |
| `chat_history` | array | N | 최근 대화 내역 (최대 8개) |
| `user_lib_codes` | array[string] | N | 대출 조회할 도서관 libCode (최대 3개) |

```json
{
  "query": "요즘 읽기 좋은 추리 소설 추천해줘",
  "chat_history": [
    { "role": "user", "content": "SF 소설 추천해줘" },
    { "role": "assistant", "content": "..." }
  ],
  "user_lib_codes": ["111004", "111005"]
}
```

> **상세 로직**: HCX로 `query` 정제 → Qdrant Top-50 검색 → **S_personal**(벡터+장르+이력) + **S_pop**(인기도) + **S_recency**(최신성) 동적 가중치 산출 → 메모리 부스팅(1.2x) → LLM 리랭커 Top-3 선정

**Response 200**
```json
{
  "success": true,
  "data": {
    "reply": "주인님이 좋아하는 추리 장르 중에서 골라봤어요!",
    "recommendations": [
      {
        "isbn": "9788936434267",
        "title": "채식주의자",
        "author": "한강",
        "cover": "https://cover.url/image.jpg",
        "reason": "주인님이 좋아하는 한국 현대문학 계열이에요.",
        "loan_status": [
          {
            "lib_code": "111004",
            "lib_name": "성남시립도서관",
            "has_book": true,
            "loan_available": true
          }
        ]
      }
    ],
    "total_count": 3,
    "response_time_ms": 4200
  }
}
```

**Error**

| 코드 | 조건 |
|---|---|
| `EXTERNAL_API_ERROR` | HCX API 응답 실패 → 캐시 인기 도서 Fallback |

> **응답시간 목표**: ≤ 5초  
> **Fallback**: 도서관 API 타임아웃(5초) 시 `loan_status: null`, `loan_unavailable: true` 플래그로 추천 결과만 반환

---

## 4. 운명의 책 뽑기 (Gacha) — F-02

### `GET /gacha/status`

오늘 뽑기 가능 여부 확인

**Response 200**
```json
{
  "success": true,
  "data": {
    "available": false,
    "reset_at": "2026-04-22T06:00:00+09:00"
  }
}
```

---

### `POST /gacha`

뽑기 실행

> **캐싱 전략**: Redis 키 `gacha_candidates:{user_id}` 우선 조회 (TTL 6h). 캐시 미스 시 Qdrant 검색 후 결과를 캐싱.  
> **제약**: 1일 1회 (KST 06:00 기준 초기화)  
> **Fallback**: 도서관 API 타임아웃(5초) 시 `loan_status: null`, `loan_unavailable: true` 플래그로 추천 결과만 반환

**Response 200**
```json
{
  "success": true,
  "data": {
    "isbn": "9788937460005",
    "title": "데미안",
    "author": "헤르만 헤세",
    "cover": "https://cover.url/demian.jpg",
    "quote": "새는 알에서 나오려고 투쟁한다.",
    "loan_status": {
      "lib_name": "성남시립도서관",
      "loan_available": true
    },
    "share_card_url": "https://bookemon.app/share/abc123.png",
    "xp_earned": 20,
    "show_loan_badge": true
  }
}
```

**Error**

| 코드 | 조건 |
|---|---|
| `RATE_LIMIT` | 오늘 이미 뽑기 사용 ("오늘은 이미 뽑기를 사용했어요!") |
| `NOT_FOUND` | 대출 가능 추천 도서 0건 |

---

## 5. 도서관 (Library) — F-03

### `GET /libraries/search`

도서관 검색 (GPS 또는 지역 기반)

**Query Parameters**

| 파라미터 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `lat` | float | N | 위도 (GPS 동의 시) |
| `lng` | float | N | 경도 (GPS 동의 시) |
| `region` | string | N | 시/도 코드 (수동 선택 시) |
| `district` | string | N | 시/군/구 코드 (수동 선택 시) |

**Response 200**
```json
{
  "success": true,
  "data": {
    "libraries": [
      {
        "lib_code": "111004",
        "lib_name": "성남시립도서관",
        "address": "경기도 성남시..."
      }
    ]
  }
}
```

---

### `POST /libraries/loan-status`

ISBN × 도서관 대출 현황 조회 (비동기 병렬)

**Request Body**
```json
{
  "isbn_list": ["9788936434267", "9788937460005"],
  "lib_codes": ["111004", "111005"]
}
```

**Response 200**
```json
{
  "success": true,
  "data": {
    "loan_results": [
      {
        "isbn": "9788936434267",
        "libraries": [
          { "lib_code": "111004", "lib_name": "성남시립도서관", "has_book": true, "loan_available": true },
          { "lib_code": "111005", "lib_name": "분당도서관", "has_book": true, "loan_available": false }
        ]
      }
    ]
  }
}
```

---

### `GET /profile/libraries`

내 등록 도서관 목록 조회

**Response 200**
```json
{
  "success": true,
  "data": {
    "libraries": [
      { "lib_code": "111004", "lib_name": "성남시립도서관", "registered_at": "2026-04-01T10:00:00" }
    ]
  }
}
```

---

### `POST /profile/libraries`

도서관 등록 (최대 3개)

**Request Body**
```json
{
  "lib_code": "111006",
  "lib_name": "판교도서관"
}
```

**Error**

| 코드 | 조건 |
|---|---|
| `VALIDATION_ERROR` | 이미 3개 등록된 상태에서 추가 시도 |
| `CONFLICT` | 이미 등록된 도서관 |

---

### `DELETE /profile/libraries/{lib_code}`

도서관 등록 해제

**Response 200**
```json
{ "success": true, "data": { "deleted": true } }
```

---

## 6. 프로필 & 메모리 (Profile & Memory) — F-04

### `GET /profile`

내 프로필 전체 조회

**Response 200**
```json
{
  "success": true,
  "data": {
    "user_id": "usr_abc123",
    "nickname": "책벌레",
    "age": 25,
    "gender": "F",
    "user_type": "existing",
    "current_xp": 350,
    "current_stage": 1,
    "total_conversations": 45,
    "total_books_registered": 5,
    "genre_preferences": { "순문학": 0.6, "추리": 0.3, "SF": 0.1 }
  }
}
```

---

### `PATCH /profile`

닉네임 등 프로필 일부 수정

**Request Body**
```json
{
  "nickname": "새닉네임"
}
```

---

### `GET /memories`

사용자 원칙(메모리) 목록 조회

**Response 200**
```json
{
  "success": true,
  "data": {
    "principles": [
      { "id": 1, "principle": "어려운 책 싫어", "created_at": "2026-04-01T10:00:00" }
    ]
  }
}
```

---

### `POST /memories`

원칙 추가

**Request Body**
```json
{
  "principle": "일본 소설 좋아함"
}
```

**Response 201**
```json
{
  "success": true,
  "data": { "id": 2, "principle": "일본 소설 좋아함" }
}
```

---

### `DELETE /memories/{id}`

원칙 삭제

**Response 200**
```json
{ "success": true, "data": { "deleted": true } }
```

---

## 7. 독서대 (Reading Shelf) — F-04

### `GET /reading-shelf`

독서대 전체 조회

**Response 200**
```json
{
  "success": true,
  "data": {
    "shelf": [
      {
        "id": 1,
        "isbn": "9788936434267",
        "title": "채식주의자",
        "author": "한강",
        "cover": "https://cover.url/image.jpg",
        "status": "reading",
        "registered_at": "2026-04-19T10:00:00",
        "completed_at": null,
        "review_unlocked_at": "2026-04-21T10:00:00",
        "review_available": true
      }
    ],
    "reading_count": 1
  }
}
```

---

### `POST /reading-shelf`

독서대에 책 등록

**Request Body**
```json
{
  "isbn": "9788936434267"
}
```

**Response 201**
```json
{
  "success": true,
  "data": {
    "id": 2,
    "isbn": "9788936434267",
    "status": "reading",
    "registered_at": "2026-04-21T14:00:00",
    "review_unlocked_at": "2026-04-24T14:00:00"
  }
}
```

**Error**

| 코드 | 조건 |
|---|---|
| `SHELF_FULL` | reading 상태 3권 초과 |
| `CONFLICT` | 이미 독서대에 등록된 책 |

> **동시성**: `SELECT FOR UPDATE`로 행 잠금 후 현재 독서대 수량 검증

---

### `PATCH /reading-shelf/{id}/complete`

완독 체크

**Response 200**
```json
{
  "success": true,
  "data": {
    "id": 1,
    "status": "completed",
    "completed_at": "2026-04-21T15:00:00",
    "xp_earned": 100,
    "evolution_triggered": false
  }
}
```

---

### `DELETE /reading-shelf/{id}`

독서대에서 책 제거

**Response 200**
```json
{
  "success": true,
  "data": {
    "deleted": true,
    "xp_deducted": 100,
    "current_xp": 250
  }
}
```

> **동시성**: `SELECT FOR UPDATE` + `current_xp = GREATEST(current_xp - 100, 0)` 으로 음수 방지

---

## 8. 리뷰 (Reviews) — F-04

### `GET /reviews`

내 리뷰 목록 조회 (커서 기반 페이지네이션)

**Query Parameters**

| 파라미터 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `cursor` | string | N | 다음 페이지 시작 커서 (이전 응답의 `next_cursor`) |
| `limit` | int | N | 한 번에 조회할 수 (기본 20, 최대 50) |

**Response 200**
```json
{
  "success": true,
  "data": {
    "reviews": [
      {
        "id": 1,
        "isbn": "9788936434267",
        "title": "채식주의자",
        "content": "너무 재밌었어요!",
        "rating": 5,
        "is_training_data": true,
        "created_at": "2026-04-21T16:00:00"
      }
    ],
    "next_cursor": "review_cursor_xyz",
    "has_more": false
  }
}
```

---

### `POST /reviews`

리뷰 작성 (독서대 등록 + 완독 + 72h 경과 필수)

**Request Body**
```json
{
  "isbn": "9788936434267",
  "content": "생각보다 훨씬 강렬한 소설이었어요.",
  "rating": 5
}
```

**Response 201**
```json
{
  "success": true,
  "data": {
    "id": 2,
    "is_training_data": true,
    "xp_earned": 50
  }
}
```

**Error**

| 코드 | 조건 |
|---|---|
| `FORBIDDEN` | 독서대 미등록 / 완독 미체크 |
| `REVIEW_LOCKED` | 독서대 등록 후 72시간 미경과 (응답에 `unlock_at` 포함) |
| `RATE_LIMIT` | 일일 리뷰 3회 한도 초과 |

> **동시성**: `SELECT FOR UPDATE`로 행 잠금 → 완독 상태·72h 경과 검증 → XP 적립 → 트랜잭션 커밋

---

### `DELETE /reviews/{id}`

리뷰 삭제

**Response 200**
```json
{ "success": true, "data": { "deleted": true } }
```

---

## 9. XP & 진화 (XP & Evolution) — F-06

### `GET /xp`

XP 및 진화 상태 조회

**Response 200**
```json
{
  "success": true,
  "data": {
    "current_xp": 350,
    "current_stage": 1,
    "stage_name": "유아기",
    "next_stage_xp": 500,
    "xp_to_next": 150,
    "today_actions": {
      "review": 1,
      "gacha": 1,
      "share": 0,
      "attendance": 1,
      "quote_share": 2
    }
  }
}
```

---

### `POST /xp/attendance`

일일 출석 체크 (XP 10)

**Response 200**
```json
{
  "success": true,
  "data": {
    "xp_earned": 10,
    "current_xp": 360,
    "evolution_triggered": false
  }
}
```

**Error**

| 코드 | 조건 |
|---|---|
| `RATE_LIMIT` | 오늘 이미 출석 체크 |

---

## 10. 소셜 교류 (Social) — F-08

### `POST /social/friends`

친구 관계 직접 생성 (양쪽 XP 40 적립)

**Request Body**
```json
{
  "target_user_id": "usr_xyz789"
}
```

**Response 201**
```json
{
  "success": true,
  "data": {
    "friend_id": "usr_xyz789",
    "xp_earned": 40,
    "current_xp": 390
  }
}
```

**Error**

| 코드 | 조건 |
|---|---|
| `CONFLICT` | 이미 친구 관계 존재 |
| `NOT_FOUND` | 대상 유저 없음 |

---

### `GET /social/matches`

현재 매칭 대기 목록 조회 (로그인 시 팝업용)

**Response 200**
```json
{
  "success": true,
  "data": {
    "matches": [
      {
        "request_id": "req_001",
        "matched_user": {
          "nickname": "책갈피",
          "bookemon_stage": 2,
          "top_genres": ["순문학/시", "에세이"]
        },
        "similarity": 0.87,
        "notified_count": 1
      }
    ]
  }
}
```

---

### `POST /social/requests/{request_id}/accept`

친구 요청 수락

**Response 200**
```json
{
  "success": true,
  "data": {
    "friend_id": "usr_xyz789",
    "xp_earned": 40
  }
}
```

---

### `POST /social/requests/{request_id}/reject`

친구 요청 거절

**Response 200**
```json
{
  "success": true,
  "data": {
    "cooldown_until": "2026-05-21T14:00:00"
  }
}
```

---

### `POST /social/requests/{request_id}/later`

나중에 (다음 로그인 시 재노출, 최대 3회)

**Response 200**
```json
{
  "success": true,
  "data": {
    "notified_count": 2,
    "max_count": 3
  }
}
```

---

### `GET /social/friends`

친구 목록 조회 (커서 기반 페이지네이션)

**Query Parameters**

| 파라미터 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `cursor` | string | N | 다음 페이지 시작 커서 |
| `limit` | int | N | 한 번에 조회할 수 (기본 20) |

**Response 200**
```json
{
  "success": true,
  "data": {
    "friends": [
      {
        "user_id": "usr_xyz789",
        "nickname": "책갈피",
        "bookemon_stage": 2,
        "favorite_books": ["9788936434267"],
        "recent_review_summary": "한강 작가의 문체가 정말 인상적이에요."
      }
    ],
    "next_cursor": "friend_cursor_abc",
    "has_more": false
  }
}
```

---

## 11. 공유 카드 설정 (Card Settings) — F-09

### `GET /settings/card`

카드 설정 조회

**Response 200**
```json
{
  "success": true,
  "data": {
    "show_loan_badge": true
  }
}
```

---

### `PUT /settings/card`

카드 설정 변경

**Request Body**
```json
{
  "show_loan_badge": false
}
```

**Response 200**
```json
{
  "success": true,
  "data": { "show_loan_badge": false }
}
```

---

### `POST /share/card`

공유 카드 생성 → XP 적립

**Request Body**
```json
{
  "card_type": "gacha"
}
```

| `card_type` | XP | 일일 한도 |
|---|---|---|
| `gacha` | 30 XP | 1회 |
| `quote` | 25 XP | 5회 |
| `review` | 0 XP | — |
| `evolution` | 0 XP | — |

**Response 201**
```json
{
  "success": true,
  "data": {
    "xp_earned": 30,
    "current_xp": 390
  }
}
```

**Error**

| 코드 | 조건 |
|---|---|
| `RATE_LIMIT` | 일일 공유 한도 초과 |

---

## 💡 구현 가이드 (개발자 필독)

### XP 동시성 제어 (CRITICAL)

모든 XP 증감 API (독서대 등록, 삭제, 리뷰 작성, 공유, 출석)는 반드시 **RDB 트랜잭션 내에서 `SELECT FOR UPDATE`** 를 사용해 행 잠금을 걸어야 합니다.

```sql
-- XP 차감 시 음수 방지
UPDATE users
SET current_xp = GREATEST(current_xp - 100, 0),
    updated_at = NOW()
WHERE user_id = :user_id;
```

### 진화 역행 방지

XP 변화 시 항상 `current_stage`와 `current_xp`를 함께 검증하여 진화 이벤트를 트리거합니다.  
**진화 단계는 절대 역행하지 않습니다.** DB 제약 조건(CHECK stage >= previous_stage) 또는 비즈니스 로직에서 방어 코드를 작성하세요.

```python
# 진화 단계 역행 방지 예시
if new_stage < current_stage:
    new_stage = current_stage  # 다운그레이드 차단
```

### 외부 API 타임아웃 & Fallback

`POST /chat` 및 `POST /gacha`는 도서관정보나루 API 호출 시 **5초 타임아웃**을 설정합니다.  
타임아웃 발생 시 도서 추천 데이터는 반환하되 대출 정보를 생략하고 `loan_unavailable: true` 플래그를 포함합니다.

```json
{
  "isbn": "9788937460005",
  "title": "데미안",
  "loan_status": null,
  "loan_unavailable": true
}
```

### 페이지네이션 표준

모든 리스트 조회 API(`GET /reviews`, `GET /social/friends`, `GET /memories` 등)는 **커서 기반 페이지네이션**을 준수합니다.

| 파라미터 | 설명 |
|---|---|
| `cursor` | 이전 응답의 `next_cursor` 값. 없으면 첫 페이지 |
| `limit` | 페이지당 항목 수 (기본 20, 최대 50) |
| `next_cursor` | 다음 페이지 커서. `null`이면 마지막 페이지 |
| `has_more` | 다음 페이지 존재 여부 |

---

## 12. 엔드포인트 목록 요약

| 메서드 | 경로 | 설명 | 기능 |
|---|---|---|---|
| POST | `/auth/social` | 소셜 로그인 | F-07 |
| POST | `/auth/local` | 자체 회원가입 | F-07 |
| GET | `/auth/check-nickname` | 닉네임 중복 확인 | F-07 |
| POST | `/auth/refresh` | Refresh Token 갱신 | F-00 |
| POST | `/auth/logout` | 로그아웃 (Redis 블랙리스트) | F-00 |
| POST | `/chat` | AI 추천 채팅 | F-01 |
| GET | `/memories` | 사용자 원칙(메모리) 목록 | F-04 |
| POST | `/memories` | 원칙 추가 | F-04 |
| DELETE | `/memories/{id}` | 원칙 삭제 | F-04 |
| GET | `/gacha/status` | 뽑기 가능 여부 | F-02 |
| POST | `/gacha` | 뽑기 실행 | F-02 |
| GET | `/libraries/search` | 도서관 검색 | F-03 |
| POST | `/libraries/loan-status` | 대출 현황 조회 | F-03 |
| GET | `/profile/libraries` | 등록 도서관 목록 | F-03 |
| POST | `/profile/libraries` | 도서관 등록 | F-03 |
| DELETE | `/profile/libraries/{lib_code}` | 도서관 해제 | F-03 |
| GET | `/profile` | 프로필 조회 | F-04 |
| PATCH | `/profile` | 프로필 수정 | F-04 |
| GET | `/reading-shelf` | 독서대 조회 | F-04 |
| POST | `/reading-shelf` | 독서대 등록 | F-04 |
| PATCH | `/reading-shelf/{id}/complete` | 완독 체크 | F-04 |
| DELETE | `/reading-shelf/{id}` | 독서대 제거 (XP 차감) | F-04 |
| GET | `/reviews` | 리뷰 목록 (cursor) | F-04 |
| POST | `/reviews` | 리뷰 작성 | F-04 |
| DELETE | `/reviews/{id}` | 리뷰 삭제 | F-04 |
| GET | `/xp` | XP & 진화 상태 | F-06 |
| POST | `/xp/attendance` | 출석 체크 | F-06 |
| POST | `/social/friends` | 친구 관계 생성 | F-08 |
| GET | `/social/matches` | 매칭 목록 | F-08 |
| POST | `/social/requests/{id}/accept` | 친구 요청 수락 | F-08 |
| POST | `/social/requests/{id}/reject` | 친구 요청 거절 | F-08 |
| POST | `/social/requests/{id}/later` | 나중에 | F-08 |
| GET | `/social/friends` | 친구 목록 (cursor) | F-08 |
| GET | `/settings/card` | 카드 설정 조회 | F-09 |
| PUT | `/settings/card` | 카드 설정 변경 | F-09 |
| POST | `/share/card` | 공유 카드 생성 → XP 적립 | F-09 |

---

## 13. 변경 이력

|버전|일자|변경 내용|
|---|---|---|
|v2.0|2026-04-21|Base URL v2 갱신, Auth 재설계(Bearer+HttpOnly Cookie, Refresh Token Rotation, Redis 블랙리스트), Chat 요청 파라미터 및 스코어링 로직 추가, Gacha Redis 6h 캐시 명세, 독서대/리뷰 에러 코드 SHELF_FULL·REVIEW_LOCKED로 정규화, DELETE /reading-shelf XP 차감 응답 추가, POST /social/friends 신규, GET /reviews·/social/friends 커서 페이지네이션, POST /share/card 명칭 변경, 💡구현 가이드 섹션 추가, 총 36개 엔드포인트|
|v1.0|2026-04-21|초안 작성 (기능 명세서 v1.1 기반 전체 엔드포인트 설계, 총 32개)|
