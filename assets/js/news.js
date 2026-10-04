// Ai-Lens — latest news: a vertical centre line, stories alternating sides,
// grouped by day. On narrow screens the line moves to the side.

import {
  $, esc, safeUrl, state, T, CATS, icon, chipGroup, initChrome,
  shownTitle, shownSummary, fmtDate, relTime, impactDots, loadNews, loadConfig, loadMilestones, matches,
} from './common.js';
import { orgsOf, newsHidden, initSources } from './sources.js';

const PAGE = 40;
const view = {
  items: [], sources: [], updatedAt: null, enrichment: false,
  cats: new Set(), q: '', milestones: [], limit: PAGE, wide: true,
};

function filtered() {
  const q = view.q.trim().toLowerCase();
  return view.items.filter((it) =>
    (!view.cats.size || view.cats.has(it.category))
    && !newsHidden(it)
    && matches(it, q));
}

// ── filters ───────────────────────────────────────────────────────────────
let renderCatChips, sources;
function buildFilters() {
  const count = (pred) => view.items.filter(pred).length;
  renderCatChips = chipGroup($('#catChips'),
    CATS.map((c) => ({ value: c, label: T().cats[c], color: `var(--c-${c})`, count: count((it) => it.category === c) })),
    view.cats, resetAndRender);
}
function resetAndRender() { view.limit = PAGE; render(); }

// ── rendering ─────────────────────────────────────────────────────────────
function dayLabel(t) {
  const d = new Date(t); d.setHours(0, 0, 0, 0);
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const diff = Math.round((today - d) / 86400e3);
  const date = fmtDate(t, { weekday: 'long', day: 'numeric', month: 'long' });
  if (diff === 0) return `${T().today} · ${date}`;
  if (diff === 1) return `${T().yesterday} · ${date}`;
  return date;
}

function event(it) {
  const st = shownTitle(it), ss = shownSummary(it);
  const badge = st.lang !== state.lang ? `<span class="badge" title="${esc(T().originalLang)}">${st.lang === 'ar' ? 'ع' : 'EN'}</span>` : '';
  const time = fmtDate(it._t, { hour: '2-digit', minute: '2-digit', hour12: false });
  const related = it.related?.length
    ? `<details class="ev-related"><summary>${esc(T().outlets(it.echo))}</summary><ul>${it.related.map((r) =>
      `<li><a href="${esc(safeUrl(r.url))}" target="_blank" rel="noopener noreferrer"><b>${esc(r.source_name)}</b> <span dir="auto">${esc(r.title)}</span></a></li>`).join('')}</ul></details>` : '';
  return `<article class="ev" style="--cat:var(--c-${it.category})">
    <div class="ev-head" aria-hidden="true"><span class="ev-icon">${icon(it.category)}</span><span class="ev-dash"></span><span class="ev-dot"></span></div>
    <p class="ev-kicker"><span class="cat">${esc(T().cats[it.category])}</span> · <time datetime="${esc(it.published)}" title="${esc(relTime(it._t))}">${esc(time)}</time></p>
    <h3 class="ev-title" lang="${st.lang}" dir="auto"><a href="${esc(safeUrl(it.url))}" target="_blank" rel="noopener noreferrer">${esc(st.text)}</a>${badge}</h3>
    ${ss.text ? `<p class="ev-sum" lang="${ss.lang}" dir="auto">${esc(ss.text)}</p>` : ''}
    <p class="ev-foot"><span class="ev-src">${esc(it.source_name)}</span>${impactDots(it.impact)}</p>
    ${related}
  </article>`;
}

function render() {
  const items = filtered();
  const shown = items.slice(0, view.limit);
  $('#count').textContent = T().stories(items.length);
  const day24 = view.items.filter((it) => Date.now() - it._t < 86400e3).length;
  $('#count24').textContent = T().last24(day24);

  if (!shown.length) {
    $('#feed').innerHTML = `<p class="empty">${esc(T().empty)}</p>`;
    $('#moreBtn').hidden = true;
    return;
  }
  const groups = [];
  for (const it of shown) {
    const key = new Date(it._t).toDateString();
    if (!groups.length || groups[groups.length - 1].key !== key) groups.push({ key, t: it._t, items: [] });
    groups[groups.length - 1].items.push(it);
  }
  // Wide screens: two columns that alternate (1st, 3rd… start side; 2nd, 4th… end side,
  // pushed down so they interleave). Narrow screens: one column in time order.
  $('#feed').innerHTML = groups.map((g) => {
    const body = view.wide
      ? `<div class="zig"><div class="col a">${g.items.filter((_, i) => i % 2 === 0).map(event).join('')}</div>
         <div class="col b">${g.items.filter((_, i) => i % 2 === 1).map(event).join('')}</div></div>`
      : `<div class="zig single"><div class="col b">${g.items.map(event).join('')}</div></div>`;
    return `<section class="day"><h2 class="day-chip"><span>${esc(dayLabel(g.t))}</span></h2>${body}</section>`;
  }).join('');
  $('#moreBtn').hidden = items.length <= view.limit;
}

function renderFooter() {
  const t = T();
  $('#updated').textContent = view.updatedAt
    ? `${t.updated}: ${fmtDate(Date.parse(view.updatedAt), { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit', hour12: false })}` : '';
  $('#enrichNote').textContent = view.enrichment ? t.enrichOn : t.enrichOff;
}

async function refreshData() {
  const doc = await loadNews();
  const changed = doc.updated_at !== view.updatedAt;
  view.items = doc.items;
  view.sources = doc.sources || [];
  view.updatedAt = doc.updated_at;
  return changed;
}

// ── boot ──────────────────────────────────────────────────────────────────
async function boot() {
  initChrome('news', (what) => {
    if (what === 'lang') { buildFilters(); render(); renderFooter(); sources?.refresh(); }
  });
  const mq = matchMedia('(min-width: 860px)');
  view.wide = mq.matches;
  mq.addEventListener('change', (e) => { view.wide = e.matches; render(); });

  $('#count').textContent = T().loading;
  try {
    const [, cfg] = await Promise.all([refreshData(), loadConfig()]);
    view.enrichment = !!cfg.enrichment;
    // A static host is rebuilt on a schedule; there is no server to refresh on demand.
    if (cfg.static) $('#refreshBtn').hidden = true;
  } catch {
    $('#loadError').hidden = false;
    $('#count').textContent = '';
    return;
  }
  buildFilters();
  try { view.milestones = await loadMilestones(); } catch { /* reference list only */ }
  sources = initSources({
    getOrgs: () => {
      const counts = {};
      view.milestones.forEach((it) => orgsOf(it).forEach((o) => { counts[o] = (counts[o] || 0) + 1; }));
      return Object.entries(counts).sort((x, y) => y[1] - x[1]).map(([name, count]) => ({ name, count }));
    },
    getFeeds: () => view.sources,
    onChange: resetAndRender,
  });
  render();
  renderFooter();

  let qTimer;
  $('#search').addEventListener('input', (e) => {
    clearTimeout(qTimer);
    qTimer = setTimeout(() => { view.q = e.target.value; resetAndRender(); }, 150);
  });
  $('#moreBtn').addEventListener('click', () => { view.limit += PAGE; render(); });
  $('#refreshBtn').addEventListener('click', async (e) => {
    const b = e.currentTarget;
    b.disabled = true; b.textContent = T().refreshing;
    try {
      const res = await fetch('api/refresh', { method: 'POST' });
      const body = await res.json().catch(() => ({}));
      if (res.status === 429) b.textContent = T().retryIn(body.retry_in);
      else { await refreshData(); buildFilters(); render(); renderFooter(); sources.refresh(); b.textContent = T().refresh; }
    } catch { b.textContent = T().refresh; }
    setTimeout(() => { b.disabled = false; b.textContent = T().refresh; }, 4000);
  });
  // New stories appear without a reload.
  setInterval(async () => {
    try { if (await refreshData()) { buildFilters(); render(); renderFooter(); } } catch { /* retry next tick */ }
  }, 5 * 60e3);
}

boot();
