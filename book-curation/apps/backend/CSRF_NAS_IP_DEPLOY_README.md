# NAS IP 운영 백엔드 설정

현재 도커 포트 기준:

- 프론트 Origin: `http://192.168.0.10:39080`
- 백엔드 직접 주소: `http://192.168.0.10:38080`

## 운영 환경변수 권장값

환경변수를 지정하지 않아도 `application-prod.yml` 기본값이 아래처럼 동작하도록 수정했습니다.
그래도 명시적으로 넣는 것을 권장합니다.

```env
SPRING_PROFILES_ACTIVE=prod
FRONTEND_ORIGIN=http://192.168.0.10:39080
SESSION_COOKIE_SAME_SITE=lax
SESSION_COOKIE_SECURE=false
CSRF_COOKIE_SAME_SITE=lax
CSRF_COOKIE_SECURE=false
```

## 확인

```bash
curl -i http://192.168.0.10:38080/api/auth/csrf
curl -i http://192.168.0.10:39080/api/auth/csrf
```
