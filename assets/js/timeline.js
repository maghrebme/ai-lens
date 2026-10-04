// Ai-Lens — the main timeline: a snake line of milestones, newest at the top.
//
// Cards sit in a grid whose rows alternate direction (boustrophedon): the first
// row reads in the page direction (right→left in Arabic), the next comes back,
// and so on. An SVG path is then drawn through the node centres with rounded
// U-turns in the side gutters, and a brighter copy of it fills in as you scroll.

import {
  $, esc, safeUrl, state, T, isRtl, CATS, icon, chipGroup, initChrome,
  shownTitle, shownSummary, fmtDate, impactDots, loadMilestones, loadNews, matches,
} from './common.js';
import { ORG_ALIASES, orgsOf, timelineHidden, initSources } from './sources.js';

const view = {
  all: [],
  feeds: [],
  cats: new Set(),
  q: '',
  cols: 0,
  items: [],
  segments: [],     // [{y, len}] row checkpoints for the scroll progress
  total: 0,
  nodeLens: [],     // path length at which each node is reached
};

const orgName = (o) => T().orgs[o] || o;

// ── data ──────────────────────────────────────────────────────────────────
async function load() {
  const milestones = await loadMilestones();
  let live = [];
  try {
    const doc = await loadNews();
    view.feeds = doc.sources || [];
    // Launches the server flagged in the news feed join the timeline as "new".
    live = doc.items.filter((it) => it.milestone).map((it) => ({
      ...it, live: true, impact: Math.max(it.impact, 4), category: 'models',
      org: ORG_ALIASES[it.source_name] || it.source_name, link: it.url,
    }));
  } catch { /* the timeline works without the news server */ }
  // Skip an auto-detected launch when the same event is already a curated milestone
  // (same link, or its curated title appears in the headline within a week).
  const norm = (t) => (t || '').toLowerCase().replace(/[^\w.\- ]/g, ' ');
  live = live.filter((n) => !milestones.some((m) =>
    (m.link && n.url && m.link.replace(/\/$/, '') === n.url.replace(/\/$/, ''))
    || (Math.abs(m._t - n._t) < 7 * 86400e3 && norm(n.title).includes(norm(m.title_en)))));
  view.all = [...milestones, ...live].sort((a, b) => b._t - a._t);
}

function filtered() {
  const q = view.q.trim().toLowerCase();
  return view.all.filter((it) => {
    if (view.cats.size && !view.cats.has(it.category)) return false;
    if (timelineHidden(it)) return false;
    return matches(it, q);
  });
}

// ── filters ───────────────────────────────────────────────────────────────
let renderCatChips, sources;
function buildFilters() {
  const count = (pred) => view.all.filter(pred).length;
  renderCatChips = chipGroup($('#catChips'),
    CATS.map((c) => ({ value: c, label: T().cats[c], color: `var(--c-${c})`, count: count((it) => it.category === c) })),
    view.cats, render);
}

// ── cards ─────────────────────────────────────────────────────────────────
function card(it, i) {
  const st = shownTitle(it), ss = shownSummary(it);
  const year = new Date(it._t).getUTCFullYear();
  // Show only as much of the date as the source confirms.
  const date = it.precision === 'year' ? ''
    : fmtDate(it._t, it.precision === 'month' ? { month: 'long', timeZone: 'UTC' } : { day: 'numeric', month: 'long', timeZone: 'UTC' });
  const badge = st.lang !== state.lang ? `<span class="badge" title="${esc(T().originalLang)}">${st.lang === 'ar' ? 'ع' : 'EN'}</span>` : '';
  const org = orgsOf(it).map(orgName).join(' · ');
  return `<li class="stop${it.live ? ' live' : ''}" style="--cat:var(--c-${it.category})" data-i="${i}">
    <span class="node" aria-hidden="true">${icon(it.category)}</span>
    <article class="mcard">
      <p class="m-meta"><span class="cat">${esc(T().cats[it.category])}</span><span>${esc(date)}</span>
        ${it.live ? `<span class="live-tag" title="${esc(T().liveTip)}">● ${esc(T().live)}</span>` : ''}</p>
      <p class="m-year">${year}</p>
      <h3 class="m-title" lang="${st.lang}" dir="auto">${esc(st.text)}${badge}</h3>
      ${ss.text ? `<p class="m-sum" lang="${ss.lang}" dir="auto">${esc(ss.text)}</p>` : ''}
      <p class="m-foot">${impactDots(it.impact)}<span class="m-org">${esc(org)}</span>
        ${it.link ? `<a href="${esc(safeUrl(it.link))}" target="_blank" rel="noopener noreferrer">${esc(T().source)} ↗</a>` : ''}</p>
    </article>
  </li>`;
}

// Decade shortcuts: scroll to the newest milestone of each decade in view.
function renderJumps() {
  const firstOf = new Map();
  view.items.forEach((it, i) => {
    const dec = Math.floor(new Date(it._t).getUTCFullYear() / 10) * 10;
    if (!firstOf.has(dec)) firstOf.set(dec, i);
  });
  $('#jumpChips').innerHTML = [...firstOf].map(([dec, i]) =>
    `<button type="button" class="chip" data-i="${i}">${dec}s</button>`).join('');
}

function columnsFor(width) {
  if (width >= 1500) return 4;
  if (width >= 1040) return 3;
  if (width >= 680) return 2;
  return 1;
}

function render() {
  view.items = filtered();
  $('#count').textContent = T().milestones(view.items.length);
  const grid = $('#snakeGrid');
  if (!view.items.length) {
    grid.innerHTML = `<li class="empty">${esc(T().empty)}</li>`;
    $('#snakeSvg').innerHTML = '';
    $('#futureTag').hidden = $('#originTag').hidden = true;
    return;
  }
  grid.innerHTML = view.items.map(card).join('');
  renderJumps();
  $('#originTag b').textContent = new Date(view.items[view.items.length - 1]._t).getUTCFullYear();
  layout(true);
  observeCards();
}

// Place every card in the grid, alternating row direction, then draw the line.
function layout(force = false) {
  const section = $('#snake');
  const cols = columnsFor(section.clientWidth);
  if (!force && cols === view.cols) { drawLine(); return; }
  view.cols = cols;
  const grid = $('#snakeGrid');
  grid.style.setProperty('--cols', cols);
  grid.classList.toggle('single', cols === 1);
  grid.querySelectorAll('.stop').forEach((li, i) => {
    const row = Math.floor(i / cols);
    const pos = i % cols;
    const col = row % 2 === 0 ? pos : cols - 1 - pos;
    li.style.gridRow = String(row + 1);
    li.style.gridColumn = String(col + 1);
    li.classList.toggle('back', row % 2 === 1);
  });
  drawLine();
}

function drawLine() {
  const section = $('#snake');
  const svg = $('#snakeSvg');
  const nodes = [...section.querySelectorAll('.stop .node')];
  if (!nodes.length) return;
  const box = section.getBoundingClientRect();
  const W = box.width, H = section.scrollHeight;
  const pts = nodes.map((n) => {
    const r = n.getBoundingClientRect();
    return { x: r.left + r.width / 2 - box.left, y: r.top + r.height / 2 - box.top };
  });
  const cols = view.cols;
  const gutter = parseFloat(getComputedStyle($('#snakeGrid')).paddingInlineStart) || 40;
  const leftX = gutter / 2, rightX = W - gutter / 2;
  // Visual direction of row r: +1 → rightwards. Row 0 follows the reading direction.
  const dirOf = (r) => ((isRtl() ? -1 : 1) * (r % 2 === 0 ? 1 : -1));

  if (cols === 1) { drawStraight(svg, pts, W, H); return; }

  const rows = [];
  pts.forEach((p, i) => { const r = Math.floor(i / cols); (rows[r] ||= []).push(p); });

  let d = '', len = 0;
  const segments = [], nodeLens = [];
  const first = rows[0][0];
  d += `M ${first.x} ${first.y}`;
  let cur = { ...first };
  let idx = 0;
  rows.forEach((row, r) => {
    const dir = dirOf(r);
    segments.push({ y: row[0].y, len });
    row.forEach((p) => {
      len += Math.abs(p.x - cur.x) + Math.abs(p.y - cur.y);
      d += ` L ${p.x} ${p.y}`;
      cur = { ...p };
      nodeLens[idx++] = len;
    });
    const next = rows[r + 1];
    if (!next) return;
    const turnX = dir > 0 ? rightX : leftX;
    const R = Math.min(34, (next[0].y - cur.y) / 2, Math.abs(turnX - cur.x));
    const sweep = dir > 0 ? 1 : 0;
    d += ` L ${turnX - dir * R} ${cur.y}`;
    d += ` A ${R} ${R} 0 0 ${sweep} ${turnX} ${cur.y + R}`;
    d += ` L ${turnX} ${next[0].y - R}`;
    d += ` A ${R} ${R} 0 0 ${sweep} ${turnX - dir * R} ${next[0].y}`;
    len += Math.abs(turnX - cur.x) - R + (Math.PI * R) / 2 + (next[0].y - cur.y - 2 * R) + (Math.PI * R) / 2;
    cur = { x: turnX - dir * R, y: next[0].y };
  });
  segments.push({ y: cur.y + 80, len });
  view.segments = segments; view.total = len; view.nodeLens = nodeLens;

  // Lead-in from "the future": comes down from the top edge on the start side.
  const dir0 = dirOf(0);
  const startX = dir0 > 0 ? leftX : rightX;
  const fy = first.y, R0 = 30;
  const future = `M ${startX} ${Math.max(4, fy - 120)} L ${startX} ${fy - R0} A ${R0} ${R0} 0 0 ${dir0 > 0 ? 0 : 1} ${startX + dir0 * R0} ${fy} L ${first.x} ${fy}`;
  // Tail after the oldest stop.
  const lastDir = dirOf(rows.length - 1);
  const tailX = cur.x + lastDir * Math.min(70, gutter + 20);
  const tail = `M ${cur.x} ${cur.y} L ${tailX} ${cur.y}`;

  paint(svg, W, H, { future, d, len, tail, end: { x: tailX, y: cur.y }, futureAt: { x: startX, y: Math.max(4, fy - 120) } });
}

// Phones: one column, the line runs straight down beside the cards.
function drawStraight(svg, pts, W, H) {
  let d = `M ${pts[0].x} ${pts[0].y}`, len = 0;
  const segments = [], nodeLens = [];
  pts.forEach((p, i) => {
    if (i) { len += p.y - pts[i - 1].y; d += ` L ${p.x} ${p.y}`; }
    segments.push({ y: p.y, len });
    nodeLens.push(len);
  });
  const last = pts[pts.length - 1];
  segments.push({ y: last.y + 80, len });
  view.segments = segments; view.total = len; view.nodeLens = nodeLens;
  const x = pts[0].x;
  paint(svg, W, H, {
    future: `M ${x} ${Math.max(4, pts[0].y - 90)} L ${x} ${pts[0].y}`,
    d, len, tail: `M ${x} ${last.y} L ${x} ${last.y + 60}`,
    end: { x, y: last.y + 60 }, futureAt: { x, y: Math.max(4, pts[0].y - 90) },
  });
}

function paint(svg, W, H, { future, d, len, tail, end, futureAt }) {
  const cs = getComputedStyle(document.documentElement);
  const stops = CATS.map((c, i) => `<stop offset="${i / (CATS.length - 1)}" stop-color="${cs.getPropertyValue(`--c-${c}`).trim()}"/>`).join('');
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
  svg.setAttribute('width', W); svg.setAttribute('height', H);
  svg.innerHTML = `
    <defs><linearGradient id="spectrum" gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="0" y2="${H}">${stops}</linearGradient></defs>
    <path class="future" d="${future}"/>
    <path class="base" d="${d}"/>
    <path class="glow" id="progressGlow" d="${d}" style="stroke-dasharray:${len};stroke-dashoffset:${len}"/>
    <path class="progress" id="progressPath" d="${d}" style="stroke-dasharray:${len};stroke-dashoffset:${len}"/>
    <path class="tail" d="${tail}"/>
    <circle class="end" cx="${end.x}" cy="${end.y}" r="5"/>`;
  const ft = $('#futureTag');
  ft.hidden = false;
  ft.style.top = `${Math.max(0, futureAt.y)}px`;
  ft.style.left = `${futureAt.x}px`;
  const ot = $('#originTag');
  ot.hidden = false;
  ot.style.top = `${end.y + 12}px`;
  ot.style.left = `${end.x}px`;
  onScroll();
}

// ── scroll progress ───────────────────────────────────────────────────────
function onScroll() {
  const section = $('#snake');
  if (!view.segments.length) return;
  const marker = innerHeight * 0.62 - section.getBoundingClientRect().top;
  const s = view.segments;
  let L = 0;
  if (marker <= s[0].y) L = 0;
  else if (marker >= s[s.length - 1].y) L = view.total;
  else {
    for (let i = 0; i < s.length - 1; i++) {
      if (marker >= s[i].y && marker < s[i + 1].y) {
        const f = (marker - s[i].y) / (s[i + 1].y - s[i].y);
        L = s[i].len + f * (s[i + 1].len - s[i].len);
        break;
      }
    }
  }
  const off = view.total - L;
  const p = $('#progressPath'), g = $('#progressGlow');
  if (p) { p.style.strokeDashoffset = off; g.style.strokeDashoffset = off; }
  document.querySelectorAll('.stop').forEach((li, i) => li.classList.toggle('reached', view.nodeLens[i] <= L + 1));
  revealCards();
}

// Cards below the screen at render time start hidden and rise in as they
// come into view; everything above the fold is visible straight away.
function observeCards() {
  if (matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  document.querySelectorAll('.stop').forEach((li) => {
    if (li.getBoundingClientRect().top > innerHeight) li.classList.add('pre');
  });
}
function revealCards() {
  document.querySelectorAll('.stop.pre').forEach((li) => {
    if (li.getBoundingClientRect().top < innerHeight * 0.92) li.classList.remove('pre');
  });
}

// ── boot ──────────────────────────────────────────────────────────────────
async function boot() {
  initChrome('timeline', (what) => {
    if (what === 'lang') { renderCatChips(); sources.refresh(); render(); }
    if (what === 'theme') drawLine();
  });
  $('#count').textContent = T().loading;
  await load();
  buildFilters();
  sources = initSources({
    getOrgs: () => {
      const counts = {};
      view.all.forEach((it) => orgsOf(it).forEach((o) => { counts[o] = (counts[o] || 0) + 1; }));
      return Object.entries(counts).sort((x, y) => y[1] - x[1]).map(([name, count]) => ({ name, count }));
    },
    getFeeds: () => view.feeds,
    onChange: render,
  });
  render();
  $('#jumpChips').addEventListener('click', (e) => {
    const b = e.target.closest('[data-i]');
    const li = b && document.querySelector(`.stop[data-i="${b.dataset.i}"]`);
    if (!li) return;
    li.classList.remove('pre');
    li.scrollIntoView({ behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'center' });
  });
  let qTimer;
  $('#search').addEventListener('input', (e) => {
    clearTimeout(qTimer);
    qTimer = setTimeout(() => { view.q = e.target.value; render(); }, 150);
  });
  let raf = 0;
  addEventListener('scroll', () => { if (!raf) raf = requestAnimationFrame(() => { raf = 0; onScroll(); }); }, { passive: true });
  new ResizeObserver(() => { if (!raf) raf = requestAnimationFrame(() => { raf = 0; layout(); }); }).observe($('#snake'));
  document.fonts?.ready.then(() => drawLine());
}

boot();
