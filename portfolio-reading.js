(() => {
  'use strict';
  const casesEl = document.getElementById('portfolio-cases');
  const results = document.getElementById('record-books');
  if (casesEl && results) {
  const cases = JSON.parse(casesEl.textContent);
  const buttons = [...document.querySelectorAll('[data-case]')];
  results.setAttribute('aria-live', 'polite');
  function showCase(id) {
    const example = cases.find(item => item.id === id);
    if (!example) return;
    document.getElementById('record-query').textContent = example.query;
    results.replaceChildren(...example.books.map(book => {
      const li = document.createElement('li');
      const rank = document.createElement('span'); rank.className = 'record-rank'; rank.textContent = String(book.rank).padStart(2, '0');
      const info = document.createElement('span');
      const title = document.createElement('strong'); title.textContent = book.title;
      const author = document.createElement('small'); author.textContent = book.author;
      info.append(title, author); li.append(rank, info); return li;
    }));
    document.getElementById('record-note').textContent = `저장된 검색 기록 · 실행 당시 결과를 그대로 보여줍니다.`;
    buttons.forEach(button => button.setAttribute('aria-pressed', String(button.dataset.case === id)));
  }
  buttons.forEach(button => button.addEventListener('click', () => showCase(button.dataset.case)));
  }

  const panels = [...document.querySelectorAll('.reader-detail')];
  const expand = document.getElementById('expand-all');
  function syncExpand() {
    const allOpen = panels.every(panel => panel.open);
    expand.textContent = allOpen ? '모두 접기' : '모두 펼치기';
    expand.setAttribute('aria-expanded', String(allOpen));
  }
  panels.forEach(panel => panel.addEventListener('toggle', syncExpand));
  expand.addEventListener('click', () => {
    const open = !panels.every(panel => panel.open);
    panels.forEach(panel => { panel.open = open; }); syncExpand();
  });
  function revealTarget() {
    let id; try { id = decodeURIComponent(location.hash.slice(1)); } catch { return; }
    const target = document.getElementById(id);
    if (!target) return;
    let panel = target.closest('details');
    while (panel) { panel.open = true; panel = panel.parentElement.closest('details'); }
    requestAnimationFrame(() => target.scrollIntoView({ block: 'start', behavior: 'auto' }));
  }
  document.addEventListener('click', event => {
    const anchor = event.target.closest('a[href^="#"]');
    if (anchor && anchor.hash === location.hash) revealTarget();
  });
  addEventListener('hashchange', revealTarget);
  if (location.hash) revealTarget();

  const query = new URLSearchParams(location.search);
  let saved = null; try { saved = JSON.parse(sessionStorage.getItem('portfolio.reading.return.v1')); } catch {}
  const home = new URL('../', location.href);
  home.searchParams.set('work', '01-bookemon');
  if (query.get('from') === 'portfolio' && saved?.version === 1) home.searchParams.set('resume', '1');
  else home.hash = 'carousel';
  document.querySelectorAll('#portfolio-back,[data-portfolio-back]').forEach(link => { link.href = home.href; });
})();
