# 포트폴리오 섹션 재편 전략

> **이 문서의 용도:** HTML 작업을 담당할 AI에게 전달하는 명세서.
> 콘텐츠 추가·수정 범위, 사용할 CSS 컴포넌트, 텍스트 초안, 설계 제약을 모두 담는다.
>
> 최종 업데이트: 2026-05-23

---

## 0. 작업 대상 파일 현황

| 파일 | 용도 | 상태 |
|---|---|---|
| `portfolio/ai book curation.html` (2,643 lines) | 부트캠프 내부 발표용 — 기준 문서 | 작업 명세 완성 (§A) |
| `portfolio/claude.html` | AI/기획 실무자 면접 포트폴리오 | 작업 명세 작성 중 (§B) |
| `팀 Report) bookemon-curation-ai.html` | 프롬프트 보조 문서 — 레퍼런스 전용 | 수정 없음 |

---

## 0-1. 공통 CSS 컴포넌트 (추가 CSS 작성 없이 재사용)

| 용도 | 클래스 |
|---|---|
| 파이프라인 흐름 | `.pipeline-flow`, `.pipe-node`, `.pipe-num`, `.pipe-info`, `.pipe-label`, `.pipe-sub`, `.pipe-connector`, `.pipe-beam` |
| 단계 수 배지 | `.funnel-badge`, `.funnel-badge.orange/.teal/.blue/.green` |
| Before / After 비교 카드 | `.problem`, `.problemHead`, `.problemBody`, `.num`, `.problemTitle`, `.problemSub`, `.before`, `.after` |
| callout 박스 | `.callout.info`, `.callout.warn`, `.callout.ok` |
| 코드블록 | `.code` |
| 핵심 수치 | `.kpi` |
| 카드·그리드 | `.card`, `.grid2`, `.grid3` |
| 표 | `.tableWrap` + `<table>` |
| 키-값 흐름 | `.mermaidLike`, `.flowRow`, `.flowKey`, `.flowVal` |
| 태그 | `.tag`, `.tagRow` |

## 0-2. 공통 글쓰기 규칙

- 기술 영어 용어는 번역 없이 한국어 문장 안에 삽입: `"fail-open합니다"`, `"artifact mapping에 없으면"`
- ML 개념은 "왜" 질문으로 문제를 먼저 제시, 해결 방향을 후술
- 수치·가중치는 산문 대신 코드블록이나 표로 직접 제시
- 시스템을 능동 주어로 서술: `"북켓몬은 ~합니다"` 형태
- fallback·안전 설계 이유는 괄호 안에 짧게 부연
- "~을 통해", "~을 활용해", "도메인 정합성", "어필", "해석 비용 0" 같은 표현 사용 금지
- 구현되지 않은 기능은 반드시 "설계값" 또는 "미구현" 명시

---

## 0-3. 최종 타겟과 포지셔닝

| 항목 | 결정 |
|---|---|
| 최종 타겟 | 게임 AI/모델 직무 실무자 |
| 문서 형태 | 시각적 포트폴리오 랜딩페이지 |
| 중심 역량 | AI 실험 설계 + 시뮬레이터 설계 + 기획 |
| 게이미피케이션 위치 | 메인 서사가 아니라 행동 데이터 수집 루프 |
| 강화학습 표현 수위 | "강화학습 기반" 금지. "강화학습형 실험 구조", "RL-style offline simulator/replay framework"까지만 허용 |

### 핵심 포지셔닝 문장

```text
초기 사용자 데이터가 부족한 AI 추천 시스템을 위해,
합성 유저 시뮬레이터와 랭킹 정책 실험 프레임워크를 설계한 프로젝트.
```

### 강화학습 표현 경계

본 프로젝트는 PPO, DQN, SAC 같은 강화학습 알고리즘을 직접 학습한 사례가 아니다.
따라서 "강화학습 기반 모델"이라고 쓰면 비약이다.

대신 다음 표현은 가능하다.

```text
사용자 상태(state), 독서 행동(action), 행동 가중치(reward proxy),
추천 정책(policy)을 분리해 offline으로 추천 정책을 실험할 수 있게 만든
강화학습형 실험 구조입니다.
```

---

## 핵심 서사 흐름 (두 파일 공통 맥락)

> 이 흐름이 두 HTML의 뼈대다. 섹션 순서나 표현 방식이 달라도 이 논리가 관통해야 한다.

```
[문제 1] AI 추천 시스템은 사용자 데이터가 있어야 작동한다
         → 그런데 초기 유저는 데이터를 남기지 않는다
         ↓
[해결 1] 북켓몬 콘텐츠 도입
         책을 읽으면 경험치 제공 → 캐릭터 진화
         목적: 리텐션 유도 + 향후 real 행동 데이터 수집
         ↓
[문제 2] 서비스 오픈 직후 real 데이터가 0이다 (Cold Start)
         LightFM을 학습시킬 수 없다
         ↓
[해결 2] Nvidia Nemotron-Personas-Korea 시뮬레이션
         1M source pool → 1,000 persona subset → 가상 유저 집단 구성
         → 실제 도서 corpus(Qdrant) 위에서 상호작용 이벤트 생성
         → LightFM 사전 학습 (Cold Start 해소)
         → 이후 real 행동 이벤트가 쌓이면 HYBRID_LITE / REAL_ONLY로 전환
         ↓
[문제 3] 추천 결과가 뭉뚱그려진다
         벡터 검색만으로는 100개 후보를 5개로 좁히기 어렵다
         ↓
[해결 3] 룰베이스 + 리랭킹 퍼널
         100(Qdrant) → 50(Rule filter) → 20(LightFM/Profile) → 5(GTE rerank + ScoreFusion)
```

**이 흐름에서 비약이 되는 표현들:**
- "기획자가 수식을 직접 설계한다" → 삭제. 수식은 구현 결과물이지 기획 산출물이 아니다.
- "해석 비용 0" → 삭제. 실제 구현은 10개 이상 신호를 프리셋 구조로 쓴다.
- "admin 콘솔에서 즉시 토글" → 삭제. 구현된 기능이 아니다.

---

# §A. `ai book curation.html` 작업 명세

> 부트캠프 내부 발표용 기준 문서.
> 기존 20개 섹션 구조 유지, 내용 추가·수정만 한다.

---

## A-1. 타겟 역량 ↔ 구현 대응

| 타겟 역량 | 북켓몬 구현 | 핵심 파일 |
|---|---|---|
| 강화학습형 시뮬레이터 환경 구성 및 실험 설계 | Nemotron persona를 초기 user state 분포로 가공 → LLM reading profile → action별 Qdrant 검색 → synthetic event 생성 | `create_persona_subset.py`, `enrich_nemotron_persona_profiles.py`, `generate_nemotron_profile_synthetic_events.py` |
| 게임 밸런스 테스트 자동화 AI 시스템 | reward proxy, shared pool 비율, ProfileReranker teacher, LightFM 후보 압축을 바꿔 추천 정책의 균형을 실험 | `generate_nemotron_rule_based_synthetic_events.py`, `train_lightfm.py` |
| 시뮬레이션 기반 실험 프레임워크 개발 | 3-tier 생성 전략 + `synthetic_max_ratio` + `real_weight_multiplier` + training mode 전환 + fallback 정책 검증 | `train_lightfm.py`, `lightfm_ranker.py` |

> 역량 연결 문장은 HTML에 직접 쓰지 않는다. 실험 설계 구조와 파이프라인 자체를 명확히 보여주는 것으로 충분하다.

---

## A-1-1. Nvidia Persona Dataset 가공은 시뮬레이션과 연결되는가?

### 결론

연결된다. 다만 "Nvidia Dataset을 사용했다" 자체가 시뮬레이션은 아니다.
시뮬레이션으로 인정받으려면 dataset이 아래 구조 안에서 역할을 가져야 한다.

```text
Persona Dataset
→ 초기 user state 분포
→ LLM reading profile
→ action별 intent/query
→ 실제 도서 corpus(Qdrant)와 상호작용
→ synthetic event log
→ ranking/model experiment
```

즉, Nvidia Dataset은 "행동 로그"가 아니라 "가상 사용자 집단의 초기 상태 분포"다.
이 상태를 action으로 변환하고, 실제 도서 후보 위에서 event를 발생시킨 뒤,
reward weight와 policy를 바꿔 실험할 때 비로소 simulator framework로 이어진다.

### 냉정한 검토

| 판단 항목 | 결론 |
|---|---|
| Dataset 확보/가공 자체 | 강점은 있지만 단독으로는 AI 시뮬레이션이 아님 |
| Persona → profile 변환 | 시뮬레이터의 user state 생성 단계로 설득력 있음 |
| Qdrant 실제 도서만 사용 | LLM 환각을 막고 environment action space를 실제 corpus로 제한하므로 중요 |
| Synthetic event 생성 | state가 action log로 바뀌는 핵심 연결부 |
| Rule teacher 재점수화 | simulator event를 production policy 기준으로 검증하는 단계 |
| LightFM 학습/평가 | 생성된 event가 모델 실험으로 이어지는 최종 근거 |

### 반드시 피해야 할 표현

- "Nvidia 데이터셋으로 실제 사용자 행동을 확보했다" → 거짓. 실제 행동 로그가 아니다.
- "강화학습 모델을 학습했다" → 비약. RL 알고리즘 학습은 없다.
- "페르소나가 책을 직접 선택했다" → 부정확. 스크립트가 persona state를 기반으로 Qdrant 후보를 검색하고 event를 생성했다.

### 써도 되는 표현

```text
Nvidia Nemotron-Personas-Korea를 원천 persona pool로 사용해
가상 사용자의 초기 state distribution을 만들었습니다.
이후 LLM으로 독서 성향 profile을 구조화하고,
Qdrant에 색인된 실제 도서 corpus 안에서 action별 후보를 검색해
LightFM 학습용 synthetic interaction event를 생성했습니다.
```

---

## A-2. Nemotron 합성 유저 시뮬레이터 — 핵심 실험 구조

### 전체 파이프라인 흐름

```
nvidia/Nemotron-Personas-Korea (HuggingFace, 1M rows, 28 fields)
        |
        v
[Step 0] create_persona_subset.py
         └─ 서브셋 로컬 JSONL 저장
            (persona_id: "persona:nemotron:XXXXXX:hash")
        |
        ├─────────────────────────────────────────┐
        v                                         v
[Tier 1]                                   [Step 1]
generate_nemotron_persona_synthetic_events  enrich_nemotron_persona_profiles.py
  페르소나 28개 필드 값을 이어붙인 단일 텍스트    페르소나 JSON
  → KURE 임베딩 (행동 유형 구분 없는 단일 쿼리)  → CLOVA HCX-007
  → Qdrant 벡터 검색                          → reading profile 생성
  → 유사도 상위 → positive 이벤트                (텍스트 8개 + 수치 4개)
  → 유사도 하위 → DISLIKE 이벤트                         |
  user_source: SYNTHETIC_NEMOTRON_QDRANT                 v
                                                  [Tier 2]
                                                  generate_nemotron_profile_synthetic_events.py
                                                    행동 유형별 profile text로 Qdrant 검색
                                                    (FAVORITE → interest_profile_text
                                                     DISLIKE  → dislike_profile_text, ...)
                                                    user_source: SYNTHETIC_NEMOTRON_LLM_PROFILE_QDRANT
                                                          |
                                                          v
                                                  [Tier 3]
                                                  generate_nemotron_rule_based_synthetic_events.py
                                                    Tier2 후보를 production ProfileReranker로 재점수화
                                                    → 실제 서빙 룰 기준으로 이벤트 재정렬
                                                    user_source: SYNTHETIC_NEMOTRON_LLM_PROFILE_RULE_BASED
        |
        └─────────────────────────────────────────┘
                                |
                                v
                        train_lightfm.py
                          real + synthetic 혼합 학습
                          → model.joblib 저장
```

### Tier별 설계

**Tier 1: 페르소나 필드 직접 임베딩**

28개 필드 값을 이어붙인 단일 텍스트를 KURE로 임베딩한다.

```python
parts = [compact_value(value, max_chars=700) for value in persona_fields.values()]
persona_text = " ".join(parts)
```

한계: 행동 유형을 구분하지 않는 단일 쿼리라 "지금 읽고 싶은 책"과 "다 읽은 책"을 같은 벡터로 검색한다.

**Tier 2: LLM으로 행동 유형별 검색 쿼리 분리**

페르소나 JSON → CLOVA HCX-007 → reading profile 12개 필드 생성.

텍스트 8개 (Qdrant 검색 쿼리):

| 필드 | 용도 |
|---|---|
| `interest_profile_text` | FAVORITE_ADD 검색용 |
| `reading_now_profile_text` | READING_ADD 검색용 |
| `read_completed_profile_text` | READ_ADD 검색용 |
| `dislike_profile_text` | DISLIKE_ADD 검색용 |
| `search_profile_text` | 범용 검색 쿼리 |
| `preference_summary` | 선호 요약 |
| `dispreference_summary` | 비선호 요약 |
| `reading_purpose_summary` | 독서 목적 요약 |

수치 4개 (이벤트 생성 편향 조정):

| 필드 | 범위 | 의미 |
|---|---|---|
| `rating_bias` | [0, 1] | 높은 평점을 주는 경향 |
| `review_sentiment_bias` | [0, 1] | 긍정적 리뷰를 쓰는 경향 |
| `exploration_level` | [0, 1] | 낯선 장르 탐색 경향 (후보 offset 조정) |
| `confidence` | [0, 1] | LLM이 추론한 profile 신뢰도 |

설계 제약: LLM은 책 제목·ISBN·출판사를 생성하지 않는다. 후보는 반드시 Qdrant 실제 도서에서만 가져온다.

**Tier 3: production 룰로 합성 이벤트 재검증**

Tier 2 후보를 production `ProfileReranker`에 통과시켜 재점수화한다.
실제 서빙 중인 룰 로직이 합성 이벤트의 순서를 다시 정렬하는 teacher 역할을 한다.

### LightFM 학습 실험

**Training mode 전환 전략**

| Mode | 내용 | 사용 시점 |
|---|---|---|
| `PERSONA_ONLY` | 합성 이벤트만 사용 | 서비스 초기, real 데이터 0건 (bootstrap) |
| `HYBRID_LITE` | real + synthetic 혼합, 비율 상한 적용 | 일반 운영 (default) |
| `REAL_ONLY` | real 이벤트만 사용 | real 데이터가 충분히 쌓인 이후 |

**혼합 비율 공식**

```python
synthetic_max_ratio = 0.5  # default
max_synthetic = int(real_count * ratio / (1.0 - ratio))
# ratio=0.5: synthetic ≤ real_count (50/50 상한)
# real_count == 0: synthetic 전량 허용 (bootstrap 지원)
```

**Event weight**

| 이벤트 | Weight | 비고 |
|---|---|---|
| READ_ADD | 1.0 | 기본 신호 |
| FAVORITE_ADD, READING_ADD | 3.0 | 적극적 관심 |
| RATING_ADD, REVIEW_ADD | 4.0 | 가장 강한 선호 신호 |
| DISLIKE_ADD | 제외 | LightFM에서는 빼고 ScoreFusion에서만 반영 |

real 이벤트에는 `real_weight_multiplier=2.0`을 추가로 곱한다.

**하이퍼파라미터**

| 파라미터 | 값 | 비고 |
|---|---|---|
| `loss` | `warp` | implicit feedback 기반 pairwise ranking loss |
| `components` | `32` | user/item latent factor 차원 수 |
| `epochs` | `10` | |
| `learning_rate` | `0.03` | |
| `random_state` | `42` | 재현 가능한 실험을 위해 고정 |

---

## A-3. HTML 작업 명세 (ai book curation.html)

### [작업 A-1] §14 페르소나 섹션 — 3-tier 블록 추가

**위치:** `<section id="persona">` 내부, 기존 카드 그리드 아래에 추가

**기존 유지 콘텐츠 (손대지 않음):**
- "왜 persona가 필요했나?" 카드
- "왜 Qdrant 실제 도서를 사용했나?" 카드
- 63 events per persona 코드블록
- source_weight / user feature / item feature 3-카드 그리드

**추가할 블록 순서:**

#### 블록 A — cold start 문제 제시
컴포넌트: `.problem`

```
problemHead:
  제목: "Nemotron 기반 합성 유저 시뮬레이터"
  부제: "서비스 오픈 전 cold start를 어떻게 해결했나"

problemBody (.grid2):
  .before:
    제목: 문제
    내용: "서비스 오픈 전 실사용자 interaction이 0건이라
           LightFM을 학습시킬 수 없었습니다.
           추천 모델 없이 서비스를 열면 cold start 상태 그대로
           유저를 맞이하게 됩니다."

  .after:
    제목: 접근
    내용: "nvidia/Nemotron-Personas-Korea를 1M source pool로 두고,
           그중 1,000 persona subset을 안정적인 persona_id로 저장했습니다.
           이후 실제 도서 corpus(Qdrant) 위에서 상호작용 이벤트를 생성해
           LightFM 학습 데이터로 사용했습니다."
```

#### 블록 B — 3-tier 파이프라인
컴포넌트: `.grid3` 카드 3개 (Tier 1·2·3는 순차가 아닌 단계적 품질 향상 전략이므로 `.pipeline-flow` 단선 대신 그리드 사용)

```html
<div class="grid3">
  <div class="card">
    <span class="funnel-badge orange">Tier 1</span>
    <h3>페르소나 필드 직접 임베딩</h3>
    <p>28개 필드 값을 이어붙인 단일 텍스트 → KURE 임베딩 → Qdrant 검색</p>
    <div class="tag">SYNTHETIC_NEMOTRON_QDRANT</div>
  </div>
  <div class="card">
    <span class="funnel-badge teal">Tier 2</span>
    <h3>LLM 프로파일 기반 행동 유형별 검색</h3>
    <p>페르소나 JSON → CLOVA HCX-007 → reading profile 12개 필드 → 행동 유형별 Qdrant 검색</p>
    <div class="tag">SYNTHETIC_NEMOTRON_LLM_PROFILE_QDRANT</div>
  </div>
  <div class="card">
    <span class="funnel-badge blue">Tier 3</span>
    <h3>Production Rule Teacher</h3>
    <p>Tier 2 후보를 production ProfileReranker로 재점수화 → 실제 서빙 룰 기준으로 재정렬</p>
    <div class="tag">SYNTHETIC_NEMOTRON_LLM_PROFILE_RULE_BASED</div>
  </div>
</div>
```

#### 블록 C — Tier 2 LLM 프로파일 상세
컴포넌트: `.card` 안에 `<h3>` + `.tableWrap`

텍스트 필드 표 (필드명 / 행동 유형 / 용도), 수치 필드 표 (필드명 / 범위 / 의미) — 위 A-2 내용 그대로 사용.

#### 블록 D — 설계 제약
컴포넌트: `.callout.warn`

```
"LLM은 책 제목·ISBN·출판사를 직접 생성하지 않습니다.
 후보 도서는 반드시 Qdrant books_kure 컬렉션의 실제 데이터에서만 가져옵니다."
```

---

### [작업 A-2] §13 LightFM 섹션 — training mode 블록 추가

**위치:** `<section id="lightfm">` 내부, 기존 callout (`loss=warp, components=32...`) 아래에 추가

**블록 A** — training mode 표: `.card` + `.tableWrap` (위 A-2 내용 그대로)

**블록 B** — 혼합 비율 공식: `.code` (위 A-2 코드블록 그대로)

**블록 C** — real_weight_multiplier: `.callout.info`
```
"real 이벤트에는 real_weight_multiplier=2.0을 추가로 곱합니다.
 합성 데이터보다 실제 유저 행동을 더 신뢰하기 때문입니다."
```

---

### [작업 A-3] §17 문제 해결 사례 — 케이스 재편

**위치:** `<section id="issues">` (line 2025~2196), 총 8개 `.problem` 블록

나머지 5개(사례 1·2·3·4·8)는 현행 유지.

**수정: 사례 5 (line 2114) — LightFM이 실제 후보를 점수화하지 못하는 문제**

```
problemSub 교체: "가설 → 실험 → 결론"

.before 제목/내용:
  "LightFM artifact에 user/item이 없을 때 예외 처리 없이 전체 추천이 실패하는 문제가 있었습니다.
   artifact mapping에 없는 user/item이 들어왔을 때 fallback 사유를 남기고
   RULE_BASED로 내려가는 방안을 정리했습니다."

.after 제목/내용:
  "현재 구현에서 직접 확인되는 fallback은 UNKNOWN_USER, NO_KNOWN_ITEMS,
   ARTIFACT_LOAD_FAILED 등입니다.
   INSUFFICIENT_KNOWN_ITEMS는 artifact contract 문서 기준으로만 분리해 표기합니다."
```

**수정: 사례 7 (line 2156) — GTE에 숫자 점수를 문서 텍스트로 넣을 위험**

```
problemSub 교체: "가설 → 실험 → 결론"

.before:
  "GTE reranker 입력 문서에 qdrant/rule/lightfm 점수를 넣으면
   reranker가 점수 정보를 참고해 정렬 품질이 높아질 것이라 가정했습니다."

.after:
  "수치 정보가 도서 텍스트의 semantic signal을 오염시킬 위험이 있어 분리했습니다.
   GTE 입력 문서는 도서 텍스트 전용으로 분리하고,
   qdrant/rule/lightfm 점수는 ScoreFusion 단계에서만 반영합니다."
```

**추가: 사례 9 — GTE reranker timeout 대비 (신규, `</section>` 바로 앞)**

```html
<!-- 사례 9 -->
<div class="problem">
  <div class="problemHead">
    <div class="num">9</div>
    <div>
      <div class="problemTitle">GTE reranker timeout 대비</div>
      <div class="problemSub">가설 → 실험 → 결론</div>
    </div>
  </div>
  <div class="problemBody">
    <div class="before">
      <strong>가설 · 실험</strong>
      <p>GTE reranker는 외부 추론 단계이므로 timeout 가능성이 있습니다.
         reranker 장애가 전체 추천 응답을 막지 않도록 fail-open 정책을 검토했습니다.</p>
    </div>
    <div class="after">
      <strong>결론 · 설계 변경</strong>
      <p>GTE reranker가 응답하지 않으면 rerankerScore를 0으로 처리하고
         ScoreFusion 단독으로 최종 순위를 결정합니다. (fail-open)</p>
    </div>
  </div>
</div>
```

---

# §B. `claude.html` 작업 명세

> 게임 AI/모델 직무 실무자 대상 시각적 포트폴리오 랜딩페이지.
> Claude가 만든 "기획자가 수식을 설계한 프로덕트 백서" 프레임을 걷어내고,
> "합성 유저 시뮬레이터 + 랭킹 정책 실험 프레임워크" 중심으로 재작성한다.

---

## B-0. 최신 `claude.html` 재점검 결과

### 총평

현재 `claude.html`은 방향성은 맞다.
Hero, Synthetic User Simulator, Boundaries, RL-style 표현 경계는 이전보다 크게 개선됐다.

다만 아직 실무자 관점에서 신뢰도를 떨어뜨리는 비약이 남아 있다.
가장 큰 문제는 "시각적으로 좋아 보이는 기술 서사"가 실제 구현과 다른 수식·조건을 다시 끌어온 점이다.

### 유지할 것

| 항목 | 판단 |
|---|---|
| `Synthetic User Simulator × Ranking Policy Experiment` 포지션 | 유지 |
| PPO/DQN/SAC 미학습 명시 | 유지 |
| Nvidia Dataset을 행동 로그가 아니라 state pool로 설명 | 유지 |
| Qdrant 실제 도서 corpus만 사용해 hallucination 차단 | 유지 |
| Retention as Data Collection Loop 프레임 | 유지 |
| `100 → 50 → 20 → 5` 다단 퍼널 본문 설명 | 유지 |
| `What this is / What this is not` boundary 섹션 | 유지 |

### 반드시 고칠 것

| 위치/내용 | 문제 | 수정 방향 |
|---|---|---|
| Hero sub: `"Nvidia Nemotron 1M 페르소나를 가공"` | 1M 전체를 처리한 것처럼 읽힘 | `"1M source pool에서 1,000 persona subset을 만들고"`로 수정 |
| Hero stat: `100 → 5` | 실험 설계 역량이 약해짐 | `100 → 50 → 20 → 5`로 수정 |
| ScoreFusion 수식: `S_personal + S_pop + S_recency` | 실제 구현과 다름 | `qdrant / rule / personalization / reranker` 정규화 가중합으로 교체 |
| XP table의 별점 `+30`, 찜 `+40` | 현재 코드 근거가 약함 | `설계값`으로 명시하거나 XP 수치 제거 |
| `SELECT FOR UPDATE + GREATEST()`를 코드 계약처럼 서술 | 바로 아래 spec-impl gap과 충돌 | "설계 명세 / 정합 예정"으로 낮춤 |
| `INSUFFICIENT_KNOWN_ITEMS`를 구현 fallback처럼 표기 | 현재 `lightfm_ranker.py` 직접 구현에는 없음 | 구현 확인 fallback과 문서 계약 fallback을 분리 |
| GTE 품질 저하·timeout 사례 | 측정 결과처럼 단정됨 | "위험을 확인하고 분리", "장애 가능성에 대비해 fail-open 선택"으로 낮춤 |

### 반영 누락 여부

| 기존 명세에서 요구한 내용 | 현재 반영 상태 | 추가 지시 |
|---|---|---|
| 게임 AI/모델 실무자 타겟 | 반영됨 | Hero/section 제목은 유지 |
| 강화학습형 실험 구조, RL-style boundary | 반영됨 | "강화학습 기반" 표현은 계속 금지 |
| Nvidia Persona Dataset 가공 과정 | 반영됨 | 단, 1M 전체 처리처럼 보이는 표현 수정 필요 |
| 행동 데이터 수집 루프 | 반영됨 | XP 수치 근거만 정리 필요 |
| 수치 기반 포트폴리오 | 반영됨 | 근거 있는 수치만 유지 |
| 시각적 포트폴리오 랜딩페이지 | 부분 반영 | `claude.html`이 데이터 객체만 있는 구조라면 렌더링 shell 확인 필요 |
| AI 실험 설계 + 시뮬레이터 설계 + 기획 | 반영됨 | ScoreFusion/LightFM 부분을 실제 구현 기준으로 정정 필요 |

---

## B-0-1. 추가 디벨롭 포인트 — 논리 연결 보강

최신 `claude.html`은 개별 섹션의 방향은 맞지만, 몇몇 요소가 아직 따로 노는 느낌이 있다.
아래 지점은 구현 사실성보다 "읽는 흐름" 기준으로 보강해야 한다.

### 1. 두 데이터 루프가 합류하는 지점을 앞에 보여줘야 한다

현재 흐름은 `북켓몬 XP/진화`와 `Nemotron synthetic event`가 각각 설명된다.
하지만 면접관 입장에서는 "게임 루프와 Nvidia simulator가 왜 같은 프로젝트 안에 있지?"라고 느낄 수 있다.

따라서 §01 또는 §02 끝에 아래 구조를 추가한다.

```text
Live Behavior Loop
추천 → 독서대 등록 → 리뷰/평점/찜/거부 → real interaction event

Offline Simulation Loop
persona state → action별 Qdrant 검색 → synthetic interaction event

두 루프는 같은 event schema로 합류하고,
train_lightfm.py에서 PERSONA_ONLY → HYBRID_LITE → REAL_ONLY 전환 전략으로 이어진다.
```

이 연결이 들어가야 `Retention as Data Collection Loop`가 뜬금없는 게임 설명으로 보이지 않는다.

### 2. "게임 AI/모델 직무"와 "책 추천 도메인" 사이의 전이 논리를 명시해야 한다

책 추천 도메인 자체는 게임 AI가 아니다.
따라서 게임 AI/모델 실무자에게 보여주려면 도메인보다 구조를 먼저 번역해야 한다.

```text
이 프로젝트의 도메인은 책 추천이지만,
보여주려는 역량은 player/user model, action space, reward proxy,
offline replay, policy comparison을 설계한 경험입니다.
```

이 문장은 Hero 직후 또는 §05 역량 매핑 직전에 들어가는 것이 좋다.
그래야 "왜 게임 AI 직무 포트폴리오에 북 추천이 나오지?"라는 이탈을 막는다.

### 3. LightFM의 역할을 "모델 성능 자랑"이 아니라 "후보 압축기"로 고정해야 한다

현재 문서에는 LightFM 학습/평가 수치가 많다.
하지만 LightFM이 최종 추천 생성기처럼 보이면 핵심이 흐려진다.

반드시 아래 문장을 §04 앞부분에 넣는다.

```text
LightFM은 최종 Top-5 생성기가 아니라,
Qdrant/Rule이 만든 후보를 50개에서 20개로 줄이는 candidate compressor입니다.
최종 노출 순위는 GTE reranker와 ScoreFusion, final stage에서 결정됩니다.
```

### 4. Shared pool 실험은 갑자기 나오면 안 된다

`shared pool 70/25/5`는 좋은 실험 포인트지만,
맥락 없이 나오면 임의의 비율 조정처럼 보인다.

앞에 반드시 문제를 둔다.

```text
초기 synthetic event를 persona별로 완전히 독립 생성하면,
사용자 간 item overlap이 부족해 collaborative filtering이 관계를 학습하기 어렵습니다.
shared pool은 이 문제를 줄이기 위해 일부 후보를 그룹/전역 단위로 공유시킨 실험입니다.
```

이렇게 써야 shared pool이 "뜬금없는 비율"이 아니라 CF 학습 조건을 만들기 위한 설계로 읽힌다.

### 5. GTE와 ScoreFusion의 역할을 분리해야 한다

현재 `GTE/ScoreFusion`이 묶여 있어 둘 다 최종 rerank처럼 보인다.
역할을 다음처럼 나눈다.

| 구성 | 역할 |
|---|---|
| GTE reranker | 후보 텍스트의 semantic relevance를 다시 평가 |
| ScoreFusion | qdrant/rule/personalization/reranker score를 정규화해 결합 |
| final stage | finalScore 기반 정렬 후 최종 노출 개수와 다양성 처리 |

### 6. 평가 지표는 "수치 나열"이 아니라 질문에 답해야 한다

아래처럼 metric을 질문과 묶어야 한다.

| 질문 | 지표 |
|---|---|
| 모델이 positive item을 구분하는가? | `TEST auc` |
| Top-10 안에 positive가 들어오는가? | `positive_hit_rate@10` |
| 추천 리스트가 얼마나 낭비 없이 맞는가? | `positive_precision@10` |
| 전체 positive 중 얼마나 회수하는가? | `positive_recall@10` |
| 싫어한 책을 얼마나 피하는가? | `dislike_hit_rate@10` |

### 7. Boundary는 마지막에만 두지 말고 초반에도 짧게 둔다

RL-style 표현은 매력적이지만 오해 가능성이 높다.
Hero 직후에 한 줄 boundary를 먼저 넣고, 마지막 §06에서 상세 boundary를 다시 보여주는 구성이 안전하다.

```text
Note: PPO/DQN/SAC을 학습한 사례가 아니라,
state/action/reward/policy를 분리한 offline simulator/replay framework입니다.
```

---

## B-0-2. AI 직무 심사관 관점 리스크 검증

아래 항목은 AI/모델 직무 실무자가 포트폴리오를 볼 때 실제로 의심할 만한 지점이다.
문서에는 강점을 더 추가하기보다, 의심을 먼저 줄이는 방향으로 반영한다.

| 리스크 | 심사관이 할 질문 | 위험도 | 방어 전략 |
|---|---|---:|---|
| RL 과장으로 보임 | "강화학습이라고 했는데 어떤 알고리즘을 학습했나요?" | 높음 | Hero 직후와 Boundaries에서 PPO/DQN/SAC 미학습을 명시. `reward` 대신 `reward proxy` 사용 |
| synthetic persona 신뢰성 | "Nemotron persona가 실제 사용자 분포를 대표하나요?" | 높음 | 대표성 주장 금지. cold start bootstrap용 initial state distribution이라고만 설명 |
| 실제 유저 성과 부재 | "운영 A/B나 real user metric이 있나요?" | 높음 | offline baseline/reference라고 표기. 운영 성과가 아니라 실험 프레임워크 설계로 포지셔닝 |
| 게임 AI 직무와 책 추천 도메인 거리 | "이게 게임 AI와 무슨 관련이 있나요?" | 높음 | 도메인은 책 추천, 역량은 user/player model · action space · reward proxy · offline replay · policy comparison이라고 번역 |
| 북켓몬이 장난감처럼 보임 | "캐릭터 진화가 AI 모델과 어떤 관련인가요?" | 중간 | 캐릭터는 메인 서사가 아니라 real behavior event를 수집하는 retention loop라고 설명 |
| LightFM 성능 과장 | "LightFM이 최종 추천을 만든 건가요?" | 중간 | LightFM은 50 → 20 candidate compressor라고 고정. final은 GTE/ScoreFusion/final stage로 분리 |
| ScoreFusion 수식 불일치 | "문서 수식이 코드와 맞나요?" | 높음 | S_pop/S_recency 제거. 실제 qdrant/rule/personalization/reranker normalized fusion만 표기 |
| 본인 기여도 불명확 | "팀 프로젝트에서 정확히 뭘 했나요?" | 높음 | 역할 섹션을 추가해 `실험 설계`, `persona pipeline`, `ranking policy framing`, `문서/기획` 중 본인 기여 범위를 명시 |
| 수치 출처 불명확 | "63K, 0.785, 0.320은 어디서 나온 값인가요?" | 중간 | 수치마다 `source`, `scope`, `not production A/B`를 붙임 |
| 너무 많은 기술 스택 나열 | "핵심이 추천인지, 게임인지, LLM인지, RL인지 모르겠습니다" | 중간 | Hero와 섹션 순서를 3축으로 제한: Simulator / Ranking Policy / Data Loop |
| 구현 안 된 명세 혼입 | "이건 구현된 기능인가요, 설계인가요?" | 높음 | 구현 완료, 설계값, 미구현, 정합 예정 라벨을 구분 |
| 평가 지표의 타당성 | "이 metric이 왜 중요한가요?" | 중간 | metric을 질문과 연결. AUC/hit/precision/recall/dislike_hit_rate의 의미를 설명 |

### 심사관에게 가장 안전한 한 줄 답변

```text
강화학습 모델을 학습한 프로젝트라기보다,
초기 real interaction이 없는 상황에서 synthetic user state와 real corpus를 결합해
추천 정책을 offline으로 반복 실험할 수 있게 만든 simulator/replay framework입니다.
```

### 면접에서 먼저 말하면 좋은 경계 문장

```text
이 프로젝트에서 Nvidia persona는 실제 사용자 로그가 아니라 cold start용 초기 state distribution입니다.
PPO나 DQN을 학습하지 않았고, event weight를 reward proxy로 두어
ranking policy와 candidate compression을 offline에서 비교할 수 있게 설계했습니다.
```

### 추가로 넣으면 좋은 "내 역할" 섹션

현재 문서에는 시스템 구조 설명은 강하지만, 본인 기여 범위가 약하게 보일 수 있다.
AI 직무 심사관은 팀 프로젝트에서 ownership을 강하게 본다.
따라서 §05 역량 매핑 앞이나 뒤에 아래 블록을 추가한다.

```text
My Role
- 초기 데이터 부족 문제를 simulator/replay 문제로 재정의
- Nemotron persona → reading profile → synthetic event 생성 흐름 설계
- synthetic/real event가 같은 학습 schema로 합류하는 training mode 전략 정리
- Qdrant 100 → Rule 50 → LightFM/Profile 20 → ScoreFusion/GTE → Final 5 랭킹 퍼널 구조화
- RL-style 표현 경계와 구현/설계/미구현 범위 문서화
```

단, 실제 본인 구현 범위와 다르면 반드시 수정한다.
구현하지 않은 부분을 "내가 구현했다"로 쓰면 가장 큰 리스크가 된다.

### 최종 판단

이 포트폴리오는 "모델 성능을 크게 끌어올린 사례"로 보이면 약하다.
반대로 "데이터가 없는 상태에서 모델 실험이 가능하도록 시뮬레이터, synthetic event, 후보 압축, fallback, 평가 기준을 설계한 사례"로 보이면 강하다.

따라서 문서의 최종 방향은 아래처럼 고정한다.

```text
성과 과장 < 실험 구조
서비스 소개 < simulator 설계
게임 콘텐츠 < behavior data loop
강화학습 주장 < RL-style 구조 경계
모델 성능 자랑 < candidate/policy experiment framework
```

---

## B-1. 현재 섹션 구조와 처리 방향

| 섹션 | 현재 내용 | 처리 |
|---|---|---|
| Hero | "기획자가 직접 수식을 설계한 AI 큐레이션 설계 문서" | **전면 교체** → simulator / experiment framework 포지션 |
| §01 Vision & Hook | 추상적 카드 3개, 협업 브릿지 중심 | **전면 재편** → "Why This System" |
| §02 Product Mechanism · Gamification | 북켓몬 XP/진화 시스템 | 유지하되 "행동 데이터 수집 루프"로 낮춤 |
| §03 Core Engine · Re-ranking | 수식·가중치 표 | 일부 유지. 실제 구현 프리셋/퍼널 중심으로 재배치 |
| §04 Architecture & Reliability | 아키텍처 다이어그램, ERD | 별도 섹션으로 유지하지 않음. 필요한 기술 구조만 §03 Simulator / §04 Ranking 안에 흡수 |
| §05 Collaborative Framework | "기획자가 수식을 설계한다" 비약 전체 | **삭제 후 새 §05 AI Experiment Design으로 교체** |
| §06 Evaluation Design | Claude가 삽입한 논문식 평가 설계 | **삭제 후 실험 설정/수치 근거 섹션으로 교체** |

---

## B-2. Hero 전면 교체

### 현재 문제

현재 Hero는 "기획자가 직접 수식을 설계"를 첫 메시지로 둔다.
게임 AI/모델 직무 실무자에게는 협업 서사보다 simulation, synthetic data, policy experiment가 먼저 보여야 한다.

### 교체 문장

```text
Synthetic User Simulator for AI Book Recommendation

초기 사용자 데이터가 부족한 추천 시스템에서
가상 유저 state를 만들고, 실제 도서 corpus 위에서 행동 event를 생성해,
랭킹 정책과 모델 후보 압축을 실험한 AI 시뮬레이션 포트폴리오.
```

### Hero stat card 교체

| 수치 | 라벨 | 하위 설명 |
|---|---|---|
| `1M` | Persona Source Pool | Nemotron-Personas-Korea 원천 pool |
| `1,000` | Persona Experiment Subset | stable persona_id로 저장한 실험 대상 |
| `28 → 12` | Persona Profile Compression | raw persona fields → reading profile schema |
| `63K` | Synthetic Events | 1,000 personas × 63 events |
| `100 → 50 → 20 → 5` | Ranking Funnel | Qdrant → Rule → LightFM/Profile → Final |

### Hero에서 삭제할 표현

- "기획자가 직접 수식을 설계한"
- "협업 브릿지"
- "해석 비용 0"
- "≤5s 추천 응답 목표" 단독 강조. 실측값이 아니므로 Hero 핵심 수치에서 제외.

---

## B-3. §01 전면 재편 — "Why This System"

**목표:** 추상적 카드 3개를 걷어내고, 데이터 수집 → cold start 해소 → 랭킹 정책 실험이라는 문제 흐름을 도입부에 배치한다.

**섹션 제목 교체:** `"Vision & Hook"` → `"왜 이 구조가 필요했나"`

#### 블록 A — 3단계 문제-해결 흐름

컴포넌트: `.problem` × 3 또는 `.pipeline-flow`

```text
[문제 1] AI 추천은 사용자 행동 데이터가 있어야 개인화된다
          그런데 초기 유저는 행동 데이터를 남기기 전에 이탈한다
          ↓
[해결 1] 북켓몬 행동 루프
          추천받은 책을 읽고, 기록하고, 리뷰하면 경험치를 얻는다
          리텐션 장치가 곧 행동 데이터 수집 장치가 된다

[문제 2] 서비스 오픈 전 real interaction이 0이다
          LightFM은 user-item interaction 없이 학습할 수 없다
          ↓
[해결 2] Nvidia Nemotron 기반 synthetic user simulator
          persona를 초기 user state로 가공하고,
          실제 Qdrant 도서 corpus 위에서 synthetic event를 생성한다

[문제 3] 벡터 검색 후보 100개를 최종 5개로 줄이는 정책이 필요하다
          ↓
[해결 3] Ranking policy experiment framework
          Qdrant 100 → Rule 50 → LightFM/Profile 20 → ScoreFusion → Final 5
```

#### 블록 B — 한 줄 요약 callout

컴포넌트: `.callout.info`

```text
"이 프로젝트의 핵심은 추천 UI가 아니라,
초기 데이터가 부족한 AI 시스템에서 user state를 만들고,
action/reward/policy를 분리해 offline으로 랭킹 정책을 실험한 구조입니다."
```

---

## B-4. §02 재정의 — "Retention as Data Collection Loop"

**현재 문제:** §02가 북켓몬 게임 메커니즘 설명에 그치고, "왜 게임 요소가 AI 모델 포트폴리오에 있는가"를 설명하지 않는다.

**섹션 제목 교체:** `"Product Mechanism · Gamification"` → `"Retention as Data Collection Loop"`

**추가할 도입 callout:**

```text
"북켓몬은 메인 서사가 아니라 AI 추천 시스템의 행동 데이터 수집 루프입니다.
사용자는 추천받은 책을 읽고 기록하면 경험치를 얻고,
시스템은 그 행동을 FAVORITE_ADD, READING_ADD, READ_ADD, RATING_ADD, REVIEW_ADD 같은
학습/랭킹 신호로 저장합니다."
```

**섹션 말미에 추가할 연결 문장:**

```text
이 live behavior loop에서 쌓이는 real interaction event와,
Nemotron simulator가 생성한 synthetic interaction event는 같은 학습 이벤트 형식으로 합류합니다.
서비스 초기에는 PERSONA_ONLY로 bootstrap하고,
real event가 쌓이면 HYBRID_LITE를 거쳐 REAL_ONLY로 전환할 수 있게 설계했습니다.
```

**유지할 내용:**
- XP 테이블
- 진화 타임라인
- 독서대 제한 / 리뷰 잠금 같은 참여 유도 장치

**수정할 관점:**
- XP/진화는 "게임 완성도"보다 "지속적인 interaction 수집 장치"로 설명
- "책을 추천받고 → 읽고 → 경험치를 얻고 → 다시 추천받는다" 순환 구조를 전면에 둠
- `UserCharacterEntity.java`가 XP가 아닌 `reviewGrowthCount` 기반으로 동작한다는 spec-impl gap은 유지
- XP 수치가 현재 코드로 확인되지 않는 경우, `설계값`으로 표기하거나 정확한 수치를 제거
- `SELECT FOR UPDATE + GREATEST()`는 구현 완료처럼 말하지 말고 명세/정합 예정으로 표기

---

## B-5. 신규 §03 — "Synthetic User Simulator"

`claude.html`에는 이 섹션이 반드시 새로 들어가야 한다.
게임 AI/모델 직무 타겟에서는 이 섹션이 가장 중요하다.

### 섹션 목표

Nvidia Dataset 가공 과정이 시뮬레이션과 어떻게 이어지는지 명확히 보여준다.
단, dataset을 실제 행동 로그처럼 포장하지 않는다.

### 도입 문장

```text
Nvidia Nemotron-Personas-Korea는 행동 로그가 아니라 가상 사용자 state의 원천입니다.
북켓몬은 이 persona pool을 독서 성향 profile로 압축하고,
실제 도서 corpus 안에서 action별 후보를 검색해 synthetic interaction event를 생성했습니다.
```

### 파이프라인

컴포넌트: `.pipeline-flow`

```text
Nvidia Nemotron-Personas-Korea
1M rows · 28 fields
        ↓
create_persona_subset.py
streaming load · shuffle · stable persona_id · local JSONL
        ↓
enrich_nemotron_persona_profiles.py
CLOVA HCX-007 · 12-field reading profile
        ↓
generate_nemotron_profile_synthetic_events.py
action-specific search text · KURE embedding · Qdrant books_kure
        ↓
generate_nemotron_rule_based_synthetic_events.py
ProfileReranker teacher · rule score 재정렬
        ↓
train_lightfm.py
LightFM WARP 학습 · candidate 50 → 20 압축기
```

### State / Action / Reward / Policy 표

컴포넌트: `.tableWrap`

| RL-style 구성요소 | 이 프로젝트의 대응 | 근거 |
|---|---|---|
| State | persona_fields + LLM reading profile | 28 raw fields → 12 profile fields |
| Action | FAVORITE_ADD, READING_ADD, READ_ADD, RATING_ADD, REVIEW_ADD, DISLIKE_ADD | synthetic event generator |
| Reward proxy | event weight, real_weight_multiplier, dislike exclusion | LightFM training weight. RL 보상이 아니라 offline 학습용 proxy reward |
| Environment | Qdrant `books_kure` 실제 도서 corpus | LLM이 책을 생성하지 않도록 제한 |
| Policy / Teacher | ProfileReranker, Rule stage, ScoreFusion | synthetic 후보 재점수화 및 final ranking |
| Replay / Training | LightFM WARP artifact | offline candidate compressor |

### Dataset 가공 수치

| 수치 | 의미 |
|---|---|
| `1M rows` | Nemotron-Personas-Korea 원천 persona pool |
| `28 fields` | 원본 persona state 구성 |
| `12 fields` | LLM reading profile schema |
| `8 text fields` | action별 Qdrant 검색 쿼리 |
| `4 numeric fields` | rating/review/exploration/confidence bias |
| `1,000 personas × 63 events` | 기본 synthetic event 규모 |
| `63,000 events` | 1,000명 기준 생성량 |

### 설계 제약 callout

컴포넌트: `.callout.warn`

```text
"LLM은 책 제목, ISBN, 출판사를 직접 생성하지 않습니다.
모든 후보 도서는 Qdrant books_kure 컬렉션에 존재하는 실제 도서 payload에서만 가져옵니다.
따라서 이 파이프라인은 persona hallucination이 아니라
실제 corpus 위에서 synthetic interaction을 만드는 구조입니다."
```

---

## B-6. 신규 §04 — "Ranking Policy Experiment Framework"

기존 §03 Core Engine은 수식보다 실제 후보 축소 퍼널과 실험 변수를 중심으로 재배치한다.

### 섹션 도입 문장

```text
LightFM은 최종 Top-5 생성기가 아니라,
Qdrant/Rule이 만든 후보를 50개에서 20개로 줄이는 candidate compressor입니다.
최종 노출 순위는 GTE reranker와 ScoreFusion, final stage에서 결정됩니다.
```

### 핵심 퍼널

```text
Qdrant 100
→ Rule filter 50
→ LightFM/Profile 20
→ GTE/ScoreFusion
→ Final 5
```

### 실험 변수 표

| 실험 변수 | 값 |
|---|---|
| `training_mode` | `PERSONA_ONLY`, `HYBRID_LITE`, `REAL_ONLY` |
| `synthetic_max_ratio` | `0.5` default |
| `real_weight_multiplier` | `2.0` |
| `LightFM loss` | `warp` |
| `components` | `32` |
| `learning_rate` | `0.03` |
| `candidate_eval_pool_size` | `50` |
| `candidate_eval_top_k` | `20` |
| 구현 확인 fallback | `LIGHTFM_DISABLED`, `MISSING_USER_ID`, `EMPTY_CANDIDATES`, `ARTIFACT_LOAD_FAILED`, `UNKNOWN_USER`, `NO_KNOWN_ITEMS`, `NUMPY_IMPORT_FAILED`, `PREDICT_FAILED` |
| 문서 계약 fallback | `INSUFFICIENT_KNOWN_ITEMS`는 artifact contract 문서에 있는 기준으로만 표기 |

### Shared pool 실험 설명

컴포넌트: `.callout.info`

```text
"초기 synthetic event를 persona별로 완전히 독립 생성하면,
사용자 간 item overlap이 부족해 collaborative filtering이 관계를 학습하기 어렵습니다.
shared pool 실험에서는 개인 후보 70%, 같은 age/profile bucket 그룹 후보 25%,
전역 공유 후보 5%를 섞어 비슷한 사용자끼리 일부 도서를 공유하게 만들었습니다."
```

기존 문장처럼 아래 내용만 단독으로 쓰면 맥락이 약하다.

```text
"초기 synthetic event는 persona별 후보가 지나치게 고립되어
협업 필터링이 사용자 간 관계를 학습하기 어려웠습니다.
shared pool 실험에서는 개인 후보 70%, 같은 age/profile bucket 그룹 후보 25%,
전역 공유 후보 5%를 섞어 비슷한 사용자끼리 일부 도서를 공유하게 만들었습니다."
```

### 넣을 수 있는 실험 기준값

아래 값은 `README_nemotron_rule_based_shared_pool_synthetic_events.md`의 판단 기준으로 사용한다.
실측 결과로 단정하지 말고 "기존 identity-only final 기준"이라고 표기한다.

| 지표 | 기준값 |
|---|---|
| `TEST auc` | `~= 0.785` |
| `TEST positive_hit_rate@10` | `~= 0.320` |
| `TEST positive_precision@10` | `~= 0.0273` |
| `TEST positive_recall@10` | `~= 0.06825` |
| `TEST dislike_hit_rate@10` | `~= 0.003` |

### 평가 지표를 질문과 연결

수치만 나열하면 실험이 아니라 대시보드처럼 보인다.
각 지표가 답하는 질문을 같이 제시한다.

| 질문 | 지표 |
|---|---|
| 모델이 positive item을 구분하는가? | `TEST auc` |
| Top-10 안에 positive가 들어오는가? | `positive_hit_rate@10` |
| 추천 리스트가 얼마나 낭비 없이 맞는가? | `positive_precision@10` |
| 전체 positive 중 얼마나 회수하는가? | `positive_recall@10` |
| 싫어한 책을 얼마나 피하는가? | `dislike_hit_rate@10` |

---

## B-7. 신규 §05 — "AI Experiment Design 역량 매핑"

기존 `Collaborative Framework`는 삭제하고 이 섹션으로 교체한다.
문장으로 "저는 이런 역량이 있습니다"라고 직접 말하지 말고, 구조 대응표로 보여준다.

| 게임 AI/모델 직무 역량 | 북켓몬 구현 구조 |
|---|---|
| 시뮬레이터 환경 구성 | persona state, action event, reward weight, Qdrant environment 구성 |
| 실험 설계 | Tier 1/2/3 synthetic generation, shared pool ratio, training mode 비교 |
| 밸런스 테스트 자동화 | event weight, reward proxy multiplier, fallback threshold, ranking funnel 조정 |
| offline replay | synthetic/real event JSONL을 LightFM 학습과 평가에 반복 투입 |
| policy validation | ProfileReranker teacher, ScoreFusion, fallback reason logging |

---

## B-8. §06 삭제 후 "Boundaries"로 교체

Claude가 만든 기존 `Evaluation Design`은 삭제한다.
대신 구현 경계를 명확히 밝히는 섹션을 둔다.

### 삭제 이유

- Precision@K, Recall@K, NDCG 등 표는 실행 결과가 아니라 논문식 계획처럼 보임
- RQ1~RQ5는 실제 A/B 테스트나 사용자 실험으로 검증되지 않음
- "12개 persona × 30 query" 식 pass criteria는 현재 핵심 실험 구조와 맞지 않음

### 대체 섹션 내용

```text
What this is
- RL-style offline simulator/replay framework
- synthetic user state와 real book corpus 기반 interaction generator
- LightFM candidate compressor와 ranking policy experiment 구조

What this is not
- PPO/DQN/SAC 같은 강화학습 알고리즘 학습 사례 아님
- 실제 사용자 행동 로그를 Nvidia Dataset으로 대체한 것 아님
- LLM이 임의로 만든 책을 추천한 것 아님
- 운영 A/B 테스트 결과 아님
```

### 초반 boundary callout

마지막 §06까지 가기 전에 Hero 또는 §01 하단에 짧은 boundary를 한 번 먼저 둔다.
그래야 RL-style 표현이 과장으로 읽히지 않는다.

```text
Note: PPO/DQN/SAC을 학습한 사례가 아니라,
state/action/reward proxy/policy를 분리한 offline simulator/replay framework입니다.
```

---

## B-9. 최신 `claude.html` 오류 수정 목록

**오류 1 — ScoreFusion 수식이 실제 구현과 다름**

현재 `claude.html`은 아래처럼 ScoreFusion을 설명한다.

```text
final_score = w₁·S_personal + w₂·S_pop + w₃·S_recency
S_pop = log(loan_count + 1) / log(max_loan + 1)
S_recency = exp(−0.001 · days_since_publication)
```

이 수식은 현재 실제 구현과 다르다.
`score_fusion_service.py`는 요청 단위로 아래 4개 점수를 min-max normalize한 뒤 가중합한다.

```text
finalScore =
  w_qdrant          · normalize(qdrantScore)
+ w_rule            · normalize(ruleScore / preScore)
+ w_personalization · normalize(lightfmScore / profileVectorScore / ...)
+ w_reranker        · normalize(rerankerScore)
```

가중치는 guest 여부, personalization 가능 여부, reranker 가능 여부에 따라 달라진다.

| 상태 | 실제 가중치 예시 |
|---|---|
| guest + reranker available | reranker 0.60 / qdrant 0.30 / rule 0.10 / personalization 0.0 |
| user + personalization + reranker available | reranker 0.40 / personalization 0.25 / rule 0.25 / qdrant 0.10 |
| user + personalization + no reranker | personalization 0.40 / rule 0.40 / qdrant 0.20 |

따라서 `S_pop`, `S_recency`, `loan_count`, `days_since_publication`은 `claude.html`에서 제거한다.
대중성/신간성 점수는 현재 포트폴리오의 핵심 근거로 쓰지 않는다.

**오류 2 — Hero의 1M 표현**

| 현재 표현 | 문제 | 수정 후 |
|---|---|---|
| `Nvidia Nemotron 1M 페르소나를 가공` | 1M 전체를 처리한 것처럼 보임 | `1M source pool에서 1,000 persona subset을 만들고` |
| `Nemotron 1M → 서브셋` | 중간 규모가 불명확함 | `Nemotron 1M source pool → 1,000 persona subset → 63K events` |

**오류 3 — Hero stat의 Ranking Funnel 축약**

| 현재 표현 | 문제 | 수정 후 |
|---|---|---|
| `100 → 5` | 다단 실험 구조가 약해짐 | `100 → 50 → 20 → 5` |
| `Qdrant → Rule → LightFM → Final` | ScoreFusion/GTE와 50/20 단계가 흐려짐 | `Qdrant 100 → Rule 50 → LightFM/Profile 20 → ScoreFusion/GTE → Final 5` |

**오류 4 — XP/진화 구현 단정**

| 현재 표현 | 문제 | 수정 후 |
|---|---|---|
| XP table의 `+30`, `+40` 등 | 현재 구현 근거가 약함 | `설계값`으로 표시하거나 수치 제거 |
| `SELECT FOR UPDATE + GREATEST() 계약으로 강제` | 구현 완료처럼 읽힘 | `명세상 목표이며, 현재 구현과 정합 필요` |
| `users.current_stage` 단조 증가 코드 계약 | 바로 아래 spec-impl gap과 충돌 | callout을 `설계 명세`로 변경 |

**오류 5 — fallback reason 범위**

| 현재 표현 | 문제 | 수정 후 |
|---|---|---|
| `INSUFFICIENT_KNOWN_ITEMS`를 구현 fallback처럼 표기 | 현재 `lightfm_ranker.py` 직접 구현에서는 확인되지 않음 | 구현 확인 fallback과 artifact contract 문서 fallback을 분리 |
| `interaction 5건 미만이면 LightFM을 건너뛰고...` | 현재 ranker 코드 기준으로 단정하기 어려움 | `artifact contract 기준으로는 known item 부족 시 fallback하도록 설계했다` |

**오류 6 — 실험 결과처럼 들리는 장애/품질 문장**

| 현재 표현 | 문제 | 수정 후 |
|---|---|---|
| `semantic signal을 오염시켜 정렬 품질이 떨어졌다` | 측정 결과처럼 단정됨 | `semantic signal을 오염시킬 위험이 있어 분리했다` |
| `GTE reranker timeout 시 전체 추천 응답이 실패했다` | 실제 장애 사례처럼 단정됨 | `GTE timeout 가능성에 대비해 fail-open 정책을 선택했다` |

**오류 7 — 실제 파일/구조 불일치**

| 현재 Claude 문서 | 수정 방향 |
|---|---|
| `Next.js 14`, `JWT`, `xp_engine.java`, `gacha.py`, `social.py` 등 | 실제 프로젝트 기준 React/Vite, Spring Session/CSRF, FastAPI service package, LightFM/Qdrant/GTE 중심으로 정리 |
| `admin 콘솔에서 즉시 토글` | 구현되지 않은 기능이므로 삭제 |
| `수식이 곧 명세`, `해석 비용 0` | 삭제 |

---

## B-10. 최종 섹션 구조

```text
Hero  Synthetic User Simulator for AI Book Recommendation
§01   왜 이 구조가 필요했나
§02   Retention as Data Collection Loop
§03   Synthetic User Simulator
§04   Ranking Policy Experiment Framework
§05   AI Experiment Design 역량 매핑
§06   Boundaries: 구현한 것과 아닌 것
```

---

## B-11. Claude에게 한 번에 줄 최종 피드백 지시문

아래 지시문을 그대로 전달한다.

```text
현재 claude.html은 방향성은 맞지만, 아직 실제 구현과 다른 기술 서사가 섞여 있어
실무자 포트폴리오 기준으로 신뢰도가 떨어진다.
더 화려하게 만들지 말고, 근거 없는 주장과 구현 불일치를 걷어내라.

1. Hero의 핵심 포지션은 유지한다.
   "Synthetic User Simulator × Ranking Policy Experiment" 방향은 맞다.
   다만 "Nvidia Nemotron 1M 페르소나를 가공"은 1M 전체를 처리한 것처럼 보이므로
   "1M source pool에서 1,000 persona subset을 만들고, 63K synthetic events를 생성"으로 바꿔라.

2. Hero stat의 Ranking Funnel은 "100 → 5"로 축약하지 마라.
   반드시 "100 → 50 → 20 → 5"로 보여줘라.
   하위 설명은 "Qdrant 100 → Rule 50 → LightFM/Profile 20 → ScoreFusion/GTE → Final 5"로 쓴다.

3. ScoreFusion 수식은 전면 교체한다.
   S_pop, S_recency, loan_count, days_since_publication 수식은 현재 실제 구현과 다르므로 삭제한다.
   실제 구현 기준으로 qdrant / rule / personalization / reranker 점수를 요청 단위로 정규화하고,
   guest 여부, personalization 가능 여부, reranker 가능 여부에 따라 가중합한다고 설명하라.

4. XP/진화 섹션은 행동 데이터 수집 루프라는 관점은 유지하되,
   코드로 확인되지 않는 XP 수치는 "설계값"으로 표시하거나 제거하라.
   SELECT FOR UPDATE + GREATEST()는 구현 완료처럼 쓰지 말고
   "명세상 목표이며 현재 구현과 정합 필요"로 낮춰라.

5. LightFM fallback은 구현 확인 범위와 문서 계약 범위를 분리하라.
   구현에서 직접 확인되는 fallback은 LIGHTFM_DISABLED, MISSING_USER_ID, EMPTY_CANDIDATES,
   ARTIFACT_LOAD_FAILED, UNKNOWN_USER, NO_KNOWN_ITEMS, NUMPY_IMPORT_FAILED, PREDICT_FAILED다.
   INSUFFICIENT_KNOWN_ITEMS는 artifact contract 문서 기준으로만 언급하라.

6. GTE 관련 문제 해결 사례는 측정 결과처럼 단정하지 마라.
   "정렬 품질이 떨어졌다" 대신 "semantic signal을 오염시킬 위험이 있어 분리했다"로 쓰고,
   "timeout으로 전체 응답이 실패했다" 대신 "timeout 가능성에 대비해 fail-open 정책을 선택했다"로 쓴다.

7. 강화학습 표현은 현재 수준을 유지한다.
   PPO/DQN/SAC을 학습한 사례가 아니므로 "강화학습 기반 모델"이라고 쓰지 않는다.
   "RL-style offline simulator/replay framework" 또는 "강화학습형 실험 구조"까지만 쓴다.

8. 삭제할 표현:
   - 기획자가 직접 수식을 설계
   - 해석 비용 0
   - admin 콘솔에서 즉시 토글
   - Nvidia 데이터셋으로 실제 사용자 행동을 확보
   - 강화학습 모델을 학습
   - 페르소나가 책을 직접 선택

9. 최종 문서의 중심은 북 추천 서비스 소개가 아니라,
   초기 데이터 부족 상황에서 persona state, action, reward, environment, policy를 분리해
   추천 정책을 offline으로 실험할 수 있게 만든 AI 시뮬레이터 설계여야 한다.

10. 북켓몬 리텐션 루프와 Nemotron simulator가 따로 놀지 않게 연결하라.
    real interaction event를 만드는 live behavior loop와
    synthetic interaction event를 만드는 offline simulation loop가
    같은 event schema로 합류하고,
    PERSONA_ONLY → HYBRID_LITE → REAL_ONLY 전환 전략으로 이어진다는 점을
    §01 또는 §02 끝에 명시하라.

11. 책 추천 도메인이 왜 게임 AI/모델 직무 포트폴리오가 되는지 설명하라.
    도메인은 책 추천이지만, 보여주는 역량은 player/user model,
    action space, reward proxy, offline replay, policy comparison 설계라고 명시하라.

12. shared pool, LightFM, GTE/ScoreFusion은 각각 역할을 분리해 설명하라.
    shared pool은 collaborative filtering을 위해 item overlap을 만드는 실험이고,
    LightFM은 최종 생성기가 아니라 50 → 20 candidate compressor이며,
    GTE는 semantic reranker, ScoreFusion은 점수 결합기다.
```

---

# 작업 상태

## ai book curation.html

- [x] Nemotron 파이프라인 구조 파악 완료
- [x] LightFM 학습 실험 구조 파악 완료
- [x] Nvidia Persona Dataset 가공과 simulator 연결성 검토 반영
- [x] HTML 작업 명세 완성 (작업 A-1, A-2, A-3)
- [ ] [작업 A-1] §14 페르소나: 3-tier 블록 4개 추가
- [ ] [작업 A-2] §13 LightFM: training mode 블록 3개 추가
- [ ] [작업 A-3] §17 문제 해결: 케이스 재편 + 사례 9 추가

## claude.html

- [x] 전체 섹션 구조 및 비약 전수 조사 완료
- [x] 핵심 서사 흐름 정의 완료
- [x] 게임 AI/모델 직무 타겟으로 포지셔닝 재정의
- [x] RL 표현 수위와 boundary 문구 반영
- [x] HTML 작업 명세 재작성 (작업 B-1 ~ B-10)
- [x] 최신 Claude 산출물 재점검 완료
- [x] ScoreFusion / XP / fallback / 1M 처리 범위 오류 수정 지시 반영
- [x] Claude에게 한 번에 전달할 최종 피드백 지시문 작성
- [x] 논리 연결 추가 점검 및 보강 지시 반영
- [ ] [작업 B-1] Hero 교체 — Synthetic User Simulator 포지션
- [ ] [작업 B-2] §01 전면 재편 — "왜 이 구조가 필요했나"
- [ ] [작업 B-3] §02 재정의 — Retention as Data Collection Loop
- [ ] [작업 B-4] §03 신규 작성 — Synthetic User Simulator
- [ ] [작업 B-5] §04 신규 작성 — Ranking Policy Experiment Framework
- [ ] [작업 B-6] §05 교체 — AI Experiment Design 역량 매핑
- [ ] [작업 B-7] §06 교체 — Boundaries

---

# 관련 파일

| 파일 | 역할 |
|---|---|
| `script/create_persona_subset.py` | Nemotron 서브셋 로컬 JSONL 저장 |
| `script/enrich_nemotron_persona_profiles.py` | 페르소나 → CLOVA HCX-007 → 12-field reading profile |
| `script/generate_nemotron_persona_synthetic_events.py` | Tier 1: 페르소나 필드 직접 임베딩 → 이벤트 생성 |
| `script/generate_nemotron_profile_synthetic_events.py` | Tier 2: LLM 프로파일 기반 행동 유형별 이벤트 생성 |
| `script/generate_nemotron_rule_based_synthetic_events.py` | Tier 3: production ProfileReranker teacher 기반 재점수화 |
| `script/train_lightfm.py` | LightFM 학습 (training mode / ratio / weight 실험) |
| `script/prompts/nemotron_persona_reading_profile_system.v1.ko.md` | LLM 시스템 프롬프트 (출력 스키마 + 제약 정의) |
| `script/prompts/nemotron_persona_reading_profile_user.v1.ko.md` | LLM 유저 프롬프트 ({{PERSONA_JSON}} 주입) |
