# Frontend API 문서

## 공통 보안 응답

### `429 Too Many Requests`

Cloudflare Free 플랜의 rate limiting 한계를 보완하기 위해 백엔드에서 주요 API별 요청 제한을 수행합니다.
아래 API들은 제한 초과 시 공통 형식으로 `429`를 반환할 수 있습니다.

- `POST /api/auth/login`
- `POST /api/auth/signup`
- `GET /api/auth/signup/email-availability`
- `POST /api/auth/password-reset/send-code`
- `POST /api/auth/password-reset/confirm`
- `POST /api/auth/dormant/send-code`
- `POST /api/auth/dormant/confirm`
- `POST /api/auth/social-signup/complete`
- `GET /api/onboarding/books/search`
- `POST /api/chats`
- `POST /api/chats/messages`
- `POST /api/chats/{sessionId}/messages`
- `POST /api/users/me/book-availability`
- `POST /api/admin/characters/images`

#### Response `429 Too Many Requests`

```json
{
  "message": "요청이 너무 많습니다. 잠시 후 다시 시도해 주세요."
}
```

#### Response Headers

| 이름 | 설명 |
| --- | --- |
| `Retry-After` | 재시도 전 대기 권장 시간(초)입니다. |
| `X-RateLimit-Rule` | 적용된 백엔드 rate limit rule 이름입니다. |
| `X-RateLimit-Limit` | 현재 창에서 허용되는 최대 요청 수입니다. |
| `X-RateLimit-Window-Seconds` | 제한 집계 시간 창(초)입니다. |

## 회원가입 이메일 검증

### `GET /api/auth/signup/email-availability`

회원가입 화면의 이메일 중복 확인 API입니다. 실제 이메일 소유 인증은 하지 않으며, 프론트와 백엔드에서 동일한 기본 형식 검증만 수행합니다.

#### 이메일 검증 정책

- 전체 길이: 최대 254자
- local part 길이: 최대 64자
- `@`는 정확히 1개
- 도메인은 `.`을 포함한 일반 도메인 형식이어야 함
- local part의 앞/뒤 `.` 및 연속 `..` 차단
- 도메인의 연속 `..` 차단
- 가입 허용 도메인: `gmail.com`, `nate.com`, `kakao.com`, `naver.com`, `daum.net`
- 위 허용 도메인 외 이메일은 프론트에서 먼저 차단하고, 백엔드에서도 동일하게 거부합니다.

> 이메일 인증 코드를 발송하지 않으므로 실제 메일함 소유 여부는 검증하지 않습니다. 비밀번호 찾기 기능은 가입자가 입력한 이메일을 기준으로 동작합니다.

#### Query Parameters

| 이름 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `email` | string | Y | 중복 확인할 이메일입니다. |

#### Response `200 OK`

```json
{
  "available": false,
  "message": "가입 가능한 이메일 도메인은 gmail.com, nate.com, kakao.com, naver.com, daum.net입니다."
}
```


#### 탈퇴 계정 재가입 정책

- 회원가입/이메일 중복 확인은 `status <> 'DELETED'` 계정만 기존 계정으로 판단합니다.
- 탈퇴 계정은 없는 계정처럼 처리하므로 같은 이메일로 새 `users` row가 생성될 수 있습니다.
- 탈퇴 시 기존 `user_credentials`, `user_social_accounts`, `user_profiles`, `user_characters`, 관심/도서관/독서대/채팅/추천 로그는 정리됩니다.

### `POST /api/auth/signup`

일반 회원가입 API입니다. `email` 필드는 위 이메일 검증 정책과 동일하게 검사합니다.

#### Request Body 중 이메일 필드

| 이름 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `email` | string | Y | 로그인 및 추후 비밀번호 찾기에 사용할 이메일입니다. 최대 254자입니다. |

### `POST /api/auth/social-signup/complete`

소셜 로그인 후 자체 계정 생성을 완료하는 API입니다. `email` 필드는 위 이메일 검증 정책과 동일하게 검사합니다.

## 소셜 로그인 연동/해제

### `POST /api/auth/social-link/{provider}/start`

로그인한 사용자가 마이페이지에서 소셜 로그인 연동을 시작할 때 호출합니다.

#### Path Parameters

| 이름 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `provider` | string | Y | `google`, `kakao`처럼 연동할 제공자입니다. 서버에서는 대문자로 정규화합니다. |

#### Response `200 OK`

```json
{
  "authorizationUrl": "/oauth2/authorization/google"
}
```

### `DELETE /api/auth/social-link/{provider}`

로그인한 사용자의 연동된 소셜 로그인 제공자를 해제합니다. 해제 성공 시 최신 사용자 세션 정보를 반환합니다.

#### 정책

- 연동된 provider만 해제할 수 있습니다.
- 자체 회원가입 계정은 소셜 연동을 모두 해제할 수 있습니다.
- 소셜 로그인만 존재하는 계정은 마지막 소셜 로그인 수단 해제를 막습니다.
- 기본 이메일은 항상 `users.primary_email` 기준으로 응답합니다. 소셜 계정 이메일은 `user_social_accounts.provider_email`에만 저장되며 `users.primary_email`을 덮어쓰지 않습니다.

#### Request

```http
DELETE /api/auth/social-link/google
X-XSRF-TOKEN: {token}
```

#### Response `200 OK`

```json
{
  "id": "7e24c44e-7f95-4f28-8213-88f5d59358c6",
  "email": "user@example.com",
  "nickname": "태오",
  "role": "USER",
  "onboardingCompleted": false,
  "linkedProviders": ["KAKAO"]
}
```

#### Error 예시

```json
{
  "message": "마지막 로그인 수단은 해제할 수 없습니다. 다른 로그인 수단을 먼저 연동해 주세요."
}
```

## 도서관 검색

### 공통 페이지 응답

일반 사용자용 도서관 검색 API는 `limit` 요청값을 받지 않고, 서버에서 10개 단위 페이지네이션으로 고정합니다. 프론트는 `page`만 전달합니다. `page`는 0부터 시작합니다.

```json
{
  "content": [],
  "page": 0,
  "size": 10,
  "totalElements": 0,
  "totalPages": 0,
  "hasNext": false,
  "hasPrevious": false
}
```

### `GET /api/libraries/search`

나만의 도서관 등록과 온보딩 대표 도서관 선택에서 사용하는 일반 사용자용 도서관 검색 API입니다.

#### Query Parameters

| 이름 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `keyword` | string | Y | 검색어. 최소 2글자 이상 입력해야 합니다. |
| `page` | number | N | 0부터 시작하는 페이지 번호입니다. 기본값은 0입니다. |

#### 검색 기준

- 도서관명(`libName`)
- 주소(`address`)

`libCode`는 내부 식별자이므로 일반 사용자 입력 검색 조건에서는 제외합니다. 단, 응답에는 계속 포함되며 나만의 도서관 저장과 대출 가능 여부 조회에 사용합니다.

#### Response `200 OK`

```json
{
  "content": [
    {
      "libCode": "111000",
      "libName": "예시도서관",
      "address": "서울특별시 예시구 예시로 1",
      "latitude": 37.123456,
      "longitude": 127.123456
    }
  ],
  "page": 0,
  "size": 10,
  "totalElements": 37,
  "totalPages": 4,
  "hasNext": true,
  "hasPrevious": false
}
```

### `GET /api/libraries/nearby`

현재 위치 기준 주변 도서관 조회 API입니다.

#### Query Parameters

| 이름 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `latitude` | number | Y | 현재 위치 위도 |
| `longitude` | number | Y | 현재 위치 경도 |
| `radiusMeters` | number | N | 검색 반경(m). 서버에서 100~20000 범위로 보정합니다. 기본값은 5000입니다. |
| `page` | number | N | 0부터 시작하는 페이지 번호입니다. 기본값은 0입니다. |

#### Response `200 OK`

```json
{
  "content": [
    {
      "libCode": "111000",
      "libName": "예시도서관",
      "address": "서울특별시 예시구 예시로 1",
      "latitude": 37.123456,
      "longitude": 127.123456,
      "distanceMeters": 321.12
    }
  ],
  "page": 0,
  "size": 10,
  "totalElements": 22,
  "totalPages": 3,
  "hasNext": true,
  "hasPrevious": false
}
```

## 온보딩 도서 검색/저장

### `GET /api/onboarding/books/search`

온보딩의 읽은 책 선택 단계에서 사용하는 도서 검색 API입니다. 프론트는 알라딘 TTBKey를 직접 보관하지 않고, backend가 알라딘 `ItemSearch.aspx`를 호출한 뒤 화면에 필요한 필드만 반환합니다.

#### Query Parameters

| 이름 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `keyword` | string | Y | 도서 검색어입니다. 최소 2글자 이상 입력해야 합니다. |
| `limit` | number | N | 조회 개수입니다. 서버에서 1~50 범위로 보정하며 기본값은 10입니다. |
| `start` | number | N | 알라딘 검색 시작 페이지입니다. 기본값은 1입니다. |

#### Response `200 OK`

```json
{
  "totalResults": 19,
  "startIndex": 1,
  "itemsPerPage": 10,
  "query": "초파리",
  "items": [
    {
      "aladinItemId": "361447374",
      "isbn": "K642038675",
      "isbn13": "9791198808851",
      "title": "초파리",
      "author": "이주형 지음",
      "publisher": "핌",
      "pubDate": "Wed, 18 Dec 2024 15:00:00 GMT",
      "description": "초파리 - 이주형 지음 ...",
      "coverUrl": "https://image.aladin.co.kr/product/36144/73/coversum/k642038675_1.jpg",
      "categoryId": "50993",
      "categoryName": "국내도서>소설/시/희곡>한국소설>2000년대 이후 한국소설",
      "customerReviewRank": 0,
      "priceSales": 14400,
      "priceStandard": 16000
    }
  ]
}
```

### `POST /api/onboarding/complete`의 `selectedBooks` 저장 방식

온보딩 프론트에서 알라딘 검색 결과 중 사용자가 선택한 책을 `selectedBooks`에 담아 전송하면, backend가 온보딩 완료 트랜잭션 안에서 다음 순서로 저장합니다.

1. `bookId`가 있으면 기존 `book.books.id`를 사용합니다.
2. `bookId`가 없고 `book.isbn13`이 있으면 `book.books`에 `isbn13` 기준으로 upsert합니다.
3. `book.user_book_shelves`에 기본적으로 읽은 책(`READ`)으로 저장합니다.
4. 새로 저장된 항목이면 개인화 학습용 `book.user_book_actions`에 `READ_FINISH`, `source=ONBOARDING` 로그를 남깁니다.

#### Request Body 중 `selectedBooks` 예시

```json
{
  "residentNumberFront": "930319",
  "residentGenderDigit": "1",
  "readerTypeOptionId": 1,
  "bookCategoryOptionIds": [10, 11, 12],
  "readingPurpose": "업무 역량을 키우고 새로운 취미를 찾고 싶어요.",
  "preferredRadiusKm": 5,
  "selectedBooks": [
    {
      "shelfType": "READ",
      "note": "온보딩에서 선택한 읽은 책",
      "book": {
        "isbn13": "9791198808851",
        "title": "초파리",
        "author": "이주형 지음",
        "publisher": "핌",
        "coverUrl": "https://image.aladin.co.kr/product/36144/73/coversum/k642038675_1.jpg",
        "categoryCode": "50993",
        "metadata": {
          "source": "ALADIN",
          "aladinItemId": "361447374",
          "isbn": "K642038675",
          "categoryName": "국내도서>소설/시/희곡>한국소설>2000년대 이후 한국소설",
          "customerReviewRank": 0
        }
      }
    }
  ]
}
```

#### `selectedBooks` 필드

| 이름 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `selectedBooks[].bookId` | number \| null | N | 이미 내부 DB에 존재하는 도서 ID입니다. 있으면 `book` 없이도 저장 가능합니다. |
| `selectedBooks[].book` | object \| null | N | 알라딘 검색 결과 기반 도서 스냅샷입니다. `bookId`가 없을 때 필요합니다. |
| `selectedBooks[].book.isbn13` | string | 조건부 Y | 13자리 ISBN입니다. 신규 도서 upsert 기준입니다. |
| `selectedBooks[].book.title` | string | N | 도서명입니다. 없으면 서버에서 `제목 정보 없음`으로 저장합니다. |
| `selectedBooks[].book.author` | string | N | 저자입니다. |
| `selectedBooks[].book.publisher` | string | N | 출판사입니다. |
| `selectedBooks[].book.coverUrl` | string | N | 표지 이미지 URL입니다. |
| `selectedBooks[].book.categoryCode` | string | N | 알라딘 `categoryId`를 넣으면 됩니다. 현재 저장은 `raw_json.metadata` 중심이며 기존 테이블 구조를 우선합니다. |
| `selectedBooks[].book.metadata` | object | N | 알라딘 `itemId`, `isbn`, `categoryName`, `customerReviewRank` 등 부가 정보입니다. `book.books.raw_json`에 저장됩니다. |
| `selectedBooks[].shelfType` | string | N | 기본값은 `READ`입니다. 읽은 책으로 저장하려면 생략하거나 `READ`를 보내면 됩니다. |
| `selectedBooks[].note` | string | N | 사용자 메모입니다. 최대 500자입니다. |

#### `readingPurpose` 필드

| 이름 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `readingPurpose` | string | N | 독서 목적 자유 텍스트입니다. 카드 선택값이 아니라 사용자가 직접 입력한 문장을 전송합니다. 최대 300자입니다. |

프론트 온보딩 담당자는 검색 응답의 `items[]`를 위 `book` 구조로 매핑해 `POST /api/onboarding/complete`에 포함하면 됩니다.



### `POST /api/onboarding/skip`

온보딩 시작 화면에서 사용자가 `괜찮아요`를 선택했을 때 호출합니다. 별도 요청 body는 없습니다. 서버는 현재 로그인 사용자의 기본 프로필을 유지하되 `onboardingCompleted=false` 상태를 유지하고, 기존 기본 캐릭터 `DEFAULT_BOOKEMON`을 유지합니다.

#### Request

```http
POST /api/onboarding/skip
X-XSRF-TOKEN: {token}
```

#### Response `200 OK`

```json
{
  "id": "7e24c44e-7f95-4f28-8213-88f5d59358c6",
  "email": "user@example.com",
  "nickname": "태오",
  "role": "USER",
  "onboardingCompleted": false,
  "linkedProviders": []
}
```

동작 정책:

- 온보딩을 건너뛰면 독자 유형, 희망 장르, 읽은 책, 도서관은 저장하지 않습니다.
- 기본 캐릭터는 `DEFAULT_BOOKEMON`을 유지합니다.
- 온보딩을 완료해 독자 유형 캐릭터가 발급되면 사용자 캐릭터 닉네임은 캐릭터 마스터의 기본 이름으로 설정됩니다. 예: `용기의 알` 캐릭터가 발급되면 마이페이지 이름도 `용기의 알`로 표시됩니다.
- 응답의 `onboardingCompleted`는 `false`로 내려가며, 프론트는 응답을 저장한 뒤 메인 화면으로 이동할 수 있습니다. 이후 다시 로그인하면 온보딩 안내 또는 온보딩 페이지로 이동시켜 다시 건너뛰거나 완료할 수 있게 합니다.


## 사용자 프로필 저장

### `PUT /api/users/me/profile`

마이페이지 기본 정보/희망 장르/독서 목적/선호 반경 수정 API입니다.

#### Request Body 중 기본 정보 필드

| 이름 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `residentNumberFront` | string \| null | N | 주민등록번호 앞자리 YYMMDD 6자리입니다. |
| `residentGenderDigit` | string \| null | N | 주민등록번호 뒷자리 첫 숫자입니다. 허용값은 `1`, `2`, `3`, `4`입니다. |

`residentGenderDigit`은 생년월일의 세기 판별에만 사용합니다. 프론트에서는 주민등록번호 전체를 수집하거나 저장하지 않습니다.

#### Request Body 중 선호 반경 필드

| 이름 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `preferredRadiusKm` | number | N | 선호 반경 km입니다. 선택지는 `1`, `2`, `3`, `4`, `5`, `6`, `7`, `8`, `9`, `10`, `50`만 허용합니다. 프론트에서는 `50`을 `10~50km` 광역 선택지로 표시합니다. 미전달 시 기본값은 `5.00`입니다. |

온보딩 미완료 사용자는 마이페이지에서 독서 프로필 카드/섹션을 표시하지 않습니다. 단, 기본 회원정보와 소셜 연동 영역은 그대로 표시합니다.

### `POST /api/onboarding/complete`

온보딩 완료 API도 동일하게 `residentGenderDigit` 허용값은 `1`, `2`, `3`, `4`입니다.

## 독서대 리뷰 저장

### `POST /api/users/me/book-shelves/{shelfId}/review`

읽는 중(`READING`) 도서가 리뷰 가능 시점이 되었을 때 리뷰와 평점을 저장하고, 해당 도서를 읽은 책(`READ`)으로 전환합니다. 리뷰 가능 시점은 고정 3일이 아니라 관리자 화면의 `REVIEW_WAIT_MINUTES` 설정값 기준입니다.

#### Request Body

| 이름 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `reviewContent` | string | Y | 리뷰 내용입니다. 최대 2000자입니다. |
| `rating` | number | Y | 별점입니다. 허용 범위는 `0.5`~`5.0`이며 `0.5` 단위만 허용합니다. |

#### Request 예시

```json
{
  "reviewContent": "추천받아 읽었는데 생각보다 몰입감이 좋았습니다.",
  "rating": 4.5
}
```

#### Response `200 OK`

```json
{
  "shelf": {
    "id": 10,
    "bookId": 100,
    "isbn13": "9790000000000",
    "title": "예시 도서",
    "author": "예시 저자",
    "publisher": "예시 출판사",
    "coverUrl": "https://example.com/cover.jpg",
    "shelfType": "READ",
    "note": null,
    "reviewContent": "추천받아 읽었는데 생각보다 몰입감이 좋았습니다.",
    "reviewRating": 4.5,
    "reviewAvailableAt": "2026-04-27T09:00:00+09:00",
    "reviewAvailable": false,
    "reviewWaitMinutes": 4320,
    "reviewWaitLabel": "3일",
    "completedAt": "2026-04-30T10:00:00+09:00",
    "createdAt": "2026-04-27T09:00:00+09:00",
    "updatedAt": "2026-04-30T10:00:00+09:00"
  },
  "character": {
    "userId": "7e24c44e-7f95-4f28-8213-88f5d59358c6",
    "characterKey": "DEFAULT_BOOKEMON",
    "stage": "BABY",
    "characterNickname": "북케몬",
    "reviewGrowthCount": 1,
    "currentImageUrl": "/uploads/characters/default-level2.png",
    "characterLevel": 2,
    "experience": 0,
    "experienceToNextLevel": 100,
    "experiencePercent": 0,
    "maxLevel": 4
  },
  "levelUpEvent": {
    "previousLevel": 1,
    "newLevel": 2,
    "characterNickname": "북케몬",
    "characterImageUrl": "/uploads/characters/default-level2.png",
    "experience": 0,
    "experienceToNextLevel": 100,
    "maxLevel": 4,
    "message": "북케몬이(가) Lv.2로 성장했어요!"
  },
  "reviewRewardGranted": true,
  "reviewRewardMessage": "리뷰 보상이 지급되었습니다."
}
```

`levelUpEvent`는 이번 리뷰 완료로 레벨이 상승했을 때만 객체로 내려갑니다. 경험치만 증가하고 레벨업하지 않은 경우에는 `null`입니다. `reviewRewardGranted`는 사용자+도서 기준 최초 리뷰 보상 지급 여부입니다. 같은 책을 삭제 후 다시 등록해 리뷰하면 리뷰 저장은 가능하지만 `reviewRewardGranted=false`가 내려가고 캐릭터 경험치/레벨은 변경되지 않습니다.

#### 프론트 표시 기준

- 리뷰 작성 UI는 별 5개를 표시합니다.
- 각 별은 좌/우 반쪽 클릭 영역으로 나누어 `0.5`점 단위 선택을 지원합니다.
- 아무 별도 선택하지 않은 상태는 `0점` 표시용 상태이며, 저장 요청 전에는 `0.5`점 이상 선택해야 합니다.
- 리뷰 가능 안내 문구는 독서대 조회 응답의 `reviewWaitLabel`, `reviewAvailableAt`, `reviewAvailable` 값을 기준으로 표시합니다.
- 리뷰 완료 후에는 응답의 `character` 값으로 마이페이지 캐릭터 카드의 레벨/이미지를 즉시 갱신합니다.
- 응답의 `reviewRewardGranted`가 `false`이면 이미 보상을 받은 같은 책이므로 캐릭터 경험치/레벨은 변경되지 않습니다.
- 응답의 `levelUpEvent`가 `null`이 아니면 온보딩 보상 화면과 유사한 레벨업 축하 모달을 표시합니다.
- 관리자가 대기시간을 변경하면 신규 조회되는 독서대 응답부터 변경된 기준으로 `reviewAvailableAt`과 `reviewAvailable`이 계산됩니다.

## 내 캐릭터 조회

### `GET /api/users/me/character`

현재 로그인 사용자의 북케몬 캐릭터와 리뷰 기반 성장 상태를 조회합니다.

#### Response `200 OK`

```json
{
  "userId": "7e24c44e-7f95-4f28-8213-88f5d59358c6",
  "characterKey": "DEFAULT_BOOKEMON",
  "stage": "BABY",
  "characterNickname": "북케몬",
  "reviewGrowthCount": 2,
  "currentImageUrl": "/uploads/characters/default-level2.png",
  "characterLevel": 2,
  "experience": 20,
  "experienceToNextLevel": 100,
  "experiencePercent": 20,
  "maxLevel": 4
}
```

#### 캐릭터 성장 정책

| 누적 리뷰 완료 수 | 표시 레벨 | stage | 경험치 계산 | 이미지 |
| --- | --- | --- | --- | --- |
| `0` | Lv.1 | `EGG` | `0/100` | `level1_image_url` |
| `1`~`5` | Lv.2 | `BABY` | 리뷰당 `+20`, `0~80/100` | `level2_image_url` |
| `6`~`15` | Lv.3 | `GROWTH` | 리뷰당 `+10`, `0~90/100` | `level3_image_url` |
| `16` 이상 | Lv.4 | `FINAL` | 최대 레벨 `100/100` | `level4_image_url` |

초기 지급 캐릭터는 Lv.1입니다. 첫 리뷰 완료 시 Lv.1에서 Lv.2로 전환되고, `levelUpEvent.previousLevel=1`, `levelUpEvent.newLevel=2`가 내려갑니다.


## DB 보정 SQL

이번 변경의 DBeaver 실행용 SQL은 `docs/sql/31-service-review-policy.sql`, `docs/sql/32-user-review-reward-logs.sql`, `docs/sql/33-sync-user-character-growth-images.sql`, `docs/sql/34-profile-radius-50km.sql`에 추가되어 있습니다.

주요 내용:

- `book.user_profiles.preferred_radius_km` 기존 값을 `1.00`~`50.00`으로 보정하고 제약조건을 동일 범위로 재생성합니다.
- 온보딩 건너뛰기로 추정되는 `DEFAULT_BOOKEMON` + 독서 프로필 핵심값 미입력 사용자의 `onboarding_completed`를 `false`로 보정합니다.
- `status='DELETED'` 일반 회원의 인증/소셜/프로필/개인화/채팅/추천 로그를 삭제하고 `users.primary_email`을 `NULL`로 정리해 재가입을 허용합니다.


---

## 관리자 리뷰 정책 API

### 1. 리뷰 작성 가능 시기 조회

```http
GET /api/admin/review-policy
```

관리자 전용 API입니다. 읽는 중 도서 등록 후 리뷰를 작성할 수 있게 되는 대기시간을 분 단위로 조회합니다.

#### Response `200 OK`

```json
{
  "reviewWaitMinutes": 4320,
  "reviewWaitLabel": "3일",
  "updatedAt": "2026-04-29T14:10:00+09:00"
}
```

### 2. 리뷰 작성 가능 시기 수정

```http
PUT /api/admin/review-policy
X-XSRF-TOKEN: {token}
```

#### Request Body

| 이름 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `reviewWaitMinutes` | number | Y | 리뷰 작성 대기시간입니다. `0`~`43200`분까지 허용합니다. `0`이면 즉시 리뷰 작성이 가능합니다. |

#### Request 예시

```json
{
  "reviewWaitMinutes": 10
}
```

#### Response `200 OK`

```json
{
  "reviewWaitMinutes": 10,
  "reviewWaitLabel": "10분",
  "updatedAt": "2026-04-29T14:10:00+09:00"
}
```

#### 필요한 DB SQL

관리자 리뷰 정책 설정을 위해 아래 SQL을 먼저 실행해야 합니다.

```text
apps/backend/docs/sql/31-service-review-policy.sql
```

`book.service_settings.setting_key='REVIEW_WAIT_MINUTES'` 값이 사용자 독서대 응답의 `reviewAvailableAt`, `reviewAvailable`, `reviewWaitMinutes`, `reviewWaitLabel` 계산 기준으로 사용됩니다.

---

## 관리자 모니터링 API

### 1. 서비스 통합 모니터링 조회

```http
GET /api/admin/monitoring?rangeType=DAILY
```

관리자 전용 API입니다. 사용자별 상세가 아니라 서비스 전체 통합 지표를 일자별 시계열로 반환합니다.

#### Query Parameters

| 이름 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `rangeType` | string | N | `DAILY`, `WEEKLY`, `MONTHLY`, `CUSTOM` 중 하나입니다. 기본값은 `DAILY`입니다. |
| `startDate` | string | `CUSTOM`일 때 필수 | `YYYY-MM-DD` 형식의 시작일입니다. |
| `endDate` | string | `CUSTOM`일 때 필수 | `YYYY-MM-DD` 형식의 종료일입니다. |

#### 기간 기준

| rangeType | 조회 범위 |
| --- | --- |
| `DAILY` | 오늘 1일 |
| `WEEKLY` | 오늘 포함 최근 7일 |
| `MONTHLY` | 오늘 포함 최근 30일 |
| `CUSTOM` | `startDate` ~ `endDate` |

`CUSTOM` 기간은 최대 366일까지 조회할 수 있습니다.

#### Response

```json
{
  "rangeType": "WEEKLY",
  "startDate": "2026-04-22",
  "endDate": "2026-04-28",
  "metrics": [
    {
      "key": "SIGNUPS",
      "label": "회원가입 수",
      "description": "해당 일자에 가입한 일반 회원 수입니다.",
      "total": 12,
      "series": [
        {
          "date": "2026-04-22",
          "count": 1
        },
        {
          "date": "2026-04-23",
          "count": 3
        }
      ]
    }
  ],
  "generatedAt": "2026-04-28T15:20:00+09:00"
}
```

#### Metric Keys

| key | 설명 |
| --- | --- |
| `SIGNUPS` | 일반 회원 가입 수입니다. `book.users.created_at` 기준입니다. |
| `ACTIVE_USERS` | 로그인 이벤트 기준 일자별 순 접속 회원 수입니다. `book.user_login_events` 기준입니다. |
| `CHAT_MESSAGES` | 사용자가 발신한 채팅 메시지 수입니다. `book.chat_messages.role='USER'` 기준입니다. |
| `CHAT_SESSIONS` | 생성된 채팅방 수입니다. `book.chat_sessions.created_at` 기준입니다. |
| `LIKES` | 현재 유지 중인 좋아요 수입니다. `user_book_shelves.shelf_type='INTERESTED'` 기준이며 취소되어 삭제된 row는 제외됩니다. |
| `DISLIKES` | 현재 유지 중인 싫어요 수입니다. `user_book_shelves.shelf_type='NOT_INTERESTED'` 기준이며 취소되어 삭제된 row는 제외됩니다. |
| `READING_BUTTONS` | 현재 유지 중인 책읽기 버튼 수입니다. `user_book_shelves.shelf_type='READING'` 기준이며 취소되거나 읽은 책으로 전환된 row는 제외됩니다. |

#### 필요한 DB SQL

관리자 모니터링의 접속회원 수 집계를 위해 아래 SQL을 먼저 실행해야 합니다.

```text
apps/backend/docs/sql/30-admin-monitoring.sql
```

`user_login_events` 테이블은 SQL 적용 이후의 로그인부터 기록됩니다. SQL 적용 전 과거 로그인은 기존 `users.last_login_at`만으로 일자별 순 접속회원 수를 정확히 복원할 수 없으므로 자동 보정하지 않습니다.


## 리뷰 보상 중복 방지 정책

리뷰 완료에 따른 캐릭터 성장 보상은 `book.user_review_reward_logs` 테이블에 사용자+도서 단위로 기록합니다.

- 같은 사용자가 같은 책으로 처음 리뷰를 완료하면 `reviewRewardGranted=true`이며 캐릭터 경험치/레벨이 갱신됩니다.
- 읽은 책 또는 독서대 항목을 삭제해도 보상 이력은 유지됩니다.
- 같은 책을 다시 등록하고 리뷰를 다시 작성하면 리뷰 저장은 가능하지만 `reviewRewardGranted=false`이며 캐릭터 경험치/레벨은 변경되지 않습니다.
- 독서대 항목이 삭제되면 `user_review_reward_logs.shelf_id`는 `NULL`로 남고, 사용자+도서 보상 이력은 계속 보존됩니다.


## 리뷰 성장 이미지 보정

리뷰 완료 후 `review_growth_count` 기준 레벨이 1 이상인데 `user_characters.current_image_url`이 이전 알 이미지로 남아 있는 경우, 캐릭터 조회 API는 `character_definitions`의 현재 레벨 이미지 기준으로 표시 이미지를 보정합니다. 기존 데이터 일괄 보정은 `apps/backend/docs/sql/33-sync-user-character-growth-images.sql`을 실행합니다.

리뷰 본문과 평점은 `book.user_book_shelves.review_content`, `book.user_book_shelves.review_rating`에 저장됩니다. 리뷰 완료 액션 이력은 `book.user_book_actions`에 `action_type = 'READ_FINISH'`로 저장되고, 캐릭터 성장 보상 중복 방지 이력은 `book.user_review_reward_logs`에 저장됩니다.

---

## 추가 변경 사항: 캐릭터 레벨 기준 변경

- 초기 지급 캐릭터는 0레벨이 아니라 **Lv.1**입니다.
- `reviewGrowthCount = 0`인 캐릭터도 `characterLevel = 1`로 응답합니다.
- 첫 리뷰 보상이 지급되면 **Lv.1 → Lv.2** 레벨업 이벤트가 발생합니다.
- 이후 성장 정책은 다음과 같습니다.

| reviewGrowthCount | 표시 레벨 | stage | 경험치 표시 |
| --- | --- | --- | --- |
| 0 | Lv.1 | `EGG` | 0/100 |
| 1~5 | Lv.2 | `BABY` | 0~80/100, 리뷰당 +20 |
| 6~15 | Lv.3 | `GROWTH` | 0~90/100, 리뷰당 +10 |
| 16 이상 | Lv.4 | `FINAL` | 100/100, 최대 레벨 |

첫 리뷰 완료 시 `levelUpEvent.previousLevel`은 `1`, `levelUpEvent.newLevel`은 `2`로 내려갑니다. `characterImageUrl`은 Lv.2 이미지(`character_definitions.level2_image_url`) 기준입니다.

---

## 추가 변경 사항: 선호 반경 선택지

`PUT /api/users/me/profile`의 `preferredRadiusKm`는 연속 범위 `1~50`이 아니라 아래 선택지만 허용합니다.

```text
1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 50
```

프론트 표시는 아래처럼 처리합니다.

```text
1~10  → 각각 1km~10km
50    → 10~50km 광역 선택지
```

예시:

```json
{
  "preferredRadiusKm": 50
}
```

DB에는 `docs/sql/34-profile-radius-50km.sql`을 실행해야 `10~50km` 광역 선택지 저장이 가능합니다. 기존에 11~49 값이 저장되어 있다면 이 SQL에서 50으로 보정합니다.

---

## 참고: 리뷰/평점 저장 위치

리뷰 본문과 평점은 별도 리뷰 테이블이 아니라 아래 테이블에 저장됩니다.

```text
book.user_book_shelves.review_content
book.user_book_shelves.review_rating
book.user_book_shelves.completed_at
```

리뷰 완료 액션 로그는 아래 테이블에 저장됩니다.

```text
book.user_book_actions
```

리뷰 보상 중복 방지 이력은 아래 테이블에 저장됩니다.

```text
book.user_review_reward_logs
```
