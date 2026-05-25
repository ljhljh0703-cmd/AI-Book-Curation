# Opus Data Extraction Spec: Bookemon Product Deep-Dive Portfolio

> **목적**: '북켓몬' 서비스의 기획 서사와 기술적 아키텍처를 집대성한
> **단독 기술 포트폴리오(HTML)** 제작을 위한 데이터 정제 명세서.
> Opus는 이 명세서와 `bookemon-portfolio.md`(원본)를 함께 읽고,
> 아래 5개 모듈을 HTML 에셋 단위로 추출·정제한다.

---

## 🤖 [Prompt to Opus]

**System Role**:
당신은 하이엔드 테크니컬 라이터이자 프로덕트 아키텍트입니다.
'북켓몬'이라는 서비스의 **단독 웹 랜딩페이지(Product Deep-dive Portfolio)**를
구성하기 위해, 제공된 원본 마크다운을 분석하여
시각적·기술적 설득력이 극대화된 텍스트 에셋으로 정제하십시오.

**이것은 이력서의 일부가 아닙니다.**
하나의 완결된 **제품 소개서이자 기술 백서**입니다.

---

## 📐 HTML 레이아웃 & 디자인 원칙

### 전체 구조 (Single-Page Scroll)

```
[Nav]  북켓몬 · Vision · Mechanism · Engine · Architecture · Bridge
  ↓
[Section 0]  Hero — 3줄 포지셔닝 + 핵심 수치 4개 (stat cards)
[Section 1]  Vision & Hook
[Section 2]  Product Mechanism (Gamification)
[Section 3]  Core Engine (Re-ranking)
[Section 4]  Architecture & Reliability
[Section 5]  Collaborative Framework
[Section 6]  Evaluation Design
[Footer]
```

### 디자인 토큰

| 토큰 | 값 | 용도 |
|---|---|---|
| `--bg` | `#0d0d1a` | 페이지 배경 |
| `--bg2` | `#13132a` | 카드 배경 |
| `--bg3` | `#1a1a35` | 코드블록·테이블 헤더 |
| `--border` | `#2a2a50` | 카드·테이블 테두리 |
| `--accent` | `#7c6fff` | 포인트 컬러 (보라) |
| `--accent2` | `#a78bfa` | 서브 포인트 (라벤더) |
| `--accent3` | `#38bdf8` | 강조 컬러 (스카이블루) |
| `--green` | `#34d399` | 성공·긍정 수치 |
| `--orange` | `#fb923c` | 경고·주의 |
| `--text` | `#e2e8f0` | 본문 |
| `--text2` | `#94a3b8` | 보조 텍스트 |
| `--text3` | `#64748b` | 캡션·레이블 |

### 컴포넌트 패턴 (3축 카드 UI)

- **Stat Card**: 수치(큰 폰트 그라디언트) + 레이블(소문자). 4개 1행 그리드.
- **Feature Card**: 상단 아이콘/뱃지 + 제목(h3) + 본문 + 하단 코드/수식. 2열 또는 3열 그리드.
- **Timeline Step**: 번호 원형 도트(그라디언트) + 세로 연결선 + 제목 + 설명.
- **Formula Box**: 좌측 accent 컬러 border-left + 다크 배경 + monospace 수식. 변수는 `--accent2`, 계수는 `--orange`.
- **Callout Box**: border-left 3px + 반투명 배경. 색상으로 severity 구분(accent/green/orange/blue).
- **Collapsible**: `<details><summary>` 패턴. 상세 기술 내용은 기본 접힘.
- **Code Block**: `--code-bg(#0f172a)` + syntax highlight (키워드 purple, 함수 blue, 문자열 green, 주석 gray).
- **Badge Row**: pill 형태 inline badge. 스택/기술명 표기용.
- **Weight Bar**: label + 시각적 progress bar + 수치. 가중치 비교 시각화용.

---

## 📦 5개 추출 모듈 상세 명세

---

### Module 1 — Vision & Hook
> **HTML Section ID**: `#vision`
> **레이아웃**: Hero 바로 아래. 전폭(full-width) 서사 텍스트 + 3-card hook row.

**추출 지시**:

1. **Hook Headline** (h1 수준, 2줄 이내)
   - "단순 추천의 한계를 게임 산업의 문법으로 해결했다" 방향의 임팩트 문장으로 정제.
   - 한국어 본문, 영어 부제(subtitle) 병기.

2. **3-Card Hook Row** (각 카드당 텍스트 에셋)
   - Card A — **협업 브릿지**: "기획자가 직접 수식을 설계"한 핵심 서사. 1~2문장.
   - Card B — **리텐션 위기**: "추천 정확도 ≠ 재방문율"의 문제 정의. 1~2문장.
   - Card C — **다중 목표 최적화**: S_personal × S_pop × S_recency 파이프라인 한 줄 요약.

3. **Stat Cards** (4개, 수치 + 레이블)
   - `100K` / 도서 벡터 색인
   - `17` / RDB 테이블 설계
   - `36` / API 엔드포인트
   - `≤5s` / 추천 응답 목표

4. **포지셔닝 한 줄 문장** (hero sub-text)
   - 역할·스택·핵심 성과를 1문장으로 압축. (예: "기획 리드 · AI 파이프라인 설계 · FE/BE/AI 크로스팀 협업")

---

### Module 2 — Product Mechanism (Gamification)
> **HTML Section ID**: `#mechanism`
> **레이아웃**: 2열 Feature Card + Timeline Steps + 2열 설계 의도 카드.

**추출 지시**:

1. **섹션 리드 문장** (2~3문장)
   - "모든 독서 행동이 XP로 전환되고, XP가 북켓몬의 성장으로 가시화된다"는 핵심 원칙.
   - 다마고치 모델 이식의 설계 의도를 압축.

2. **XP 적립 구조 테이블** (추출 그대로 사용)
   - 행동 / XP / 일일 한도 / 설계 근거 4열.
   - `+100`, `+50`, `-100` 수치는 색상 구분 필요 (green/orange/red).

3. **진화 단계 Timeline** (Step 0~3, 4개)
   - 각 Step: 번호 + 단계명(한/영) + 조건 + 대사/설명 1줄.
   - Step 2에서 3개 장르 분기(2A/2B/2C) 인라인 badge로 표현.
   - Step 3 하이브리드 조건(`부 장르 비율 ≥ 40%`) 강조.

4. **설계 의도 카드 2개** (2열 grid)
   - Card: **독서대 3권 제한** — 문제 상황 vs. 설계 효과 대비.
   - Card: **리뷰 72시간 잠금** — 학습 데이터 품질 + 재방문 유도 이중 설계 의도.

5. **Callout**: 역행 금지 설계 (`current_stage` 절대 감소하지 않음, DB 트랜잭션 레벨 보장).

---

### Module 3 — Core Engine (Re-ranking)
> **HTML Section ID**: `#engine`
> **레이아웃**: Formula Box(수식) + 동적 가중치 2열 카드(Weight Bar) + 행동 신호 테이블 + Sequence Diagram.

**추출 지시**:

1. **섹션 리드 Callout** (blue, 2~3문장)
   - Dense 벡터 단독 추천의 한계(인기 편향, 시간 편향) → 3개 목표 함수 명시적 정의 → 동적 가중치 전환의 설계 의도.

2. **Formula Box — 수식 전체** (수학적 명세 수준)
   ```
   final_score = w₁ × S_personal + w₂ × S_pop + w₃ × S_recency

   S_personal  = 0.5 × S_vector   [Qdrant cosine similarity]
               + 0.3 × S_genre    [장르 선호도 일치율]
               + 0.2 × S_history  [행동 이력 가중 합산]

   S_pop       = log(loan_count + 1) / log(max_loan + 1)
               [도서관 대출 통계 Log 정규화 — 0~1 범위 보장]

   S_recency   = exp(−0.001 × days_since_publication)
               [출판일 기준 지수 감쇠 — 최신 도서 우대]

   memory_boost = × 1.2
               [user_principle 키워드 매칭 도서에 적용]
   ```
   - 각 변수에 **[출처/데이터 소스]** 주석 병기.
   - 계수(`0.5`, `0.3`, `0.2`, `0.001`, `1.2`)는 orange 색상.
   - 변수명(`S_personal` 등)은 accent2 색상.

3. **동적 가중치 전환 카드 2열**
   - Left Card: **Cold-start 유저** — 조건 + Weight Bar 3개 (`w₁=0.1`, `w₂=0.7`, `w₃=0.2`) + 설계 근거 callout(orange).
   - Right Card: **Warm 유저** — 조건 + Weight Bar 3개 (`w₁=0.5`, `w₂=0.3`, `w₃=0.2`) + 설계 근거 callout(green).
   - 전환 임계값: `대화 ≥ 20회 OR 등록 책 ≥ 3권` 강조 표시.

4. **행동 신호 가중치 테이블** (5행)
   - 행동 / 가중치 / 설계 근거.
   - 가중치 수치(1.0 ~ 3.5)는 accent 색상 code 태그.

5. **POST /chat 시퀀스 다이어그램** (Mermaid — collapsible)
   - 참여자: User → Spring Boot → profiler.py → llm_client.py(HCX) → vector_db.py(Qdrant) → reranker.py → library_api.py
   - 핵심 Note 3개: S_personal 계산식 / S_pop 계산식 / S_recency 계산식
   - 비동기 병렬 호출(LibAPI), 5s timeout fallback 명시.

6. **Redis 캐시 전략 테이블** (3행: 캐시 HIT / MISS / 장애)
   - 시나리오 / 흐름 / 응답 속도 (색상 구분).

---

### Module 4 — Architecture & Reliability
> **HTML Section ID**: `#architecture`
> **레이아웃**: 전체 아키텍처 Mermaid + 3-Layer 카드(3열) + ERD Mermaid(collapsible) + SQL 코드 블록.

**추출 지시**:

1. **섹션 리드 Callout** (2문장)
   - Spring Boot / FastAPI 분리 원칙 (레이어 분리 → 독립 롤링 업데이트 가능).
   - PostgreSQL · Qdrant · Redis 3-Layer 역할 분리 원칙.

2. **전체 아키텍처 Mermaid 다이어그램** (flowchart TD)
   - 6개 서브그래프: Auth Layer / API Layer / Service Layer / Core Layer / Data Layer / Batch Jobs
   - 컴포넌트 명칭은 실제 파일명(`profiler.py`, `xp_engine.py` 등) 그대로.
   - Qdrant Top-K 소셜 매칭 개선(`O(N²) → O(N×K)`) 노드 설명에 포함.

3. **3-Layer 데이터 전략 카드 (3열)**
   - **PostgreSQL**: 17개 테이블, PostGIS GEOGRAPHY, SELECT FOR UPDATE, INSERT ON CONFLICT UPDATE.
   - **Qdrant**: 벡터 차원 1,024, Cosine distance, book_vectors / user_vectors, O(N×K).
   - **Redis**: gacha_candidates TTL 6h, token_blacklist, 장애 시 Qdrant Fallback.

4. **ERD 다이어그램** (Mermaid erDiagram — collapsible)
   - 10개 테이블: users / books / reading_shelf / reviews / xp_transactions / friend_relationships / gacha_history / libraries / user_libraries / refresh_tokens
   - 각 테이블 핵심 컬럼(PK, FK, 특이 타입) 포함.
   - 관계선 (||--o{) 전부 포함.

5. **SELECT FOR UPDATE 코드 블록** (PostgreSQL — collapsible)
   - 전체 트랜잭션 흐름 4단계: 행 잠금 → 일일 한도 체크 → XP 갱신 + 진화 체크 → COMMIT.
   - syntax highlight: 키워드(purple) / 함수(blue) / 주석(gray) / 수치(orange).
   - 상단 Callout(orange): Lost Update 문제 상황 설명.
   - 하단 Callout(green): 진화 역행 금지 설계 설명.

6. **배치 파이프라인 Mermaid** (flowchart LR — collapsible)
   - 도서관정보나루 API → 중복 제거 → books upsert → 벡터 임베딩 → Qdrant upsert → 캐시 워밍 트리거.
   - 배치 스케줄 3종 명시: Weekly(도서 적재) / Daily 03:00(소셜 매칭) / Every 6h(캐시 워밍).

7. **Monorepo 구조 코드 블록** (tree 형식)
   - apps/ 5개 서버 + packages/ 2개 + database/ 구조.
   - 각 디렉토리에 한 줄 주석.

---

### Module 5 — Collaborative Framework
> **HTML Section ID**: `#bridge`
> **레이아웃**: 서사 리드 + 5-Step Timeline + 3-Effect Callout Row + 명세 테이블 + 크로스팀 카드(3열).

**추출 지시**:

1. **섹션 리드 문장** (2~3문장, 임팩트 최대화)
   - "기획자가 수식을 설계한다는 것은, 엔지니어의 구현 언어를 기획 단계에서 미리 통일하는 것이다."
   - 일반적인 PM-엔지니어 협업 방식과의 차이점을 대비 구조로 서술.

2. **기획 의도 → 수식 변환 5-Step Timeline**
   - Step 1: 문제 인식 — 인용구 형식으로 정제.
   - Step 2: 의도 언어화 — 인용구 형식.
   - Step 3: 수식 설계 (기획자) — 실제 수치(`cold: w₁=0.1, w₂=0.7, w₃=0.2`) 코드 인라인.
   - Step 4: 엔지니어 구현 — `reranker.py` 바로 구현 가능했던 이유 1줄.
   - Step 5: 피드백 루프 — 평가 지표(Precision@K, NDCG@K) → 가중치 재조정 → 명세 업데이트의 사이클.

3. **협업 효과 Callout 3개** (각각 다른 색상)
   - **공통 언어 확립** (green): `S_personal`, `S_pop`, `S_recency` — 기획 문서 = 코드 변수명.
   - **스펙 변경 최소화** (blue): 수식 확정 후 "어떻게 할까요?" 재협의 불필요.
   - **학습 데이터 연계** (accent): `is_training_data`, 72h 잠금, 행동 가중치 — 동일 기획 언어로 AI 파이프라인 직결.

4. **기획자가 직접 설계한 기술 명세 테이블** (9행)
   - 명세 항목 / 설계 내용 / 연결된 코드·DB 컬럼.
   - 3열로 확장하여 기획-구현 연결고리를 시각화.

5. **크로스팀 협업 카드 (3열)**
   - Frontend / Backend / AI Server 각 카드: 기술 스택 badge + "기획자 접점" 1~2문장.

---

### Module 6 — Evaluation Design (Collapsible 섹션)
> **HTML Section ID**: `#evaluation`
> **레이아웃**: 기본 접힘(collapsible). 평가 지표 테이블 + RQ 테이블 + 페르소나 평가 테이블.

**추출 지시**:

1. **오프라인 평가 지표 테이블** (7행)
   - 지표명 / 측정 대상 / 활용 / K값 기준.

2. **연구 가설(RQ) 테이블** (5행)
   - RQ1~RQ5 / 가설 / 검증 방법.

3. **Synthetic Persona 평가 설계** (Callout + 4행 테이블)
   - `synthetic_persona_output/` 폴더 존재 언급.
   - 평가 항목 4개: 장르 일관성 / 이미 읽은 책 배제 / 거부 도서 배제 / LLM 자가 평가.

---

## 🎨 추가 렌더링 지시

### Mermaid 다이어그램 초기화 설정

```javascript
mermaid.initialize({
  startOnLoad: true,
  theme: 'dark',
  themeVariables: {
    primaryColor: '#7c6fff',
    primaryTextColor: '#e2e8f0',
    primaryBorderColor: '#2a2a50',
    lineColor: '#4a4a70',
    secondaryColor: '#13132a',
    tertiaryColor: '#1a1a35',
    background: '#0f172a',
    mainBkg: '#13132a',
    nodeBorder: '#2a2a50',
    titleColor: '#a78bfa',
    edgeLabelBackground: '#13132a',
    fontFamily: 'Segoe UI, Apple SD Gothic Neo, sans-serif',
  },
  flowchart: { htmlLabels: true, curve: 'basis' },
  sequence: { useMaxWidth: true },
  er: { useMaxWidth: true },
});
```

### Sticky Nav 구성

```
[북켓몬]  Vision  Mechanism  Engine  Architecture  Bridge  Evaluation
```
- 배경: `rgba(13,13,26,.92)` + `backdrop-filter: blur(12px)`
- 활성 섹션 하이라이트: Intersection Observer로 구현

### 반응형 브레이크포인트

- `≥ 1080px`: 2열·3열 그리드 활성
- `< 720px`: 모든 그리드 1열 전환

### CDN 의존성 (외부 네트워크 필요)

```html
<script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
```

---

## 📋 최종 산출물 체크리스트

HTML 작성 완료 후 아래 항목을 검증할 것.

- [ ] 5개 섹션 모두 `<section id="...">` 태그로 앵커 연결
- [ ] Sticky Nav 클릭 시 해당 섹션으로 스크롤 이동
- [ ] Mermaid 다이어그램 3개 이상 렌더링 확인 (아키텍처 / 시퀀스 / ERD)
- [ ] Formula Box 수식 변수·계수 색상 구분 적용
- [ ] 동적 가중치 Weight Bar 2열 카드 시각화
- [ ] `<details>` collapsible 정상 동작 (기본 접힘 상태)
- [ ] SQL 코드 블록 syntax highlight 적용
- [ ] 모바일(720px) 그리드 1열 전환 확인
- [ ] 모든 Mermaid 다이어그램 다크 테마 적용

---

## 📎 Input Data 참조

- **원본 마크다운**: `bookemon-portfolio.md` (동일 디렉토리)
- **아키텍처 문서**: `book-curation/docs/meeting-notes/04.21/아키텍처.md`
- **시스템 플로우**: `book-curation/docs/meeting-notes/04.21/시스템_플로우.md`
- **API 명세서**: `book-curation/docs/meeting-notes/04.21/API_명세서.md`
