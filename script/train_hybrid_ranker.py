#!/usr/bin/env python3
import argparse
import json
import random
import numpy as np
import pandas as pd
from typing import List, Dict, Any, Tuple
from lightfm import LightFM
from lightfm.data import Dataset
from lightfm.evaluation import auc_score

def load_data(file_path: str) -> List[Dict[str, Any]]:
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def run_experiment(args):
    print(f"🚀 하이브리드 실험 시작: {args.experiment_name}")
    raw_data = load_data(args.input_file)
    
    # 1. 데이터 파싱
    users = []
    items = set()
    user_features_map = {}
    positive_interactions = []
    negative_interactions = [] # dislike 액션 기록
    
    all_track_keywords = set()
    
    for entry in raw_data:
        uid = entry['uuid']
        users.append(uid)
        
        # Tracks 추출 (User Features)
        tracks = entry.get('tracks', {})
        u_features = []
        for t_type in ['track_a', 'track_b', 'track_c']:
            keywords = tracks.get(t_type, [])
            u_features.extend(keywords)
            all_track_keywords.update(keywords)
        user_features_map[uid] = u_features
        
        # Interactions 추출
        for inter in entry.get('interactions', []):
            iid = inter['book_id']
            action = inter['action']
            items.add(iid)
            if action in ['read', 'reading', 'interested']:
                positive_interactions.append((uid, iid))
            elif action == 'dislike':
                negative_interactions.append((uid, iid))

    all_users = sorted(users)
    all_items = sorted(list(items))
    all_features = sorted(list(all_track_keywords))
    
    print(f"📊 스펙: 유저 {len(all_users)}명, 아이템 {len(all_items)}종, 유저 피처 {len(all_features)}개")
    
    # 2. Dataset 구성
    dataset = Dataset()
    dataset.fit(users=all_users, items=all_items, user_features=all_features)
    
    # 8:2 User-wise Split
    random.seed(args.random_state)
    random.shuffle(all_users)
    train_users = all_users[:int(len(all_users)*0.8)]
    test_users = all_users[int(len(all_users)*0.8):]
    
    # Interaction Matrices
    train_pos = [it for it in positive_interactions if it[0] in train_users]
    test_pos = [it for it in positive_interactions if it[0] in test_users]
    
    (train_interactions, _) = dataset.build_interactions(train_pos)
    (test_interactions, _) = dataset.build_interactions(test_pos)
    
    # User Features Matrix
    # (user_id, [feature1, feature2, ...])
    user_features = dataset.build_user_features(((uid, user_features_map[uid]) for uid in all_users))
    
    # 3. 모델 학습
    model = LightFM(no_components=args.components, loss='warp', learning_rate=args.learning_rate, random_state=args.random_state)
    print(f"⚙️ 하이브리드 모델 학습 중 (WARP Loss)...")
    model.fit(train_interactions, user_features=user_features, epochs=args.epochs, verbose=False)
    
    # 4. 평가 (Global Ranking)
    user_id_map, _, item_id_map, _ = dataset.mapping()
    all_item_indices = np.array(list(item_id_map.values()))
    
    precisions = []
    recalls = []
    hit_rates = []
    dislike_hits = []
    
    # Dislike 맵 구성
    user_dislikes = {}
    for uid, iid in negative_interactions:
        if uid not in user_dislikes: user_dislikes[uid] = set()
        if iid in item_id_map:
            user_dislikes[uid].add(item_id_map[iid])

    print("📈 미지 유저(Cold Start) 대상 실전 랭킹 테스트 수행 중...")
    for uid in test_users:
        u_idx = user_id_map[uid]
        actual_pos = set([item_id_map[iid] for iid, u in test_pos if u == uid and iid in item_id_map])
        if not actual_pos: continue
        
        # 예측
        scores = model.predict(u_idx, all_item_indices, user_features=user_features)
        top_k_indices = all_item_indices[np.argsort(-scores)[:10]]
        top_k_items = set(top_k_indices)
        
        # Metrics
        hits = len(top_k_items.intersection(actual_pos))
        precisions.append(hits / 10)
        recalls.append(hits / len(actual_pos))
        hit_rates.append(1.0 if hits > 0 else 0.0)
        
        # Dislike Check
        dislike_set = user_dislikes.get(uid, set())
        d_hits = len(top_k_items.intersection(dislike_set))
        dislike_hits.append(1.0 if d_hits > 0 else 0.0)

    # AUC
    auc = auc_score(model, test_interactions, user_features=user_features).mean()
    
    print("\n" + "="*50)
    print(f"✨ 하이브리드 콜드스타트 실험 결과: {args.experiment_name}")
    print("-" * 50)
    print(f"AUC             : {auc:.4f}")
    print(f"HitRate@10      : {np.mean(hit_rates):.4f}")
    print(f"Precision@10    : {np.mean(precisions):.4f}")
    print(f"Recall@10       : {np.mean(recalls):.4f}")
    print(f"Dislike HR@10   : {np.mean(dislike_hits) if dislike_hits else 0.0:.4f}")
    print("=" * 50 + "\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--experiment-name", default="HYBRID_TRACK_COLD_START")
    parser.add_argument("--input-file", default="synthetic_persona_output/persona_final_interactions_100.json")
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--components", type=int, default=64)
    parser.add_argument("--learning-rate", type=float, default=0.03)
    parser.add_argument("--random-state", type=int, default=42)
    args = parser.parse_args()
    run_experiment(args)
