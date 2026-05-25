# Real User LightFM Training

이 파일은 호환용 안내입니다. 최신 절차는 아래 문서를 기준으로 사용하세요.

- `script/README_lightfm_real_user_hybrid_feature_training.md`

핵심 흐름:

1. 로컬/NAS에서 PostgreSQL에 접속해 `real_user_events.jsonl`, `real_user_features.jsonl`, `real_item_features.jsonl`을 export합니다.
2. Colab에는 DB 접속 정보를 올리지 않고 JSONL 파일만 tar.gz로 묶어서 업로드합니다.
3. `shared-pool synthetic events + real user events + real user/item features`로 `hybrid-lite LightFM`을 학습합니다.
4. 평가는 `50개 후보 -> 20개 압축` 지표를 함께 확인합니다.
