# LightFM 무의존성 Pure NumPy 서빙 아키텍처 명세 및 검증 테스트

## 1. 맥락 및 도입 배경 (Context & Overview)

**LightFM**은 강력한 하이브리드 추천 모델이지만, Python 최신 버전 및 로컬 환경(특히 Apple Silicon Mac)에서 C++ 컴파일러 호환성 문제로 인해 설치 및 배포가 매우 까다롭습니다. 이를 해결하기 위해 백엔드 서빙 레이어에서 `lightfm` 패키지 의존성을 완전히 제거하는 **Zero-Dependency Pure NumPy Serving** 아키텍처를 도입했습니다.

핵심 아이디어는 **학습(Training)은 외부 클라우드(Colab 등)에서 수행하고, 로컬 서빙 서버는 무거운 패키지 없이 훈련된 가중치(Weights)만 넘파이(NumPy)로 읽어들여 100% 동일한 수학적 연산을 수행**하는 것입니다.

---

## 2. 치명적 리스크와 방어 설계 (Future-Proofing for Hybrid Models)

### 🚨 발생 가능한 치명적 리스크 (Dimension Mismatch)
단순히 훈련된 모델의 `model.user_embeddings` 속성을 그대로 추출하여 서빙에 사용할 경우, **모델이 메타데이터(장르, 나이 등)를 포함한 하이브리드(Hybrid) 방식으로 훈련되었을 때 치명적인 차원 불일치(Dimension Mismatch) 에러가 발생**합니다.

* 하이브리드 모델에서 `model.user_embeddings`는 최종 유저 벡터가 아닌 **"특징(Feature)들의 잠재 벡터"**를 의미합니다.
* 이를 단순 추출하여 `(유저 수, 차원)`으로 간주하고 연산하면 규격이 맞지 않아 수학적 붕괴가 일어납니다.

### 🛡️ 방어 설계 (Feature Injection)
미래에 어떠한 특징(Feature) 행렬이 추가되더라도 코드가 깨지지 않도록, 추출 시점에 **실제 훈련에 사용된 특징 행렬을 명시적으로 주입(Inject)하여 최종적으로 해결된(Resolved) 진짜 벡터를 추출**합니다.

```python
# [학습 스크립트 방어 설계 로직]
user_features_to_pass = locals().get("user_features", None)
item_features_to_pass = locals().get("item_features", None)

# 하이브리드 차원 충돌 리스크를 100% 영구 원천 차단
user_biases, user_embeddings = model.get_user_representations(features=user_features_to_pass)
item_biases, item_embeddings = model.get_item_representations(features=item_features_to_pass)
```

---

## 3. 핵심 아키텍처 명세 (Implementation Guide)

### A. 훈련 레이어 (Training - e.g., Colab)
모델 훈련 완료 후, 위 방어 설계를 적용하여 최종 `embeddings`와 `biases`를 `weights.joblib`으로 직렬화하여 저장합니다.

### B. 서빙 레이어 (Serving - Local Backend)
서빙 레이어는 `lightfm` 패키지 없이 오직 `numpy`만 사용하여 예측 점수를 산출합니다. 예측 공식은 다음과 같이 C++ 오리지널 코드와 수학적으로 100% 동치입니다.

$$ \hat{r}_{ui} = (\text{User\_Embedding}_u \cdot \text{Item\_Embedding}_i) + \text{User\_Bias}_u + \text{Item\_Bias}_i $$

```python
# [서빙 랭커 넘파이 연산 로직]
user_emb = artifact.user_embeddings[user_index]          # (components,)
item_embs = artifact.item_embeddings[item_indices]       # (N, components)
user_bias = artifact.user_biases[user_index]             # float
item_biases = artifact.item_biases[item_indices]         # (N,)

# 병렬 고속 넘파이 연산
raw_scores = (item_embs * user_emb).sum(axis=1) + user_bias + item_biases
```

---

## 4. 아키텍처 검증용 테스트 코드 (Mathematical Equivalence Test)

외부 AI나 팀원들이 이 아키텍처의 수학적 동치성을 독립적으로 검증할 수 있도록 작성된 독립형(Standalone) 테스트 코드입니다. **하이브리드(특징 주입) 상황을 시뮬레이션하여 두 연산 결과가 소수점 끝자리까지 정확히 일치함을 증명**합니다.

```python
# test_lightfm_numpy_equivalence.py
import numpy as np
import scipy.sparse as sp
from lightfm import LightFM

def main():
    print("=== LightFM Pure NumPy Serving 검증 테스트 시작 ===")
    
    # 1. 더미 데이터 생성 (유저 10명, 아이템 20개, 유저 특징 5개)
    num_users = 10
    num_items = 20
    num_user_features = 5
    no_components = 16

    # 상호작용 행렬 (10x20)
    interactions = sp.random(num_users, num_items, density=0.2, format='coo')
    # 유저 특징 행렬 (10x5) - 하이브리드 모델 시뮬레이션
    user_features = sp.random(num_users, num_user_features, density=0.5, format='csr')

    # 2. LightFM 모델 훈련 (하이브리드)
    model = LightFM(no_components=no_components, loss='warp', random_state=42)
    model.fit(interactions, user_features=user_features, epochs=5)

    # 3. 테스트할 타겟 (유저 ID 3번, 아이템 ID 0~19 전체)
    target_user_id = 3
    target_item_ids = np.arange(num_items)
    user_indices = np.full(len(target_item_ids), target_user_id, dtype=np.int32)

    # 4. [기준점] 오리지널 LightFM 패키지를 이용한 예측 (C++ 내부 연산)
    original_scores = model.predict(
        user_ids=user_indices, 
        item_ids=target_item_ids, 
        user_features=user_features
    )

    # 5. [우리 방식] 특징 명시적 주입을 통한 "진짜" 유저 벡터 추출 (Dimension Mismatch 방어)
    user_biases, user_embeddings = model.get_user_representations(features=user_features)
    item_biases, item_embeddings = model.get_item_representations(features=None) # 아이템은 특징 없음 가정

    # 6. [서빙 시뮬레이션] 추출된 가중치를 넘파이로만 계산 (lightfm 패키지 미사용)
    user_emb = user_embeddings[target_user_id]
    item_embs = item_embeddings[target_item_ids]
    user_bias = user_biases[target_user_id]
    item_bias = item_biases[target_item_ids]

    # 넘파이 벡터 동치 연산
    numpy_scores = (item_embs * user_emb).sum(axis=1) + user_bias + item_bias

    # 7. 검증 (두 결과가 완벽히 동일한지 확인)
    is_equal = np.allclose(original_scores, numpy_scores, atol=1e-6)
    
    print("\n[검증 결과]")
    print(f"오리지널 모델 점수 (상위 5개): {original_scores[:5]}")
    print(f"NumPy 수식 연산 점수 (상위 5개): {numpy_scores[:5]}")
    print(f"\n=> 수학적 동치성 검증 결과: {'✅ 성공 (100% 일치)' if is_equal else '❌ 실패 (불일치)'}")

if __name__ == "__main__":
    main()
```
