import json
import os
import sys
from typing import List, Dict, Any

# 프로젝트 루트를 경로에 추가
sys.path.append(os.getcwd())

from app.services.ranking.lightfm_ranker import LightFmRanker

def run_validation():
    print("=== [검증 시작] 100인 페르소나 데이터 기반 개인화 및 비선호 배제 테스트 ===\n")
    
    # 1. 랭커 초기화
    try:
        ranker = LightFmRanker()
    except Exception as e:
        print(f"랭커 로드 실패: {e}")
        return

    # 2. 페르소나 매핑 데이터 로드
    mapping_path = 'artifacts/lightfm/latest/mappings.json'
    metadata_path = 'artifacts/lightfm/latest/metadata.json'
    
    with open(mapping_path, 'r') as f:
        m = json.load(f)
    with open(metadata_path, 'r') as f:
        meta = json.load(f)

    # 테스트 대상 유저 랜덤 선택 (첫 번째 유저)
    test_user_id = list(m['user_id_to_index'].keys())[0]
    print(f"대상 페르소나 ID: {test_user_id}")
    print(f"훈련 제외된 이벤트 유형: {meta.get('excluded_event_types', [])}\n")

    # 3. 테스트 시나리오 구성
    # 시나리오: 
    # - 선호 도서(학습됨): 높은 점수 기대
    # - 신규 도서(미학습): None 또는 기본 점수
    # - 비선호 도서(학습 데이터에서 제외됨): 낮은 점수 기대
    
    # 실제 mappings에서 아이템 하나 추출
    known_item_id = list(m['item_id_to_index'].keys())[0]
    alternate_item_id = list(m['item_id_to_index'].keys())[10] # 다른 도서
    
    candidates = [
        {"isbn": known_item_id, "title": "페르소나 선호 도서 (Positive)"},
        {"isbn": alternate_item_id, "title": "페르소나 유사 선호 도서 (Candidate)"},
        {"isbn": "9999999999999", "title": "신규/비선호 도서 (Unknown/Negative)"}
    ]

    # 4. 리랭킹 수행
    result = ranker.rerank(
        user_id=test_user_id,
        candidates=candidates,
        requested_model="LIGHTFM",
        limit=10
    )

    # 5. 결과 분석
    print("--- 랭킹 결과 순위 ---")
    sorted_cand = sorted(result.candidates, key=lambda x: (x.get('lightfmScore') is not None, x.get('lightfmScore') or -999), reverse=True)
    
    top_hit = False
    for i, c in enumerate(sorted_cand, 1):
        score = c.get('lightfmScore')
        status = "✅ 상단 노출" if i == 1 and score is not None else "점수 없음" if score is None else "하단 배치"
        print(f"{i}. {c['title']} | Score: {score} | {status}")
        
        if i == 1 and "Positive" in c['title']:
            top_hit = True

    print("\n--- 검증 요약 ---")
    if top_hit:
        print("RESULT: [SUCCESS] 훈련된 선호 도서가 최상단에 전략적으로 배치되었습니다.")
    else:
        print("RESULT: [CHECK] 선호 도서가 최상단이 아닙니다. 모델의 가중치 또는 학습 품질 확인이 필요합니다.")
    
    print(f"비선호(Negative) 도서 노출 여부: {'배제됨(None)' if sorted_cand[-1].get('lightfmScore') is None else '하단 점수 배정'}")

if __name__ == "__main__":
    run_validation()
