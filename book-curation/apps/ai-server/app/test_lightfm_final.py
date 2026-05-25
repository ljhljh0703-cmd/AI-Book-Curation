import json
import os
import sys

# 프로젝트 루트를 경로에 추가
sys.path.append(os.getcwd())

from app.services.ranking.lightfm_ranker import LightFmRanker

try:
    # 1. 랭커 초기화
    ranker = LightFmRanker()
    
    # 2. mappings.json에서 실제 유저와 아이템 ID 가져오기
    mapping_path = 'artifacts/lightfm/latest/mappings.json'
    if not os.path.exists(mapping_path):
        print(f"Error: {mapping_path} 파일을 찾을 수 없습니다. 현재 위치: {os.getcwd()}")
        sys.exit(1)
        
    with open(mapping_path, 'r') as f:
        m = json.load(f)
        test_user_id = list(m['user_id_to_index'].keys())[0]
        test_item_id = list(m['item_id_to_index'].keys())[0]

    print(f"테스트 유저: {test_user_id}")
    print(f"테스트 아이템(학습됨): {test_item_id}")

    # 3. 테스트 후보군
    candidates = [
        {"isbn": test_item_id, "title": "훈련에 포함된 도서"},
        {"isbn": "9999999999999", "title": "훈련에 없는 도서"}
    ]

    # 4. 리랭킹 수행
    result = ranker.rerank(
        user_id=test_user_id,
        candidates=candidates,
        requested_model="LIGHTFM",
        limit=5
    )

    # 5. 결과 출력
    print("\n--- 랭킹 결과 ---")
    for c in result.candidates:
        print(f"도서: {c['title']}, Score: {c.get('lightfmScore')}")
        if 'score_detail' in c:
            print(f"  Status: {c['score_detail'].get('lightfm_status', 'KNOWN')}")
            print(f"  Key: {c['score_detail'].get('lightfm_item_key')}")

except Exception as e:
    print(f"에러 발생: {e}")
    import traceback
    traceback.print_exc()
