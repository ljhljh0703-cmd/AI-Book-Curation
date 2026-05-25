#!/usr/bin/env python3
import argparse
import json
import random
import numpy as np
import pandas as pd
from typing import List, Dict, Any, Tuple
from lightfm import LightFM
from lightfm.data import Dataset
from lightfm.evaluation import auc_score, precision_at_k

def load_json(file_path: str) -> List[Dict[str, Any]]:
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def run_experiment(args):
    print(f"🚀 [Compressed Pool] 아이템 풀 압축 실험 (Min Interactions: {args.min_count})")
    raw_data = load_json(args.input_file)
    
    # 1. 아이템 카운팅 및 필터링
    item_counts = {}
    for entry in raw_data:
        for inter in entry.get('interactions', []):
            iid = inter['book_id']
            item_counts[iid] = item_counts.get(iid, 0) + 1
            
    # 최소 n번 이상 등장한 '메이저' 아이템만 선별
    valid_items = {iid for iid, count in item_counts.items() if count >= args.min_count}
    print(f"📦 아이템 풀 압축: 15,806종 -> {len(valid_items)}종 (밀도 집중)")

    interactions = []
    user_features_map = {}
    all_user_features = set()
    item_to_genre = {}
    
    for entry in raw_data:
        uid = entry['uuid']
        tracks = entry.get('tracks', {})
        u_feats = []
        for t in ['track_a', 'track_b', 'track_c']:
            for kw in tracks.get(t, []):
                tokens = kw.replace(":", " ").replace(",", " ").split()
                u_feats.extend(tokens)
                all_user_features.update(tokens)
        user_features_map[uid] = u_feats
        
        for inter in entry.get('interactions', []):
            iid = inter['book_id']
            if iid not in valid_items: continue
            
            action = inter['action']
            weight = 1.0
            if action == 'dislike': weight = -1.0
            interactions.append((uid, iid, weight))
            if iid not in item_to_genre:
                item_to_genre[iid] = f"Genre_{iid[:3]}"

    # 2. Dataset 구성
    all_users = sorted(list(user_features_map.keys()))
    all_items = sorted(list(valid_items))
    all_item_features = sorted(list(set(item_to_genre.values())))
    
    dataset = Dataset()
    dataset.fit(users=all_users, items=all_items, user_features=all_user_features, item_features=all_item_features)
    
    # 3. 20% Masking
    random.seed(args.random_state)
    random.shuffle(interactions)
    cut = int(len(interactions) * 0.8)
    train_data = interactions[:cut]
    test_data = interactions[cut:]
    
    train_pos = [(u, i, w) for u, i, w in train_data if w > 0]
    test_pos = [(u, i, w) for u, i, w in test_data if w > 0]
    test_neg = [(u, i, w) for u, i, w in test_data if w < 0]
    
    (train_interactions, train_weights) = dataset.build_interactions(train_pos)
    (test_interactions, _) = dataset.build_interactions(test_pos)
    user_features = dataset.build_user_features(((uid, user_features_map[uid]) for uid in all_users))
    item_features = dataset.build_item_features(((iid, [item_to_genre[iid]]) for iid in all_items))
    
    # 4. 모델 학습
    model = LightFM(no_components=args.components, loss='warp', learning_rate=args.learning_rate, random_state=args.random_state)
    model.fit(train_interactions, sample_weight=train_weights, user_features=user_features, item_features=item_features, epochs=args.epochs)
    
    # 5. 평가
    auc = auc_score(model, test_interactions, user_features=user_features, item_features=item_features).mean()
    prec = precision_at_k(model, test_interactions, user_features=user_features, item_features=item_features, k=10).mean()
    
    print("\n" + "="*50)
    print(f"✨ [Compressed] 밀도 집중 실험 결과 (풀: {len(all_items)}권)")
    print("-" * 50)
    print(f"AUC             : {auc:.4f}")
    print(f"Precision@10    : {prec:.4f}")
    print("-" * 50)
    print(f"💡 분석: 아이템 풀이 {len(all_items)}권으로 압축됨에 따라 추천 밀도가 상승함.")
    print("=" * 50 + "\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-file", default="synthetic_persona_output/persona_final_interactions_100.json")
    parser.add_argument("--min-count", type=int, default=2) # 최소 2인 이상 읽은 책만
    parser.add_argument("--epochs", type=int, default=150)
    parser.add_argument("--components", type=int, default=64)
    parser.add_argument("--learning-rate", type=float, default=0.05)
    parser.add_argument("--random-state", type=int, default=42)
    args = parser.parse_args()
    run_experiment(args)
