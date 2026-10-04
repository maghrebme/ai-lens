// Ai-Lens — shared helpers for both pages: language, theme, chips, icons, data.

import { STR, CATS, locale } from './i18n.js';

export { CATS };
export const $ = (s, el = document) => el.querySelector(s);
export const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
export const safeUrl = (u) => (/^https?:\/\//i.test(u || '') ? u : '#');

const store = {
  get(k) { try { return localStorage.getItem(k); } catch { return null; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch { /* private mode */ } },
};

const params = new URLSearchParams(location.search);
export const state = {
  lang: params.get('lang') || store.get('lens.lang') || 'ar',
  theme: params.get('theme') || store.get('lens.theme')
    || (matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark'),
};
if (!['ar', 'en'].includes(state.lang)) state.lang = 'ar';
if (!['dark', 'light'].includes(state.theme)) state.theme = 'dark';

export const T = () => STR[state.lang];
export const isRtl = () => state.lang === 'ar';

// ── text & dates ──────────────────────────────────────────────────────────
export function shownTitle(it) {
  if (state.lang === 'ar' && it.title_ar) return { text: it.title_ar, lang: 'ar' };
  if (state.lang === 'en' && it.title_en) return { text: it.title_en, lang: 'en' };
  return { text: it.title, lang: it.lang || 'en' };
}
export function shownSummary(it) {
  if (state.lang === 'ar' && it.summary_ar) return { text: it.summary_ar, lang: 'ar' };
  if (state.lang === 'en' && it.summary_en) return { text: it.summary_en, lang: 'en' };
  return { text: it.summary || '', lang: it.lang || 'en' };
}
export function fmtDate(t, opts) { return new Intl.DateTimeFormat(locale(state.lang), opts).format(new Date(t)); }
export function relTime(t) {
  const rtf = new Intl.RelativeTimeFormat(locale(state.lang), { numeric: 'auto' });
  const s = (t - Date.now()) / 1000;
  const a = Math.abs(s);
  if (a < 60) return rtf.format(0, 'minute');
  if (a < 3600) return rtf.format(Math.round(s / 60), 'minute');
  if (a < 86400) return rtf.format(Math.round(s / 3600), 'hour');
  if (a < 86400 * 30) return rtf.format(Math.round(s / 86400), 'day');
  return fmtDate(t, { day: 'numeric', month: 'short', year: 'numeric' });
}
export function impactDots(n) {
  return `<span class="impact" role="img" aria-label="${esc(T().impact)} ${n}/5">${'<i class="on"></i>'.repeat(n)}${'<i></i>'.repeat(5 - n)}</span>`;
}

// ── category icons (24×24, stroke) ───────────────────────────────────────
const PATHS = {
  models: '<rect x="5" y="5" width="14" height="14" rx="3"/><rect x="9.5" y="9.5" width="5" height="5" rx="1"/><path d="M9 2v3M15 2v3M9 19v3M15 19v3M2 9h3M2 15h3M19 9h3M19 15h3"/>',
  products: '<rect x="3" y="4" width="18" height="16" rx="3"/><path d="M3 9h18"/><circle cx="6.5" cy="6.5" r=".6"/><circle cx="9" cy="6.5" r=".6"/><path d="M8 14l2.5 2.5L16 12"/>',
  research: '<path d="M9 3h6M10 3v6.5L4.6 18.4A1.8 1.8 0 0 0 6.2 21h11.6a1.8 1.8 0 0 0 1.6-2.6L14 9.5V3"/><path d="M7 15h10"/>',
  business: '<path d="M3 20h18"/><path d="M5 16l5-5 3.5 3.5L20 8"/><path d="M15 8h5v5"/>',
  policy: '<path d="M12 3v17M7 20h10M4 7h16"/><path d="M6 7l-3 6.5a3 3 0 0 0 6 0L6 7zM18 7l-3 6.5a3 3 0 0 0 6 0L18 7z"/>',
  society: '<circle cx="9" cy="8" r="3.2"/><path d="M3 20a6 6 0 0 1 12 0"/><circle cx="17.5" cy="9.5" r="2.4"/><path d="M15.5 14.6A4.6 4.6 0 0 1 21.5 19"/>',
};
export function icon(cat) {
  return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${PATHS[cat] || PATHS.models}</svg>`;
}

// ── filter chips ──────────────────────────────────────────────────────────
// `selected` is a Set; empty means "all". Clicking a chip while "all" is on
// selects just that one; further clicks add or remove; Shift/Alt = only this.
export function chipGroup(el, options, selected, onChange) {
  const render = () => {
    const allOn = selected.size === 0;
    el.innerHTML = `<button type="button" class="chip all" aria-pressed="${allOn}">${esc(T().all)}</button>`
      + options.map((o) => `<button type="button" class="chip" data-v="${esc(o.value)}" aria-pressed="${!allOn && selected.has(o.value)}"
          ${o.color ? `style="--cat:${o.color}"` : ''}>${o.color ? '<i></i>' : ''}<span ${o.lang ? `lang="${o.lang}"` : ''}>${esc(o.label)}</span>${o.count != null ? `<small>${o.count}</small>` : ''}</button>`).join('');
  };
  el.onclick = (e) => {
    const b = e.target.closest('.chip');
    if (!b) return;
    if (b.classList.contains('all')) selected.clear();
    else {
      const v = b.dataset.v;
      if (e.shiftKey || e.altKey) { selected.clear(); selected.add(v); }
      else if (selected.has(v)) selected.delete(v);
      else selected.add(v);
      if (selected.size === options.length) selected.clear();
    }
    render();
    onChange();
  };
  render();
  return render;
}

// ── chrome: language, theme, nav ─────────────────────────────────────────
function applyStaticText(page) {
  const t = T();
  const html = document.documentElement;
  html.lang = state.lang;
  html.dir = isRtl() ? 'rtl' : 'ltr';
  document.title = { news: t.titleNews, invest: t.titleInvest }[page] || t.titleTimeline;
  document.querySelectorAll('[data-i18n]').forEach((el) => {
    const v = t[el.dataset.i18n];
    if (typeof v === 'string') el.textContent = v;
  });
  document.querySelectorAll('[data-i18n-ph]').forEach((el) => { el.placeholder = t[el.dataset.i18nPh]; });
  document.querySelectorAll('[data-i18n-label]').forEach((el) => {
    el.setAttribute('aria-label', t[el.dataset.i18nLabel]);
  });
  const lb = $('#langBtn');
  lb.textContent = t.langBtn;
  lb.setAttribute('aria-label', t.langBtnLabel);
  lb.lang = isRtl() ? 'en' : 'ar';
  // Carry the language across pages.
  document.querySelectorAll('a[data-nav]').forEach((a) => {
    a.href = `${a.dataset.nav}?lang=${state.lang}`;
  });
  $('#dateG').textContent = fmtDate(Date.now(), { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' });
  try {
    $('#dateH').textContent = new Intl.DateTimeFormat(
      isRtl() ? 'ar-u-ca-islamic-umalqura-nu-latn' : 'en-u-ca-islamic-umalqura',
      { day: 'numeric', month: 'long', year: 'numeric' }).format(Date.now());
  } catch { $('#dateH').textContent = ''; }
}

function applyTheme() {
  document.documentElement.dataset.theme = state.theme;
  $('#themeBtn').textContent = state.theme === 'dark' ? '☀' : '☾';
}

function initToTop() {
  const b = $('#toTop');
  if (!b) return;
  const sync = () => { b.hidden = scrollY < 600; };
  addEventListener('scroll', sync, { passive: true });
  sync();
  b.addEventListener('click', () => {
    scrollTo({ top: 0, behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' });
  });
}

export function initChrome(page, onChange) {
  initToTop();
  applyTheme();
  applyStaticText(page);
  $('#langBtn').addEventListener('click', () => {
    state.lang = isRtl() ? 'en' : 'ar';
    store.set('lens.lang', state.lang);
    const url = new URL(location.href);
    url.searchParams.set('lang', state.lang);
    history.replaceState(null, '', url);
    applyStaticText(page);
    onChange('lang');
  });
  $('#themeBtn').addEventListener('click', () => {
    state.theme = state.theme === 'dark' ? 'light' : 'dark';
    store.set('lens.theme', state.theme);
    applyTheme();
    onChange('theme');
  });
  document.addEventListener('keydown', (e) => {
    if (e.target.matches('input, select, textarea') || e.metaKey || e.ctrlKey) return;
    if (e.key === '/') { e.preventDefault(); $('#search')?.focus(); }
    else if (e.key === 'l' || e.key === 'L') $('#langBtn').click();
  });
}

// ── data ──────────────────────────────────────────────────────────────────
// Live server first (python/server.py); static hosts serve pre-built JSON instead
// (python/build_static.py → api/news.json, api/config.json).
async function fetchJson(live, file) {
  try {
    const res = await fetch(live, { cache: 'no-store' });
    if (res.ok && (res.headers.get('content-type') || '').includes('json')) return await res.json();
  } catch { /* fall through to the static file */ }
  const res = await fetch(file, { cache: 'no-store' });
  if (!res.ok) throw new Error(String(res.status));
  return res.json();
}

export async function loadNews() {
  const doc = await fetchJson('api/news?days=45', 'api/news.json');
  doc.items = doc.items.map((it) => ({ ...clean(it), _t: Date.parse(it.published) }));
  return doc;
}
export async function loadConfig() {
  try { return await fetchJson('api/config', 'api/config.json'); } catch { return {}; }
}
export async function loadMilestones() {
  const rows = await (await fetch('assets/data/milestones.json')).json();
  return rows.map((m, i) => ({
    ...clean(m), id: `m${i}`, title: m.title_en, summary: m.summary_en, lang: 'en', _t: Date.parse(m.date),
  }));
}

// Values that end up in attributes (class, style, lang) or in repeat() are forced
// into their known ranges, so a malformed data file can't inject markup.
function clean(it) {
  return {
    ...it,
    category: CATS.includes(it.category) ? it.category : 'society',
    lang: it.lang === 'ar' ? 'ar' : 'en',
    impact: Math.min(5, Math.max(1, Math.round(Number(it.impact)) || 1)),
    echo: Math.max(1, Math.round(Number(it.echo)) || 1),
  };
}

export function matches(it, q) {
  if (!q) return true;
  return [it.title, it.title_ar, it.title_en, it.summary, it.summary_ar, it.summary_en, it.source_name, it.org]
    .filter(Boolean).join(' ').toLowerCase().includes(q);
}
