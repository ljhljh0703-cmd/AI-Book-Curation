# CSRF NAS IP 배포 체크리스트

현재 기준:

```env
FRONTEND_ORIGIN=http://192.168.0.10:39080
VITE_PUBLIC_SITE_URL=http://192.168.0.10:39080
SESSION_COOKIE_SAME_SITE=lax
SESSION_COOKIE_SECURE=false
CSRF_COOKIE_SAME_SITE=lax
CSRF_COOKIE_SECURE=false
```

## CSRF 확인

```bash
curl -i http://192.168.0.10:39080/api/auth/csrf
```

정상 조건:

- HTTP 200
- `Set-Cookie: XSRF-TOKEN=...`
- JSON body에 `headerName`, `token` 존재

## 회원가입 테스트

```bash
BASE="http://192.168.0.10:39080"
TOKEN=$(curl -s -c cookies.txt "$BASE/api/auth/csrf" | python3 -c "import sys,json; print(json.load(sys.stdin)['token'])")

curl -i \
  -b cookies.txt \
  -c cookies.txt \
  -H "Content-Type: application/json" \
  -H "X-XSRF-TOKEN: $TOKEN" \
  -X POST "$BASE/api/auth/signup" \
  -d '{"email":"csrf-test-001@example.com","password":"password123","nickname":"csrf테스트"}'
```

## URL 미리보기 이미지 확인

```bash
curl -I "http://192.168.0.10:39080/bookemon.png"
curl -L "http://192.168.0.10:39080/" | grep -i "og:image"
```

주의: 카카오톡/외부 공유 미리보기는 사설 IP(`192.168.x.x`)에 접근할 수 없습니다. 외부 공유 미리보기를 보려면 공개 도메인/HTTPS로 접근 가능해야 합니다.
