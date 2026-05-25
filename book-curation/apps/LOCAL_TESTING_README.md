# 로컬 개발/테스트 환경 설정 가이드

이 문서는 운영/NAS 배포 설정을 건드리지 않고 팀원 PC에서 `frontend → backend → ai-server → kure-embedding-server/Qdrant`를 실행하는 기준입니다.

## 1. 서비스 포트

| 서비스 | 로컬 포트 | 기본 주소 |
|---|---:|---|
| frontend | 5173 | `http://localhost:5173` |
| backend | 8080 | `http://localhost:8080` |
| ai-server | 8001 | `http://localhost:8001` |
| kure-embedding-server | 8002 | `http://localhost:8002` |
| Qdrant | 6333 | `http://localhost:6333` 또는 `http://100.x.x.x:6333` |
| PostgreSQL | 5432 | `jdbc:postgresql://localhost:5432/book_curation` 또는 `jdbc:postgresql://100.x.x.x:5432/book_curation` |

## 2. 실제 소스에서 사용하는 환경변수명

### frontend

- `VITE_USE_RELATIVE_API=true`
- `VITE_API_PROXY_TARGET=http://localhost:8080`
- `VITE_API_BASE_URL=`
- `VITE_OAUTH_BASE_URL=`
- `VITE_PUBLIC_SITE_URL=http://localhost:5173`

`frontend/.env.local.example`을 `frontend/.env.local`로 복사해서 사용합니다. 상대경로 모드에서는 브라우저가 `/api`만 호출하고 Vite proxy가 backend로 전달하므로 CSRF/세션 쿠키 테스트가 가장 안정적입니다.

### backend

Spring Boot는 `.env.local`을 자동으로 읽지 않습니다. `local` profile과 환경변수를 같이 사용합니다.

- `SPRING_PROFILES_ACTIVE=local`
- `DB_URL`
- `DB_USERNAME`
- `DB_PASSWORD`
- `AI_SERVER_BASE_URL=http://localhost:8001`
- `AI_INTERNAL_API_KEY`: backend가 ai-server로 보낼 `X-AI-Internal-Key` 값
- `CSRF_COOKIE_SAME_SITE=lax`
- `CSRF_COOKIE_SECURE=false`
- `SESSION_COOKIE_SAME_SITE=lax`
- `SESSION_COOKIE_SECURE=false`

`LOCAL_APP_SECRET`, `LOCAL_JWT_SECRET`, `LOCAL_SESSION_SECRET`, `LOCAL_CSRF_SECRET`, `LOCAL_API_SECRET`, `LOCAL_INTERNAL_SERVICE_TOKEN`, `LOCAL_ENCRYPTION_KEY`는 현재 backend 소스에서 직접 읽지 않습니다. JWT 구조도 현재 세션 기반 로그인에서는 사용되지 않습니다.

### ai-server

`ai-server/app/core/config.py`가 `.env` 이후 `.env.local`을 읽습니다.

- `CLOVA_API_KEY`: CLOVA Chat/Embedding 호출에 필요
- `QDRANT_URL`
- `QDRANT_API_KEY`
- `QDRANT_COLLECTION=books`
- `QDRANT_KURE_COLLECTION=books_kure`
- `KURE_EMBEDDING_BASE_URL=http://localhost:8002`
- `KURE_INTERNAL_API_KEY`: ai-server가 kure-embedding-server로 보낼 `X-KURE-Internal-Key` 값
- `KURE_INTERNAL_HEADER_NAME=X-KURE-Internal-Key`
- `AI_INTERNAL_API_KEY`: backend가 ai-server로 보낼 `X-AI-Internal-Key`와 같은 값
- `AI_INTERNAL_HEADER_NAME=X-AI-Internal-Key`
- `PERSONALIZATION_PROVIDER=PROFILE_VECTOR`
- `SEQUENCE_PROVIDER=NONE`
- `RERANKER_PROVIDER=NONE`

`KURE_API_KEY`, `KURE_INTERNAL_TOKEN`, `KURE_APP_SECRET`, `KURE_EMBEDDING_SECRET`, `KURE_SERVICE_TOKEN`은 현재 ai-server 소스에서 직접 읽지 않습니다. 실제 인증키 변수명은 `KURE_INTERNAL_API_KEY`입니다.

### kure-embedding-server

`kure-embedding-server/app/core/config.py`가 `.env` 이후 `.env.local`을 읽도록 수정했습니다.

- `APP_PORT=8002`
- `KURE_MODEL_NAME=nlpai-lab/KURE-v1`
- `KURE_MODEL_CACHE_DIR=.local/models`
- `KURE_DEVICE=cpu`
- `KURE_INTERNAL_API_KEY`: ai-server의 `KURE_INTERNAL_API_KEY`와 같은 값
- `KURE_INTERNAL_HEADER_NAME=X-KURE-Internal-Key`

`/health`는 인증 없이 호출됩니다. `/warmup`, `/embed`는 `KURE_INTERNAL_API_KEY`가 비어 있지 않으면 `X-KURE-Internal-Key` 헤더가 필요합니다.

## 3. 로컬에서 전부 직접 띄우는 예시

### Windows PowerShell

```powershell
# 1) kure-embedding-server
cd kure-embedding-server
Copy-Item .env.local.example .env.local -Force
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-torch-cpu.txt
pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 8002 --reload
```

```powershell
# 2) ai-server
cd ai-server
Copy-Item .env.local.example .env.local -Force
# .env.local에서 CLOVA_API_KEY를 실제 값으로 채우세요.
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
```

```powershell
# 3) backend
cd backend
$env:SPRING_PROFILES_ACTIVE="local"
$env:DB_URL="jdbc:postgresql://localhost:5432/book_curation"
$env:DB_USERNAME="book_user"
$env:DB_PASSWORD="본인_DB_비밀번호"
$env:AI_SERVER_BASE_URL="http://localhost:8001"
$env:AI_INTERNAL_API_KEY="17962ac470810973bbecbe004cdb3bee3bb46218fbddba6d753df718cbf01052"
.\gradlew.bat bootRun
```

```powershell
# 4) frontend
cd frontend
Copy-Item .env.local.example .env.local -Force
npm ci
npm run dev -- --host 0.0.0.0 --port 5173
```

### Git Bash/Linux

```bash
# 1) kure-embedding-server
cd kure-embedding-server
cp .env.local.example .env.local
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-torch-cpu.txt
pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 8002 --reload
```

```bash
# 2) ai-server
cd ai-server
cp .env.local.example .env.local
# .env.local에서 CLOVA_API_KEY를 실제 값으로 채우세요.
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
```

```bash
# 3) backend
cd backend
SPRING_PROFILES_ACTIVE=local \
DB_URL=jdbc:postgresql://localhost:5432/book_curation \
DB_USERNAME=book_user \
DB_PASSWORD='본인_DB_비밀번호' \
AI_SERVER_BASE_URL=http://localhost:8001 \
AI_INTERNAL_API_KEY=17962ac470810973bbecbe004cdb3bee3bb46218fbddba6d753df718cbf01052 \
./gradlew bootRun
```

```bash
# 4) frontend
cd frontend
cp .env.local.example .env.local
npm ci
npm run dev -- --host 0.0.0.0 --port 5173
```

## 4. Tailscale로 NAS DB/Qdrant만 붙는 예시

Tailscale은 IPv6보다 IPv4 `100.x.x.x`를 우선 사용합니다.

### backend → NAS PostgreSQL

```bash
export DB_URL='jdbc:postgresql://100.77.247.12:31432/book_curation'
export DB_USERNAME='book_user'
export DB_PASSWORD='BookCuration_2026!'
```

K3s NodePort로 PostgreSQL을 노출한 경우에는 팀에서 정한 외부 포트를 사용합니다. 예: `jdbc:postgresql://100.77.247.12:31432/book_curation`.

### ai-server → NAS Qdrant

`ai-server/.env.local`:

```env
QDRANT_URL=http://100.77.247.12:30633
QDRANT_API_KEY=
QDRANT_COLLECTION=books
QDRANT_KURE_COLLECTION=books_kure
```

## 5. NAS에 떠 있는 kure-embedding-server를 쓰는 예시

`ai-server/.env.local`:

```env
KURE_EMBEDDING_BASE_URL=http://100.x.x.x:8002
KURE_INTERNAL_API_KEY=NAS_KURE_서버와_동일한_키
KURE_INTERNAL_HEADER_NAME=X-KURE-Internal-Key
```

NAS의 kure-embedding-server가 `KURE_INTERNAL_API_KEY`를 비워 둔 상태라면 ai-server 쪽도 비워도 됩니다. 다만 Tailscale 내부라도 팀원이 여러 명이면 값을 맞춰 두는 편이 안전합니다.

## 6. CSRF/CORS/세션 기준

로컬 권장 구조는 `frontend`가 `/api` 상대경로로 호출하고 Vite proxy가 backend로 넘기는 방식입니다.

```text
브라우저 http://localhost:5173
→ /api/auth/csrf
→ Vite proxy
→ backend http://localhost:8080
```

- frontend axios: `withCredentials: true`
- backend CORS: `http://localhost:5173`, `http://127.0.0.1:5173` 허용
- CSRF cookie: `SameSite=Lax`, `Secure=false`
- Session cookie: `SameSite=Lax`, `Secure=false`
- CSRF header: `X-XSRF-TOKEN`

## 7. 동작 확인 curl

```bash
curl -i http://localhost:8002/health
curl -i -X POST http://localhost:8002/warmup -H 'X-KURE-Internal-Key: 05b595c966eb3a1ace07883264f4af81f8e085e523264f4157ebb104ea08b72f'
curl -i http://localhost:8001/health
curl -i http://localhost:8080/api/auth/csrf
```

PowerShell에서는 작은따옴표 대신 큰따옴표를 써도 됩니다.

## 8. Git 브랜치/커밋 예시

```bash
git checkout -b chore/local-dev-env

git add LOCAL_TESTING_README.md \
  frontend/src/api/authApi.ts \
  frontend/.gitignore \
  ai-server/.dockerignore ai-server/.env.local ai-server/.env.local.example \
  backend/.gitignore backend/src/main/resources/application-local.yml \
  kure-embedding-server/.dockerignore \
  kure-embedding-server/app/core/config.py \
  kure-embedding-server/app/main.py \
  kure-embedding-server/.env.local kure-embedding-server/.env.local.example

git commit -m "chore: add local dev environment settings"
git push -u origin chore/local-dev-env
```

프로젝트 정책상 `.env.local`을 Git에 올리지 않는다면 `.env.local.example`만 커밋하고 각자 로컬에서 복사해서 사용하세요.
