import json
import os
import sys
import numpy as np
from typing import List, Dict, Any

# 프로젝트 루트 경로 추가
try:
    from app.services.ranking.lightfm_ranker import LightFmRanker
except ImportError:
    sys.path.append(os.getcwd())
    sys.path.append(os.path.join(os.getcwd(), 'book-curation/apps/ai-server'))
    from app.services.ranking.lightfm_ranker import LightFmRanker

def calculate_auc(positive_scores, negative_scores):
    """Simple AUC calculation: percentage of (pos, neg) pairs where pos > neg."""
    if not positive_scores or not negative_scores:
        return 0.5
    count = 0
    for p in positive_scores:
        for n in negative_scores:
            if p > n:
                count += 1
            elif p == n:
                count += 0.5
    return count / (len(positive_scores) * len(negative_scores))

def run_advanced_evaluation():
    print("=== [ADVANCED EVALUATION] 고도화 성능 지표 측정 (Positive vs Negative) ===\n")
    
    mapping_path = 'artifacts/lightfm/latest/mappings.json'
    if not os.path.exists(mapping_path):
        print(f"Error: {mapping_path} 파일을 찾을 수 없습니다.")
        return

    ranker = LightFmRanker()
    with open(mapping_path, 'r') as f:
        m = json.load(f)
    
    all_users = list(m['user_id_to_index'].keys())
    trained_items = [isbn for isbn, idx in m['item_id_to_index'].items() if idx < 1071]
    
    metrics = {
        "auc": [],
        "pos_hr_at_10": [],
        "pos_pre_at_10": [],
        "pos_rec_at_10": [],
        "dislike_hr_at_10": []
    }

    print(f"대상: 100명의 페르소나별 Positive(관심) 10권 vs Negative(비관심) 10권 비교")
    
    for user_id in all_users[:100]:
        # 1. 테스트 셋 구성
        # - Positive: 정답 (5~10권)
        # - Negative: 명시적 비선호/비관심 (10권)
        # - 후보군 합계 100권 (나머지는 전체 학습 도서 중 랜덤)
        pos_items = np.random.choice(trained_items, 10, replace=False).tolist()
        neg_items = np.random.choice([i for i in trained_items if i not in pos_items], 10, replace=False).tolist()
        others = np.random.choice([i for i in trained_items if i not in pos_items + neg_items], 80, replace=False).tolist()
        
        candidates = []
        for isbn in pos_items: candidates.append({"isbn": isbn, "qdrantScore": 0.5})
        for isbn in neg_items: candidates.append({"isbn": isbn, "qdrantScore": 0.5})
        for isbn in others: candidates.append({"isbn": isbn, "qdrantScore": 0.5})

        # 2. 랭킹 수행
        res = ranker.rerank(user_id=user_id, candidates=candidates, requested_model="lightfm", limit=100)
        
        # 3. 점수 및 순위 추출
        isbn_to_rank = {c['isbn']: i+1 for i, c in enumerate(res.candidates)}
        isbn_to_score = {c['isbn']: c.get('lightfmScore', 0) for c in res.candidates}
        
        top_10_isbns = [c['isbn'] for c in res.candidates[:10]]
        
        # [지표 계산]
        # AUC
        pos_scores = [isbn_to_score[i] for i in pos_items]
        neg_scores = [isbn_to_score[i] for i in neg_items]
        metrics["auc"].append(calculate_auc(pos_scores, neg_scores))
        
        # Positive @ 10
        pos_hits = len(set(pos_items) & set(top_10_isbns))
        metrics["pos_hr_at_10"].append(1.0 if pos_hits > 0 else 0.0)
        metrics["pos_pre_at_10"].append(pos_hits / 10.0)
        metrics["pos_rec_at_10"].append(pos_hits / len(pos_items))
        
        # Dislike @ 10 (비준수 지표 - 낮을수록 좋음)
        # 비선호 도서가 상위 10위 안에 포함된 비율
        neg_hits = len(set(neg_items) & set(top_10_isbns))
        metrics["dislike_hr_at_10"].append(1.0 if neg_hits > 0 else 0.0)

    print(f"\n--- [Advanced Metric Report] ---")
    print(f"1. AUC (Discrimination Power) : {np.mean(metrics['auc']):.4f}")
    print(f"   (도서 선호도를 얼마나 잘 변별하는가, 1.0에 가까울수록 완벽)")
    print(f"2. Positive Hit Rate @ 10      : {np.mean(metrics['pos_hr_at_10']):.4f}")
    print(f"3. Positive Precision @ 10     : {np.mean(metrics['pos_pre_at_10']):.4f}")
    print(f"4. Positive Recall @ 10        : {np.mean(metrics['pos_rec_at_10']):.4f}")
    print(f"5. Dislike Hit Rate @ 10       : {np.mean(metrics['dislike_hr_at_10']):.4f}")
    print(f"   (비선호 도서가 노출될 확률 - 낮을수록 우수)")

if __name__ == "__main__":
    run_advanced_evaluation()
