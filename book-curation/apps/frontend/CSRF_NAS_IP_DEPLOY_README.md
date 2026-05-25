# NAS IP 운영 배포 설정

현재 도커 포트 기준:

- 프론트: `http://192.168.0.10:39080`
- 백엔드: `http://192.168.0.10:38080`

프론트는 백엔드를 직접 `38080`으로 호출하지 않고 `/api` 상대경로로 호출합니다.
프론트 Nginx가 `/api` 요청을 `http://192.168.0.10:38080/api/`로 프록시합니다.

## 배포 순서

```bash
cd frontend
npm run build
```

빌드된 `dist`를 프론트 Nginx 컨테이너의 `/usr/share/nginx/html`로 배포하세요.

`nginx-csrf-proxy-example.conf`는 프론트 Nginx 컨테이너의 실제 `default.conf`로 반영해야 합니다.

```bash
docker cp nginx-csrf-proxy-example.conf book-curation-frontend:/etc/nginx/conf.d/default.conf
docker exec book-curation-frontend nginx -t
docker exec book-curation-frontend nginx -s reload
```

## 확인

```bash
curl -i http://192.168.0.10:39080/api/auth/csrf
```
