import json
import os
import sys
import numpy as np
from typing import List, Dict, Any

# 프로젝트 루트 경로 추가
sys.path.append(os.getcwd())
try:
    from app.services.ranking.lightfm_ranker import LightFmRanker
except ImportError:
    sys.path.append('/Users/godju/Downloads/AI AGENT/AI Book Curation/book-curation/apps/ai-server')
    from app.services.ranking.lightfm_ranker import LightFmRanker

def calculate_precision_at_k(actual, predicted, k):
    act_set = set(actual)
    pred_set = set(predicted[:k])
    if not act_set: return 0.0
    return len(act_set & pred_set) / float(k)

def run_evaluation(simulation_mode=True):
    mode_name = "10만 권 DB 시뮬레이션 (Hybrid)" if simulation_mode else "표준 성능 측정 (Trained Items Only)"
    print(f"=== {mode_name} ===\n")
    
    mapping_path = 'artifacts/lightfm/latest/mappings.json'
    if not os.path.exists(mapping_path):
        print(f"Error: {mapping_path} 파일을 찾을 수 없습니다.")
        return

    try:
        ranker = LightFmRanker()
    except Exception as e:
        print(f"Error: 랭커 초기화 실패 ({e})")
        return

    with open(mapping_path, 'r') as f:
        m = json.load(f)
    
    all_users = list(m['user_id_to_index'].keys())
    trained_items = [isbn for isbn, idx in m['item_id_to_index'].items() if idx < 1071]
    
    metrics = {
        "precision_at_5": [],
        "hit_rate_at_20": [],
        "unknown_item_top5_ratio": []
    }

    test_users = all_users[:100]
    
    for user_id in test_users:
        if simulation_mode:
            # [시뮬레이션 모드] 신작 70권을 섞어서 리스크 측정
            actual_positives = np.random.choice(trained_items, 5, replace=False).tolist()
            other_trained = np.random.choice([item for item in trained_items if item not in actual_positives], 25, replace=False).tolist()
            unknown_items = [f"NEW_BOOK_{i}" for i in range(70)]
            
            candidates = []
            for isbn in actual_positives: candidates.append({"isbn": isbn, "qdrantScore": np.random.uniform(0.7, 0.9)})
            for isbn in other_trained: candidates.append({"isbn": isbn, "qdrantScore": np.random.uniform(0.4, 0.7)})
            for isbn in unknown_items: candidates.append({"isbn": isbn, "qdrantScore": np.random.uniform(0.6, 0.95)})
        else:
            # [표준 모드] 학습된 아이템 100권 중 정답 5권 찾기 (모델 자체의 정답률 측정)
            actual_positives = np.random.choice(trained_items, 5, replace=False).tolist()
            other_candidates = np.random.choice([item for item in trained_items if item not in actual_positives], 95, replace=False).tolist()
            
            candidates = []
            for isbn in (actual_positives + other_candidates):
                candidates.append({"isbn": isbn, "qdrantScore": 0.5}) # Qdrant 변수 통제
            unknown_items = []

        res = ranker.rerank(user_id=user_id, candidates=candidates, requested_model="lightfm", limit=20)
        predicted_isbns = [c.get('isbn') for c in res.candidates]
        
        metrics["precision_at_5"].append(calculate_precision_at_k(actual_positives, predicted_isbns, 5))
        metrics["hit_rate_at_20"].append(1.0 if set(actual_positives) & set(predicted_isbns[:20]) else 0.0)
        
        if simulation_mode:
            top_5_unknowns = len(set(unknown_items) & set(predicted_isbns[:5]))
            metrics["unknown_item_top5_ratio"].append(top_5_unknowns / 5.0)

    print(f"--- [결과 Report] ---")
    print(f"1. Precision @ 5  : {np.mean(metrics['precision_at_5']):.4f}")
    print(f"2. Hit Rate @ 20  : {np.mean(metrics['hit_rate_at_20']):.4f}")
    if simulation_mode:
        print(f"3. 미학습 도서 노출율: {np.mean(metrics['unknown_item_top5_ratio'])*100:.1f}%")
    print("\n" + "="*50 + "\n")

if __name__ == "__main__":
    # 1. 표준 성능 (모델 자체 실력)
    run_evaluation(simulation_mode=False)
    # 2. 리스크 시뮬레이션 (현장 실전)
    run_evaluation(simulation_mode=True)
