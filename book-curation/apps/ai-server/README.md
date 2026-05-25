# AI Server

FastAPI 기반 AI/RAG 서버입니다.

## LightFM candidate reranking

LightFM은 최종 추천 응답 생성기가 아니라 Qdrant/룰베이스 후보를 압축하는 reranking stage입니다.

```text
Qdrant 100 → Rule 50 → LightFM 20 → Final response
```

운영 artifact는 Git에 커밋하지 않고 `LIGHTFM_ARTIFACT_DIR`가 바라보는 디렉터리에 배포합니다.

```bash
export LIGHTFM_ENABLED=true
export LIGHTFM_ARTIFACT_DIR=/app/artifacts/lightfm/current
export LIGHTFM_TOP_N=20
export LIGHTFM_CANDIDATE_LIMIT=50
```

상세 로컬/NAS/Kubernetes 배포 절차는 [`docs/LIGHTFM_ARTIFACT_DEPLOYMENT.md`](docs/LIGHTFM_ARTIFACT_DEPLOYMENT.md)를 확인하세요.
