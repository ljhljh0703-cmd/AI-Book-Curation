#!/usr/bin/env python3
import argparse
import json
import random
import numpy as np
import pandas as pd
from typing import List, Dict, Any, Tuple

from lightfm import LightFM
from lightfm.data import Dataset

def load_persona_data(file_path: str) -> List[Dict[str, Any]]:
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def process_interactions(personas: List[Dict[str, Any]], weight_read: float) -> Tuple[pd.DataFrame, pd.DataFrame]:
    interactions = []
    item_metadata = []
    for persona in personas:
        user_id = persona.get("persona_id")
        if not user_id: continue
        book_history = persona.get("book_history") or []
        for book in book_history:
            isbn = book.get("isbn")
            if not isbn: continue
            interactions.append({"user_id": user_id, "item_id": isbn, "weight": weight_read})
            cates = book.get("cate_depth1") or ["기타"]
            if isinstance(cates, str): cates = [cates]
            item_metadata.append({"item_id": isbn, "genres": cates})
    return pd.DataFrame(interactions), pd.DataFrame(item_metadata).drop_duplicates('item_id')

def calculate_metrics_manual(model, dataset, test_df, item_features, k=10):
    """
    전통적인 Leave-one-user-out 또는 User-wise Cold Start 검증 방식.
    각 테스트 유저별로 '전체 아이템'에 대한 스코어를 계산하여 순위를 매깁니다.
    """
    user_id_map, _, item_id_map, _ = dataset.mapping()
    inv_item_id_map = {v: k for k, v in item_id_map.items()}
    all_item_ids = np.array(list(item_id_map.values()))
    
    precisions = []
    recalls = []
    hit_rates = []
    
    test_user_ids = test_df['user_id'].unique()
    
    for user_id in test_user_ids:
        if user_id not in user_id_map: continue
        
        u_idx = user_id_map[user_id]
        # 해당 유저가 실제로 읽은 아이템 인덱스 (정답 셋)
        actual_items = set([item_id_map[iid] for iid in test_df[test_df['user_id'] == user_id]['item_id'] if iid in item_id_map])
        if not actual_items: continue
        
        # 모델을 이용해 '모든 아이템'에 대한 예측 점수 계산
        scores = model.predict(u_idx, all_item_ids, item_features=item_features)
        
        # 점수 기준 내림차순 정렬 후 상위 K개 추출
        top_k_indices = all_item_ids[np.argsort(-scores)[:k]]
        top_k_items = set(top_k_indices)
        
        # 지표 계산
        hits = len(top_k_items.intersection(actual_items))
        precisions.append(hits / k)
        recalls.append(hits / len(actual_items))
        hit_rates.append(1.0 if hits > 0 else 0.0)
        
    return np.mean(precisions), np.mean(recalls), np.mean(hit_rates)

def run_experiment(args):
    print(f"🚀 전통적 검증 방식 시작: {args.experiment_name}")
    raw_personas = load_persona_data(args.input_file)
    full_interactions, full_item_meta = process_interactions(raw_personas, args.weight_read)
    
    all_users = sorted(full_interactions['user_id'].unique().tolist())
    all_items = sorted(full_interactions['item_id'].unique().tolist())
    all_genres = sorted(list(set([g for genres in full_item_meta['genres'] for g in genres])))
    
    dataset = Dataset()
    dataset.fit(users=all_users, items=all_items, item_features=all_genres)
    
    # [Strict Cold Start Split]
    random.seed(args.random_state)
    random.shuffle(all_users)
    train_users = all_users[:int(len(all_users)*0.8)]
    test_users = all_users[int(len(all_users)*0.8):]
    
    train_df = full_interactions[full_interactions['user_id'].isin(train_users)]
    test_df = full_interactions[full_interactions['user_id'].isin(test_users)]
    
    (train_interactions, train_weights) = dataset.build_interactions((row.user_id, row.item_id, row.weight) for row in train_df.itertuples())
    item_features = dataset.build_item_features((row.item_id, row.genres) for row in full_item_meta.itertuples())
    
    model = LightFM(no_components=args.components, loss=args.loss, learning_rate=args.learning_rate, item_alpha=args.item_alpha, random_state=args.random_state)
    
    print(f"📊 스펙: 아이템 {len(all_items)}종, 학습 유저 {len(train_users)}명, 테스트 유저 {len(test_users)}명")
    print(f"⚙️ 모델 학습 중 (Loss: {args.loss})...")
    model.fit(interactions=train_interactions, sample_weight=train_weights, item_features=item_features, epochs=args.epochs, verbose=False)
    
    print("📈 전체 아이템 풀 대상 실전 랭킹 테스트 수행 중...")
    p10, r10, hr10 = calculate_metrics_manual(model, dataset, test_df, item_features, k=10)
    
    # AUC는 내장 함수 사용 (경향성 확인용)
    from lightfm.evaluation import auc_score
    (test_interactions, _) = dataset.build_interactions((row.user_id, row.item_id, 1.0) for row in test_df.itertuples())
    auc = auc_score(model, test_interactions, item_features=item_features).mean()
    
    print("\n" + "="*50)
    print(f"✨ 최종 학술적 실험 결과: {args.experiment_name}")
    print("-" * 50)
    print(f"AUC (Overall)   : {auc:.4f}")
    print(f"HitRate@10      : {hr10:.4f} (하한선 없음)")
    print(f"Precision@10    : {p10:.4f} (목표: 0.0180)")
    print(f"Recall@10       : {r10:.4f}")
    print(f"Cold Start 여부 : YES (Unseen Users)")
    print("=" * 50 + "\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--experiment-name", default="ACADEMIC_COLD_START_REPORT")
    parser.add_argument("--input-file", default="synthetic_persona_output/persona_full_result_000_099.json")
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--components", type=int, default=64)
    parser.add_argument("--learning-rate", type=float, default=0.01)
    parser.add_argument("--item-alpha", type=float, default=1e-5)
    parser.add_argument("--loss", default="warp")
    parser.add_argument("--weight-read", type=float, default=1.0)
    parser.add_argument("--num-threads", type=int, default=1)
    parser.add_argument("--random-state", type=int, default=42)
    args = parser.parse_args()
    run_experiment(args)
