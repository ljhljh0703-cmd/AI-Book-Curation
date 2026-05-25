# Claude HTML 문장 다듬기 피드백

> 대상 파일: `portfolio/claude.html`  
> 목적: 내용 구조를 유지한 상태에서 번역투, 과한 단정, 비약, 논리 연결 부족을 줄이는 문장 개선 지시문  
> 작성일: 2026-05-23

---

## 1. 작업 원칙

`claude.html`의 현재 방향성은 유지한다.
다만 문장이 번역투처럼 보이거나, 실제 구현보다 강하게 말하거나, 섹션 간 연결이 약한 부분은 전부 낮춘다.

수정 우선순위는 아래 순서다.

1. 실제 구현과 다른 주장 제거
2. 운영 성과처럼 보이는 표현 제거
3. 강화학습 과장 제거
4. 문장 자연화
5. 섹션 간 논리 연결 보강

---

## 2. 문장 톤 기준

### 피해야 할 문장 톤

- 영어 직역처럼 보이는 문장
- “실험했다”, “검증했다”, “실패했다”, “품질이 떨어졌다”처럼 로그나 결과가 있어야만 가능한 단정
- “실서비스”, “운영”, “A/B”처럼 실제 운영 성과로 오해될 수 있는 표현
- “기획자가 직접 수식을 설계”, “해석 비용 0”처럼 역할을 과장하는 표현
- “강화학습 모델을 학습했다”처럼 RL 알고리즘 학습으로 읽히는 표현

### 선호하는 문장 톤

- “설계했다”
- “분리했다”
- “정리했다”
- “비교할 수 있게 만들었다”
- “위험이 있어 분리했다”
- “offline baseline reference로만 사용한다”
- “구현 완료가 아니라 설계 명세/정합 예정이다”

---

## 3. 핵심 표현 정리

| 피해야 할 표현 | 바꿀 표현 |
|---|---|
| `offline으로 실험` | `offline에서 실험` |
| `실서비스 기준` | `서비스 파이프라인 기준` |
| `정렬 품질이 떨어졌다` | `semantic signal을 오염시킬 위험이 있어 분리했다` |
| `GTE timeout으로 전체 응답이 실패했다` | `GTE timeout 가능성에 대비해 fail-open을 선택했다` |
| `정적인 상수 1조` | `하나의 고정 상수 세트` |
| `RPG 아이템이라고 가정하면` | `사용자 상태와 아이템 선택 구조로 전이 가능하다` |
| `역설계` | `악용 방지` |
| `Nvidia 1M 페르소나를 가공` | `1M source pool에서 1,000개 persona subset을 만들었다` |
| `강화학습 기반 모델` | `RL-style offline simulator/replay framework` |

---

## 4. 반드시 유지할 경계

아래 경계 문장은 유지하거나 더 명확히 해야 한다.

```text
본 프로젝트는 PPO·DQN·SAC 같은 강화학습 알고리즘을 학습한 사례가 아니다.
user state · action · reward proxy · policy를 분리해
offline에서 랭킹 정책을 실험할 수 있도록 만든
RL-style simulator/replay framework다.
```

```text
Nvidia Nemotron-Personas-Korea는 실제 사용자 행동 로그가 아니라
cold start bootstrap용 initial state distribution이다.
```

```text
LightFM은 최종 Top-5 생성기가 아니라
Qdrant/Rule 후보를 50개에서 20개로 줄이는 candidate compressor다.
```

---

## 5. 논리 연결 보강

현재 문서에서 가장 중요한 연결은 아래 두 루프의 합류다.

```text
Live Behavior Loop
추천 → 독서대 등록 → 리뷰/평점/찜/거부 → real interaction event

Offline Simulation Loop
persona state → action별 Qdrant 검색 → synthetic interaction event

두 루프는 같은 event schema로 합류하고,
PERSONA_ONLY → HYBRID_LITE → REAL_ONLY 전환 전략으로 이어진다.
```

이 연결이 약하면 북켓몬 XP/진화와 Nvidia simulator가 따로 노는 것처럼 보인다.
따라서 §02 말미 또는 §01 하단에 이 내용을 반드시 유지한다.

---

## 6. 심사관 관점 리스크

AI 직무 심사관은 아래 질문을 할 수 있다.

| 질문 | 방어 문장 |
|---|---|
| 강화학습이라면서 어떤 알고리즘을 학습했나요? | PPO/DQN/SAC을 학습한 사례가 아니라 RL-style offline simulator/replay framework입니다. |
| Nemotron persona가 실제 사용자를 대표하나요? | 대표성 주장이 아니라 cold start용 initial state distribution입니다. |
| 운영 A/B 결과가 있나요? | 운영 A/B가 아니라 offline baseline reference입니다. |
| 책 추천이 게임 AI와 무슨 관련인가요? | 도메인은 책 추천이지만, 구조는 user/player model, action space, reward proxy, offline replay, policy comparison 설계입니다. |
| LightFM이 최종 추천 모델인가요? | 최종 생성기가 아니라 50 → 20 candidate compressor입니다. |

---

## 7. 수정 예시

### Hero 문장

```text
nvidia/Nemotron-Personas-Korea 1M source pool에서 1,000개 persona subset을 만들고,
실제 Qdrant 도서 corpus 위에서 63K synthetic interaction event를 생성했다.
이를 LightFM 후보 압축과 랭킹 정책 실험에 사용한
RL-style simulator/replay framework다.
```

### GTE 사례

```text
GTE reranker 입력 문서에 qdrant/rule/lightfm 점수를 넣는 방안을 검토했다.
다만 이 방식은 reranker가 도서 텍스트가 아니라
사전 점수에 과도하게 반응할 위험이 있었다.
```

### 도메인 연결

```text
이 프로젝트의 도메인은 책 추천이지만,
보여주려는 역량은 player/user model · action space · reward proxy ·
offline replay · policy comparison 설계 경험이다.
도메인 객체가 책일 뿐, 구조적으로는 사용자 상태와 아이템 선택,
보상 신호, 정책 비교를 다루는 시뮬레이터·밸런스 실험에 가깝다.
```

---

## 8. 최종 체크리스트

- [ ] `S_pop`, `S_recency`, `loan_count`, `days_since_publication` 수식이 남아 있지 않은가?
- [ ] `1M 전체를 가공했다`처럼 읽히지 않는가?
- [ ] PPO/DQN/SAC 미학습 경계가 초반과 마지막에 모두 보이는가?
- [ ] XP 수치가 구현값처럼 보이지 않고 `설계값`으로 처리되어 있는가?
- [ ] `실패했다`, `품질이 떨어졌다` 같은 결과 단정이 남아 있지 않은가?
- [ ] `My Role`이 실제 본인 기여 범위를 넘지 않는가?
- [ ] 새 데이터 필드가 실제 랜딩페이지 렌더러에서 표시되는가?

---

## 9. 추가 고위험 피드백

아래 항목은 문장 다듬기보다 우선순위가 높다.
AI 직무 심사관이나 포트폴리오 리뷰어가 실제로 걸어볼 가능성이 큰 지점이다.

### 9-1. `claude.html`이 실제 HTML 랜딩페이지가 아니다

현재 `portfolio/claude.html`은 `<!doctype html>`, `<html>`, `<body>`, 렌더링 스크립트가 없는 `window.BK = {...}` 데이터 객체다.
즉 파일명을 `.html`로 열어도 시각적 랜딩페이지가 아니라 raw text처럼 보일 수 있다.

이 상태에서는 내용이 아무리 좋아도 포트폴리오로 전달되지 않는다.

반드시 둘 중 하나로 정리한다.

```text
Option A. claude.html을 진짜 standalone HTML로 만든다.
  - doctype/html/body 추가
  - window.BK 데이터를 렌더링하는 template 추가
  - initialBoundary, loopMerge, roleSplit, myRole 등 새 필드가 화면에 표시되는지 확인

Option B. 현재 파일을 data JS로 분리한다.
  - claude.html → 실제 화면 shell
  - claude-data.js → window.BK 데이터
  - HTML에서 <script src="claude-data.js"></script>로 로드
```

### 9-2. 새 필드가 렌더링되지 않을 수 있다

현재 데이터에는 아래 새 필드가 추가되어 있다.

```text
initialBoundary
mechanism.loopMerge
ranking.roleSplit
ranking.metricQuestions
experiment.myRole
boundaries.safeAnswer
```

하지만 렌더러가 이 키를 읽지 않으면 실제 화면에는 보이지 않는다.
특히 `initialBoundary`, `loopMerge`, `myRole`은 이번 리프레임의 핵심이므로 반드시 렌더링 확인이 필요하다.

최종 검수 기준:

```text
Hero 아래에 scope/boundary가 보이는가?
§02 끝에 live loop와 offline loop 합류 설명이 보이는가?
§04에서 GTE / ScoreFusion / LightFM 역할 분리가 보이는가?
§05에서 My Role이 보이는가?
마지막에 Scope & Limits가 보이는가?
```

### 9-3. 공개 포트폴리오와 제작자용 메모를 분리해야 한다

현재 `claude.html`에는 포트폴리오 본문에 적합하지 않은 내부 메타 표현이 섞여 있다.

| 현재 표현 | 문제 | 공개 페이지용 대체 |
|---|---|---|
| `표현 경계 (먼저)` | 제작자 메모처럼 보임 | `Scope` 또는 `Project Scope` |
| `심사관에게 가장 안전한 한 줄 답변` | 면접 대비 메모처럼 보임 | `Project Scope Summary` |
| `피해야 할 표현` | 내부 피드백 문서에 가까움 | 공개 페이지에서는 제거하거나 `Scope & Limits`로 흡수 |
| `What this is not` 과도한 나열 | 방어적으로 보일 수 있음 | 3~4개 핵심 경계만 남김 |

공개 랜딩페이지에는 “내가 어떤 말을 피해야 하는지”를 직접 보여주지 않는다.
그 내용은 이 피드백 문서나 작업 명세에 남기고, 실제 페이지에는 차분한 scope 문장으로만 반영한다.

### 9-4. 방어 문장이 너무 많으면 자신감이 약해 보인다

현재 방향은 안전하지만, `아님`, `단정하지 않는다`, `구현 단정 아님`, `정합 예정`이 너무 많이 보이면 포트폴리오가 방어 문서처럼 보일 수 있다.

권장 구조:

```text
Hero: 강점 제시
초반 Scope: RL 과장 방지 1문장
본문: simulator / ranking / data loop 중심
마지막 Scope & Limits: 핵심 한계 3~4개만 정리
```

피해야 할 구조:

```text
Hero부터 마지막까지 계속 "아님", "단정 아님", "정합 예정"을 반복
```

### 9-5. `My Role`이 너무 약하면 AI/모델 직무에서 손해다

현재 `My Role` caveat는 안전하지만, “구현 코드 작성·운영은 별도 팀 분담”이라는 문장이 너무 강하면 심사관이 이렇게 볼 수 있다.

```text
그러면 AI/model 실무 역량은 실제로 어디까지 했나요?
```

따라서 본인 기여 범위를 정확히 다시 나눠야 한다.

| 실제 기여 상황 | 문서화 방식 |
|---|---|
| 코드/스크립트도 직접 작성했다 | 담당 파일과 실험 산출물을 명확히 적는다 |
| 설계와 문서화가 중심이었다 | `AI experiment design / simulator design / technical planning` 포지션으로 명확히 둔다 |
| 구현은 팀원이 했다 | 구현했다고 쓰지 말고, 설계 의사결정과 검증 기준을 만든 역할로 둔다 |

현재 최종 타겟이 `게임 AI/모델 직무 실무자`라면, 단순 기획보다 아래 증거가 필요하다.

```text
내가 설계한 실험 변수가 무엇인지
내가 정의한 event schema가 무엇인지
내가 비교한 baseline이 무엇인지
내가 만든/검토한 artifact가 무엇인지
```

### 9-6. 결과보다 실험 설계가 강점이라는 점을 더 선명하게 해야 한다

이 포트폴리오는 “추천 성능을 크게 올렸다”로 말하면 약하다.
운영 A/B도 없고, persona 대표성도 제한적이기 때문이다.

강한 포지션은 아래다.

```text
데이터가 없는 초기 상태에서
user state, action, reward proxy, environment, policy를 분리하고,
synthetic event와 real event가 같은 학습 schema로 합류하게 만든
AI 실험 설계 사례.
```

따라서 성과 문장은 모델 성능보다 구조적 성과로 둔다.

```text
Before: real interaction 0건이라 모델 실험 불가
After: synthetic replay event로 candidate compression / ranking policy 실험 가능
```

### 9-7. 증거 링크가 부족하다

심사관은 “말은 좋은데 근거 파일은?”을 본다.
각 핵심 주장에는 최소 하나의 근거 파일을 붙이는 것이 좋다.

| 주장 | 근거 파일 |
|---|---|
| Persona subset 생성 | `script/create_persona_subset.py` |
| LLM reading profile 생성 | `script/enrich_nemotron_persona_profiles.py` |
| action별 synthetic event 생성 | `script/generate_nemotron_profile_synthetic_events.py` |
| rule teacher 재정렬 | `script/generate_nemotron_rule_based_synthetic_events.py` |
| LightFM 학습/혼합 전략 | `script/train_lightfm.py` |
| LightFM fallback | `apps/ai-server/app/services/ranking/lightfm_ranker.py` |
| ScoreFusion 실제 수식 | `apps/ai-server/app/services/recommendation/score_fusion_service.py` |

공개 페이지에서 모든 파일을 길게 설명할 필요는 없지만, `Evidence` 또는 `Key Files` 형태로 짧게 노출하면 신뢰도가 올라간다.

### 9-8. 최종 페이지 구조 제안

현재 내용을 모두 보여주면 길고 방어적이다.
공개 랜딩페이지는 아래 7블록 정도가 적당하다.

```text
Hero
Scope note
01 Problem: real interaction 0건
02 Data Loop: live behavior loop + offline simulation loop
03 Simulator: Nemotron → profile → Qdrant → synthetic event
04 Ranking Policy: 100 → 50 → 20 → 5
05 My Role + Evidence
06 Scope & Limits
```

`avoidTable`, `safeAnswer`, 상세 fallback reason 전체 목록은 공개 페이지 본문보다 appendix나 제작자 문서에 두는 편이 낫다.

---

## 10. 긴 기술 내용은 접이식 패널로 분리

수식, fallback reason, 세부 파이프라인, 근거 파일 목록은 중요한 내용이지만 본문에 전부 펼치면 페이지가 무거워진다.
따라서 공개 랜딩페이지는 요약을 먼저 보여주고, 세부 내용은 사용자가 눌렀을 때 열리도록 구성한다.

권장 UI는 HTML 기본 `<details><summary>` 또는 기존 디자인 시스템에 맞춘 accordion이다.
JavaScript 없이도 동작해야 하므로 `<details>`를 우선 사용한다.

### 10-1. 기본 패턴

```html
<details class="detail-panel">
  <summary>
    <span>ScoreFusion 실제 계산식 보기</span>
    <small>qdrant / rule / personalization / reranker normalized fusion</small>
  </summary>
  <div class="detail-body">
    <!-- 수식, 표, 코드, 근거 파일 -->
  </div>
</details>
```

### 10-2. 접이식으로 넣을 항목

| 본문에 짧게 보여줄 내용 | 접이식 패널에 넣을 세부 내용 |
|---|---|
| `ScoreFusion은 4개 점수를 정규화해 결합한다` | 실제 formula, weight preset, guest/user/reranker 조건별 가중치 |
| `Nemotron → profile → event 생성` | 3-tier synthetic generation pipeline, profile 12 fields, Mermaid/flowchart |
| `LightFM은 50 → 20 candidate compressor` | training mode, synthetic ratio 공식, event weight, fallback reason |
| `shared pool로 CF item overlap을 만든다` | 70/25/5 비율, 왜 overlap이 필요한지, baseline reference |
| `GTE는 semantic reranker다` | GTE 입력에서 숫자 점수를 제외한 이유, timeout fail-open 설계 |
| `My Role` | 담당 범위, 핵심 의사결정, evidence files |
| `Scope & Limits` | PPO/DQN/SAC 미학습, Nvidia 대표성 한계, 운영 A/B 아님 |

### 10-3. 섹션별 accordion 배치안

```text
Hero
  - 펼침 없음. 짧고 강하게.

Scope note
  - 펼침 없음. RL 과장 방지 1문장만.

01 Problem
  - 펼침 없음. real interaction 0건 문제만 명확히.

02 Data Loop
  - Accordion: Live behavior loop event schema
  - Accordion: Offline simulation loop event schema

03 Simulator
  - Accordion: 3-tier synthetic generation
  - Accordion: 12-field reading profile schema
  - Accordion: Qdrant hallucination guard

04 Ranking Policy
  - Accordion: ScoreFusion formula
  - Accordion: LightFM training modes
  - Accordion: Fallback reasons
  - Accordion: Shared pool experiment

05 My Role + Evidence
  - Accordion: Key files and evidence

06 Scope & Limits
  - Accordion: Detailed limitations
```

### 10-4. 공개 본문과 펼침 패널의 문장 차이

본문은 결론만 말한다.

```text
LightFM은 최종 생성기가 아니라 50개 후보를 20개로 줄이는 candidate compressor입니다.
```

펼침 패널은 근거를 보여준다.

```text
LIGHTFM_TOP_N=20
LIGHTFM_CANDIDATE_LIMIT=50
training_mode: PERSONA_ONLY / HYBRID_LITE / REAL_ONLY
synthetic_max_ratio=0.5
real_weight_multiplier=2.0
```

### 10-5. 너무 많은 accordion을 피하는 기준

모든 카드에 펼침을 붙이면 사용자가 길을 잃는다.
아래 기준을 만족하는 내용만 접이식으로 보낸다.

- 수식 또는 코드가 들어간다
- 표가 5행 이상이다
- 근거 파일 목록이 들어간다
- 읽지 않아도 핵심 이해에는 문제가 없지만, 읽으면 신뢰도가 올라간다
- 면접 질문이 들어왔을 때 방어 근거가 되는 내용이다

### 10-6. 렌더링 필드 제안

`window.BK` 데이터 구조에 접이식 내용을 넣으려면 아래처럼 명시적으로 `details` 필드를 둔다.

```js
ranking: {
  summary: "...",
  details: [
    {
      title: "ScoreFusion 실제 계산식",
      subtitle: "score_fusion_service.py 기준",
      type: "formula",
      body: [...]
    },
    {
      title: "LightFM training mode",
      subtitle: "PERSONA_ONLY / HYBRID_LITE / REAL_ONLY",
      type: "table",
      rows: [...]
    }
  ]
}
```

렌더러는 `section.details`를 순회해 `<details>` 요소로 그린다.
이렇게 해야 긴 수식과 파이프라인을 충분히 넣으면서도 첫 화면의 밀도를 낮출 수 있다.

### 10-7. 최종 지시문

```text
긴 기술 내용은 본문에 모두 펼치지 마라.
본문은 문제, 결정, 결과만 보여주고,
수식·세부 파이프라인·fallback reason·근거 파일은
클릭하면 열리는 details/accordion 패널로 분리하라.

특히 ScoreFusion formula, LightFM training mode, synthetic generation 3-tier,
shared pool ratio, evidence files는 접이식으로 넣어라.
```
