# book-curation-api

Spring Boot 기반 기업연계 AI 도서 큐레이션 API 서버입니다.

## 포함 기능

- 세션 기반 자체 회원가입/로그인/로그아웃
- Google/Kakao OAuth2 소셜 로그인 콜백 처리
- `users` / `user_credentials` / `user_social_accounts` 분리형 인증 구조
- 사용자 추가 프로필 저장
- 관심 카테고리/키워드 저장
- 즐겨찾는 도서관 저장
- 도서 좋아요/클릭/평점 등 행동 로그 저장
- 읽고 싶은 책/읽은 책 등 서재 상태 저장
- Spring Security + CSRF 쿠키 방식
- PostgreSQL + PostGIS 기반 근처 도서관 조회
- 도서관정보나루 `/api/libSrch` 목록 동기화 관리 API

## 실행 전 DB 준비

DBeaver에서 아래 SQL을 순서대로 실행하세요.

기존 테스트용 users 테이블이 이미 있다면 먼저 `docs/sql/00-dev-reset-auth-and-core.sql`을 실행한 뒤 아래 순서로 실행하세요.

```sql
-- 1. 도서관 테이블 + PostGIS location trigger
-- docs/sql/01-libraries.sql

-- 2. 사용자/인증/도서/개인화/대화/추천로그 테이블
-- docs/sql/02-core-schema.sql

-- 3. MVP용 KDC 대분류 seed
-- docs/sql/03-seed-book-categories.sql
```

### 기존 테스트용 users 테이블을 이미 만든 경우

이전 최소 로그인 구조는 다음 형태였습니다.

```text
book.users(id BIGSERIAL, email, password_hash, nickname, role, status)
```

현재 리팩토링된 구조는 다음 형태입니다.

```text
book.users(id UUID, primary_email, nickname, role, status)
book.user_credentials(user_id UUID, email, password_hash)
book.user_social_accounts(...)
```

따라서 기존 테스트용 `book.users`가 이미 있으면 `02-core-schema.sql`과 충돌합니다.
개발 DB에 중요한 데이터가 없다면 기존 users/auth 관련 테이블을 정리한 뒤 새 SQL을 실행하세요.
운영 데이터가 있다면 DROP이 아니라 별도 마이그레이션 SQL로 옮겨야 합니다.

## 환경변수

```bash
export DB_URL='jdbc:postgresql://192.168.0.10:15432/book_curation'
export DB_USERNAME='book_user'
export DB_PASSWORD='NAS PostgreSQL 비밀번호'
export DATA4LIBRARY_AUTH_KEY='도서관정보나루 API 키'
export ALADIN_TTB_KEY='알라딘 TTBKey'
export FRONTEND_ORIGIN='http://localhost:5173'
export OAUTH2_SUCCESS_REDIRECT_URL='http://localhost:5173/oauth/success'
export OAUTH2_FAILURE_REDIRECT_URL='http://localhost:5173/login?socialError=true'
```

Windows PowerShell 예시:

```powershell
$env:DB_URL='jdbc:postgresql://192.168.0.10:15432/book_curation'
$env:DB_USERNAME='book_user'
$env:DB_PASSWORD='NAS PostgreSQL 비밀번호'
$env:DATA4LIBRARY_AUTH_KEY='도서관정보나루 API 키'
$env:ALADIN_TTB_KEY='알라딘 TTBKey'
$env:FRONTEND_ORIGIN='http://localhost:5173'
$env:OAUTH2_SUCCESS_REDIRECT_URL='http://localhost:5173/oauth/success'
$env:OAUTH2_FAILURE_REDIRECT_URL='http://localhost:5173/login?socialError=true'
```

## 실행

```bash
gradle bootRun
```

또는 IntelliJ에서 Gradle 프로젝트로 열고 `BookCurationApiApplication` 실행.

## 프론트엔드 API 문서

프론트 개발자에게는 아래 문서를 전달하면 됩니다.

```text
docs/FRONTEND_API.md
```

## 주요 API 요약

### 인증

```http
GET  /api/auth/csrf
GET  /api/auth/oauth2/providers
GET  /oauth2/authorization/google
GET  /oauth2/authorization/kakao
GET  /login/oauth2/code/{provider}  # provider 콜백용, 프론트 직접 호출 X
POST /api/auth/signup
POST /api/auth/login
GET  /api/auth/me
POST /api/auth/logout
```

### 사용자 개인화

```http
GET    /api/users/me/profile
PUT    /api/users/me/profile
GET    /api/users/me/preferred-libraries
POST   /api/users/me/preferred-libraries
DELETE /api/users/me/preferred-libraries/{libCode}
POST   /api/users/me/book-actions
GET    /api/users/me/book-shelves
POST   /api/users/me/book-shelves
DELETE /api/users/me/book-shelves?bookId={bookId}&shelfType={shelfType}
```

### 도서관

```http
GET  /api/libraries/search?keyword=서울&limit=20
GET  /api/libraries/nearby?latitude=37.4386&longitude=127.1378&radiusMeters=5000&limit=10
POST /api/admin/libraries/sync
```

- `GET /api/libraries/search`는 일반 사용자용 도서관 검색 API입니다.
- 검색 대상은 도서관명(`libName`)과 주소(`address`)입니다.
- `libCode`는 응답 식별자, 나만의 도서관 저장, 대출 가능 여부 조회에만 사용하며 검색 조건에는 포함하지 않습니다.

## React 주의사항

세션/CSRF 방식이므로 요청에 반드시 `credentials: 'include'`를 넣어야 합니다.

`POST`, `PUT`, `PATCH`, `DELETE` 요청에는 `GET /api/auth/csrf`에서 받은 토큰을 `X-XSRF-TOKEN` 헤더로 넣어야 합니다.

## 보안 주의사항

아래 값은 Git에 올리지 않습니다.

- DB password
- 도서관정보나루 API Key
- 알라딘 TTBKey
- HCX API Key
- Google/Kakao client secret
- 원본 도서 데이터셋

OAuth access token / refresh token은 현재 DB에 저장하지 않습니다.
추후 provider API를 백그라운드에서 계속 호출해야 할 때만 암호화 저장을 별도 검토합니다.

## 소셜 로그인 설정

소셜 로그인 콜백 구현은 포함되어 있지만, 실제 provider client 설정은 secret이므로 Git에 올리지 않습니다.
템플릿 파일은 아래에 있습니다.

```text
src/main/resources/application-oauth-template.yml
```

로컬 테스트 시 템플릿을 복사해서 사용하세요.

```bash
cp src/main/resources/application-oauth-template.yml src/main/resources/application-oauth.yml
```

`application.yml`에는 아래 설정이 들어 있어 `application-oauth.yml`이 있으면 자동으로 읽습니다.

```yaml
spring:
  config:
    import: optional:classpath:application-oauth.yml
```

provider 개발자 콘솔 Redirect URI는 백엔드 콜백 주소로 등록해야 합니다.

```text
http://localhost:8080/login/oauth2/code/google
http://localhost:8080/login/oauth2/code/kakao
```

프론트는 콜백 URL을 직접 호출하지 않고 아래 URL로 이동시키면 됩니다.

```text
/oauth2/authorization/google
/oauth2/authorization/kakao
```
