# Frontend Auth Fix - External API Mode

## 왜 다시 수정했는가

팀원 중 Java/Spring Boot 백엔드를 로컬에 띄우지 못하는 사람이 있으므로, React 개발 서버가 기본적으로 외부 NAS API 서버를 직접 호출하도록 수정했습니다.

기본 API 서버:

```env
VITE_API_BASE_URL=https://book-api.taeo-dev.com
```

## 요청 URL

프론트 요청은 다음처럼 나갑니다.

```text
https://book-api.taeo-dev.com/api/auth/csrf
https://book-api.taeo-dev.com/api/auth/signup
https://book-api.taeo-dev.com/api/auth/login
https://book-api.taeo-dev.com/api/auth/me
```

중요: `VITE_API_BASE_URL`에는 `/api`를 붙이지 않는 것을 권장합니다.

```env
# 권장
VITE_API_BASE_URL=https://book-api.taeo-dev.com

# 실수해도 authApi.ts에서 보정하지만 권장하지 않음
VITE_API_BASE_URL=https://book-api.taeo-dev.com/api
```

## 실행

```bash
cd frontend
npm install
npm run dev
```

브라우저:

```text
http://localhost:5173
```

## 외부 API 직접 호출 모드에서 백엔드가 만족해야 하는 조건

외부 API 서버를 직접 호출하는 구조이므로 백엔드 CORS/쿠키 설정이 맞아야 합니다.

- CORS allowed origin에 React 개발 주소가 있어야 함
  - 예: `http://localhost:5173`
- credentials 허용 필요
- axios는 `withCredentials: true` 사용
- 세션 쿠키가 크로스 사이트로 유지되어야 한다면 `SameSite=None; Secure` 검토 필요
- `GET /api/auth/csrf`가 `XSRF-TOKEN`을 내려줘야 함
- POST 요청에 `X-XSRF-TOKEN` 헤더가 들어가야 함

## nginx /api 상대경로 모드로 쓰고 싶을 때

`.env.development`에서 아래처럼 바꾸세요.

```env
VITE_USE_RELATIVE_API=true
VITE_API_PROXY_TARGET=https://book-api.taeo-dev.com
```

그러면 브라우저는 `/api/auth/login`을 호출하고, Vite proxy가 외부 API 서버로 넘깁니다.

배포 nginx에서도 같은 개념으로 `/api`를 백엔드로 프록시하면 됩니다.
