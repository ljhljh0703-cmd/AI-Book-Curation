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
    print(f"🚀 [v2] 하이브리드 고도화 실험: {args.experiment_name}")
    raw_data = load_data(args.input_file)
    
    # 1. 아이템 필터링 (최소 2회 이상 발생한 아이템만 타겟팅하여 Sparsity 완화)
    item_counts = {}
    for entry in raw_data:
        for inter in entry.get('interactions', []):
            iid = inter['book_id']
            item_counts[iid] = item_counts.get(iid, 0) + 1
    
    popular_items = {iid for iid, count in item_counts.items() if count >= 1} # 1회로 유지하되 전체 풀은 유지
    
    # 2. 데이터 파싱
    users = []
    user_features_map = {}
    positive_interactions = []
    negative_interactions = []
    all_track_keywords = set()
    
    for entry in raw_data:
        uid = entry['uuid']
        users.append(uid)
        
        # Tracks 추출 (User Features)
        tracks = entry.get('tracks', {})
        u_features = []
        for t_type in ['track_a', 'track_b', 'track_c']:
            keywords = tracks.get(t_type, [])
            # 너무 긴 텍스트는 키워드 단위로 쪼개어 피처 풍부화
            for kw in keywords:
                parts = kw.replace(":", " ").replace(",", " ").split()
                u_features.extend(parts)
                all_track_keywords.update(parts)
        user_features_map[uid] = u_features
        
        # Interactions
        for inter in entry.get('interactions', []):
            iid = inter['book_id']
            action = inter['action']
            if action in ['read', 'reading', 'interested']:
                positive_interactions.append((uid, iid))
            elif action == 'dislike':
                negative_interactions.append((uid, iid))

    all_users = sorted(users)
    all_items = sorted(list({iid for uid, iid in positive_interactions} | {iid for uid, iid in negative_interactions}))
    all_features = sorted(list(all_track_keywords))
    
    print(f"📊 정제된 스펙: 유저 {len(all_users)}명, 유효 아이템 {len(all_items)}종, 토큰화된 피처 {len(all_features)}개")
    
    dataset = Dataset()
    dataset.fit(users=all_users, items=all_items, user_features=all_features)
    
    # 8:2 User-wise Split (Cold Start)
    random.seed(args.random_state)
    random.shuffle(all_users)
    train_users = all_users[:int(len(all_users)*0.8)]
    test_users = all_users[int(len(all_users)*0.8):]
    
    train_pos = [it for it in positive_interactions if it[0] in train_users]
    test_pos = [it for it in positive_interactions if it[0] in test_users]
    
    (train_interactions, _) = dataset.build_interactions(train_pos)
    (test_interactions, _) = dataset.build_interactions(test_pos)
    user_features = dataset.build_user_features(((uid, user_features_map[uid]) for uid in all_users))
    
    # 3. 모델 학습 (Learning Rate 조절 및 Epoch 증가)
    model = LightFM(no_components=args.components, loss='warp', learning_rate=args.learning_rate, random_state=args.random_state)
    print(f"⚙️ 하이브리드 모델 정밀 학습 중...")
    model.fit(train_interactions, user_features=user_features, epochs=args.epochs, verbose=False)
    
    # 4. 실전 랭킹 평가
    user_id_map, _, item_id_map, _ = dataset.mapping()
    all_item_indices = np.array(list(item_id_map.values()))
    
    p10_list, r10_list, hr10_list, dhr10_list = [], [], [], []
    
    user_dislikes = {}
    for uid, iid in negative_interactions:
        if uid not in user_dislikes: user_dislikes[uid] = set()
        if iid in item_id_map: user_dislikes[uid].add(item_id_map[iid])

    for uid in test_users:
        u_idx = user_id_map[uid]
        actual_pos = set([item_id_map[iid] for iid, u in test_pos if u == uid and iid in item_id_map])
        if not actual_pos: continue
        
        # 예측 (전체 아이템 대상)
        scores = model.predict(u_idx, all_item_indices, user_features=user_features)
        top_k_indices = all_item_indices[np.argsort(-scores)[:10]]
        top_k_items = set(top_k_indices)
        
        hits = len(top_k_items.intersection(actual_pos))
        p10_list.append(hits / 10)
        r10_list.append(hits / len(actual_pos))
        hr10_list.append(1.0 if hits > 0 else 0.0)
        
        dislike_set = user_dislikes.get(uid, set())
        d_hits = len(top_k_items.intersection(dislike_set))
        dhr10_list.append(1.0 if d_hits > 0 else 0.0)

    avg_auc = auc_score(model, test_interactions, user_features=user_features).mean()
    
    print("\n" + "="*60)
    print(f"✨ [v2 Robust Result] {args.experiment_name}")
    print("-" * 60)
    print(f"AUC (Overall)   : {avg_auc:.4f} (랜덤 0.5 대응 실력 체킹)")
    print(f"HitRate@10      : {np.mean(hr10_list) if hr10_list else 0:.4f}")
    print(f"Precision@10    : {np.mean(p10_list) if p10_list else 0:.4f}")
    print(f"Recall@10       : {np.mean(r10_list) if r10_list else 0:.4f}")
    print(f"Dislike HR@10   : {np.mean(dhr10_list) if dhr10_list else 0:.4f}")
    print("-" * 60)
    print("💡 분석: AUC가 0.5 이상으로 올라왔다면 모델이 유저 피처를 이해하기 시작한 것임.")
    print("=" * 60 + "\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--experiment-name", default="HYBRID_TRACK_ROBUST_TEST")
    parser.add_argument("--input-file", default="synthetic_persona_output/persona_final_interactions_100.json")
    parser.add_argument("--epochs", type=int, default=200)
    parser.add_argument("--components", type=int, default=128)
    parser.add_argument("--learning-rate", type=float, default=0.01)
    parser.add_argument("--random-state", type=int, default=42)
    args = parser.parse_args()
    run_experiment(args)
