# HyperFrames용 HTML 사전 설계 전략

> 이 문서는 "기존 HTML 포트폴리오/발표자료를 HyperFrames로 영상 렌더링할 때" 처음부터 효율적으로 작업하기 위한 설계 전략이다.
> 실제 북켓몬 프로젝트 변환 경험(2026-05)에서 발생한 문제를 기반으로 작성되었다.

---

## 핵심 원칙

> "HyperFrames는 스크롤이 없다. 타임라인이 스크롤을 대신한다."

- 각 섹션은 **독립된 슬라이드**처럼 설계
- 전환은 **JS + `hf-seek` 이벤트**로 처리
- 사이드바·목차·스크롤 트리거는 **처음부터 배제**

---

## 1. 레이아웃 설계 원칙

### 금지 패턴
```css
/* 금지: 사이드바+본문 그리드 */
body { display: grid; grid-template-columns: 300px 1fr; }

/* 금지: 스크롤 기반 레이아웃 */
main { overflow-y: scroll; height: 100vh; }

/* 금지: 섹션이 세로로 쌓이는 구조 */
section { margin-bottom: 40px; }
```

### 권장 패턴
```css
/* 권장: 단일 스테이지 */
body, html { margin: 0; padding: 0; overflow: hidden; }

#stage {
  position: relative;
  width: 1920px;
  height: 1080px;
  overflow: hidden;
}

/* 권장: 섹션은 절대 위치, 기본 숨김 */
section {
  position: absolute;
  top: 0; left: 0;
  width: 1920px;
  height: 1080px;
  opacity: 0;
  pointer-events: none;
  box-sizing: border-box;
}

/* 권장: 활성 섹션만 표시 */
section.hf-active {
  opacity: 1;
  pointer-events: auto;
  z-index: 10;
}
```

---

## 2. HTML 구조 원칙

### 금지 구조
```html
<!-- 금지: 사이드바 -->
<aside>
  <nav>목차 링크들</nav>
</aside>

<!-- 금지: 모든 섹션이 DOM에 세로로 쌓임 -->
<main>
  <section id="s1">...</section>
  <section id="s2">...</section>
  ...
</main>
```

### 권장 구조
```html
<div id="stage"
  data-composition-id="MY_PROJECT"
  data-duration="180"
  data-width="1920"
  data-height="1080">

  <section id="s01" data-start="0"  data-duration="15" data-track-index="0">...</section>
  <section id="s02" data-start="15" data-duration="15" data-track-index="0">...</section>
  <!-- ... -->

</div>
```

**규칙:**
- `<aside>`, `<nav>` 목차 구조 → 처음부터 제외
- 각 `<section>`에 `data-start`, `data-duration`, `data-track-index="0"` 추가
- `#stage` 바로 아래에 `<section>` 배치 (main 래퍼 없어도 됨)

---

## 3. 애니메이션 설계 원칙

### 금지 패턴
```js
// 금지: IntersectionObserver (스크롤 트리거)
const observer = new IntersectionObserver(entries => {
  entries.forEach(e => e.target.classList.toggle('visible', e.isIntersecting));
});
document.querySelectorAll('.reveal').forEach(el => observer.observe(el));
```

```css
/* 금지: 진입 애니메이션이 스크롤/hover에 의존 */
.reveal { opacity: 0; transform: translateY(30px); }
.reveal.visible { opacity: 1; transform: none; }
```

### 권장 패턴
```css
/* 권장: CSS 애니메이션, section이 활성화될 때 자동 실행 */
section.hf-active .card {
  animation: fadeSlideUp 0.5s ease forwards;
}

@keyframes fadeSlideUp {
  from { opacity: 0; transform: translateY(20px); }
  to   { opacity: 1; transform: none; }
}

/* 지연 변형 */
section.hf-active .card:nth-child(2) { animation-delay: 0.1s; }
section.hf-active .card:nth-child(3) { animation-delay: 0.2s; }
```

**원칙:** 애니메이션 트리거를 `.hf-active` 클래스 부착에 연결한다.

---

## 4. HyperFrames 연동 JS 보일러플레이트

모든 HyperFrames용 HTML에 아래 JS를 `</body>` 직전에 삽입한다.

```js
(function () {
  // ① 섹션 타이밍 테이블 — data-start 값과 일치시킬 것
  const SECTIONS = [
    { id: 's01', start:  0, end: 15 },
    { id: 's02', start: 15, end: 30 },
    // ...
  ];

  let currentId = null;

  function showSection(id) {
    if (currentId === id) return;
    document.querySelectorAll('section.hf-active').forEach(el => {
      el.classList.remove('hf-active');
    });
    const el = document.getElementById(id);
    if (el) { el.classList.add('hf-active'); currentId = id; }
  }

  function onSeek(timeSec) {
    for (const s of SECTIONS) {
      if (timeSec >= s.start && timeSec < s.end) { showSection(s.id); return; }
    }
    // 마지막 섹션 처리
    showSection(SECTIONS[SECTIONS.length - 1].id);
  }

  // ② HyperFrames 이벤트 수신 (detail.time = 초 단위)
  window.addEventListener('hf-seek', e => onSeek(e.detail.time));

  // ③ 초기 렌더링
  document.addEventListener('DOMContentLoaded', () => showSection(SECTIONS[0].id));
})();
```

---

## 5. 섹션 시간 설계 가이드

| 섹션 유형 | 권장 duration | 이유 |
|-----------|--------------|------|
| 타이틀/커버 | 8~12초 | 임팩트 + 보이스오버 시작 |
| 텍스트 중심 (개념 설명) | 10~15초 | 읽을 시간 확보 |
| 다이어그램/아키텍처 | 15~25초 | 구조 파악 시간 |
| 코드 스니펫 | 10~15초 | 핵심 라인만 보여줄 것 |
| 수치/통계 강조 | 8~12초 | 짧고 임팩트 있게 |
| Q&A/마무리 | 8~10초 | |

**총 시간 계산:** `sections.reduce((sum, s) => sum + s.duration, 0)` → `data-duration`에 입력

---

## 6. 해상도 & 폰트 설계

```css
/* 영상 기준: 1920×1080 고정 */
#stage {
  width: 1920px;
  height: 1080px;
  font-size: 18px; /* 기준 폰트 */
}

/* 폰트 크기 권장값 (영상용) */
h1        { font-size: 64px; }
h2        { font-size: 48px; }
h3        { font-size: 36px; }
body text { font-size: 22px; }
caption   { font-size: 18px; }
code      { font-size: 18px; }

/* 영상에서 잘 보이는 최소 폰트 크기: 16px */
```

---

## 7. 체크리스트 (HTML 제작 시)

### 구조
- [ ] `<aside>`, `<nav>` 목차 없음
- [ ] `<section>` 각각에 `id`, `data-start`, `data-duration`, `data-track-index="0"` 있음
- [ ] `#stage`에 `data-composition-id`, `data-duration`, `data-width="1920"`, `data-height="1080"` 있음
- [ ] `body`/`html`에 `overflow: hidden`

### 레이아웃
- [ ] `section { position: absolute; top:0; left:0; width:1920px; height:1080px; }`
- [ ] 사이드바 grid 레이아웃 없음
- [ ] 스크롤 의존 레이아웃 없음

### 애니메이션
- [ ] IntersectionObserver 없음
- [ ] 진입 애니메이션은 `.hf-active` 클래스 트리거
- [ ] hover 전용 효과는 영상에서 무의미하므로 제거

### JS
- [ ] HyperFrames 보일러플레이트 `</body>` 직전에 삽입
- [ ] SECTIONS 배열이 `data-start`/`data-duration`과 일치

### 영상 품질
- [ ] 폰트 최소 16px 이상
- [ ] 대비가 충분한 배경/텍스트 색상 (WCAG AA 이상 권장)
- [ ] 이미지는 `width`/`height` 명시 (레이아웃 shift 방지)

---

## 8. 기존 웹용 HTML → 영상용 변환 절차

기존에 만든 스크롤 기반 HTML을 영상용으로 바꿀 때의 단계:

1. `<aside>` 제거
2. `.layout { display: grid }` → `display: block`
3. `<section>`에 `data-start`, `data-duration` 추가
4. `#stage` 래퍼 추가 + HyperFrames attributes
5. CSS에 `section { position: absolute; opacity: 0; }` 추가
6. IntersectionObserver 코드 제거
7. HyperFrames 보일러플레이트 JS 삽입
8. `npx hyperframes compositions` 로 인식 확인
9. `npx hyperframes preview --force-new` 로 시각 확인

---

## 9. 처음부터 영상 전용으로 만들 때 템플릿

```html
<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<title>MY PROJECT</title>
<style>
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
html, body { overflow: hidden; }

#stage {
  position: relative;
  width: 1920px;
  height: 1080px;
  overflow: hidden;
  background: #0f172a;
  font-family: 'Outfit', sans-serif;
  font-size: 18px;
  color: #f1f5f9;
}

section {
  position: absolute;
  top: 0; left: 0;
  width: 1920px;
  height: 1080px;
  opacity: 0;
  pointer-events: none;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 80px 120px;
}

section.hf-active {
  opacity: 1;
  pointer-events: auto;
  z-index: 10;
}

/* 진입 애니메이션 */
section.hf-active h2,
section.hf-active p,
section.hf-active .card {
  animation: fadeUp 0.5s ease forwards;
}
@keyframes fadeUp {
  from { opacity: 0; transform: translateY(24px); }
  to   { opacity: 1; transform: none; }
}
</style>
</head>
<body>
<div id="stage"
  data-composition-id="MY_PROJECT"
  data-duration="120"
  data-width="1920"
  data-height="1080">

  <section id="s01" data-start="0"  data-duration="12" data-track-index="0">
    <h1>타이틀</h1>
    <p>부제목</p>
  </section>

  <section id="s02" data-start="12" data-duration="15" data-track-index="0">
    <h2>섹션 2</h2>
    <p>내용</p>
  </section>

  <!-- 섹션 추가 ... -->

</div>

<script>
(function () {
  const SECTIONS = [
    { id: 's01', start:  0, end: 12 },
    { id: 's02', start: 12, end: 27 },
    // ...
  ];
  let currentId = null;
  function showSection(id) {
    if (currentId === id) return;
    document.querySelectorAll('section.hf-active').forEach(el => el.classList.remove('hf-active'));
    const el = document.getElementById(id);
    if (el) { el.classList.add('hf-active'); currentId = id; }
  }
  function onSeek(t) {
    for (const s of SECTIONS) { if (t >= s.start && t < s.end) { showSection(s.id); return; } }
    showSection(SECTIONS[SECTIONS.length - 1].id);
  }
  window.addEventListener('hf-seek', e => onSeek(e.detail.time));
  document.addEventListener('DOMContentLoaded', () => showSection(SECTIONS[0].id));
})();
</script>
</body>
</html>
```
