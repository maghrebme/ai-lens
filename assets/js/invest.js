// Ai-Lens — the investment track: a vertical rail of verified deals grouped by
// year, newest first, with the amount set large beside each card.

import {
  $, esc, safeUrl, state, T, chipGroup, initChrome, fmtDate, loadNews, matches,
} from './common.js';
import { orgsOf, timelineHidden, newsHidden, initSources } from './sources.js';

const TYPES = ['funding', 'acquisition', 'strategic', 'infrastructure', 'public', 'market', 'ipo'];
const REGIONS = ['us', 'europe', 'china', 'gulf', 'northafrica', 'other'];
const TYPE_COLOR = {
  funding: 'var(--c-models)', acquisition: 'var(--c-products)', strategic: 'var(--c-research)',
  infrastructure: 'var(--c-business)', public: 'var(--c-policy)', market: 'var(--c-society)', ipo: 'var(--c-products)',
};
const DEAL_WORDS = /\b(raises?|raised|funding round|valuation|valued at|acquires?|acquired|acquisition|invests?|investment in|ipo|series [a-h])\b|جولة تمويل|تمويل|استحواذ|تستحوذ|يستحوذ|تستثمر|يستثمر|طرح عام|بتقييم/i;

const view = { all: [], feeds: [], news: [], types: new Set(), regions: new Set(), q: '' };

// "$6.6B" in English; "6.6 مليار دولار" in Arabic (a bare "US$" reads poorly in RTL).
function money(n, cur) {
  if (state.lang === 'ar') {
    const num = new Intl.NumberFormat('ar-u-nu-latn', { notation: 'compact', maximumFractionDigits: 1 }).format(n);
    return `${num} ${{ EUR: 'يورو', MAD: 'درهم' }[cur] || 'دولار'}`;
  }
  return new Intl.NumberFormat('en-US', {
    style: 'currency', currency: cur || 'USD', notation: 'compact', maximumFractionDigits: 1,
  }).format(n);
}

function dateLabel(it) {
  if (it.precision === 'year') return '';
  return fmtDate(it._t, it.precision === 'month'
    ? { month: 'long', year: 'numeric', timeZone: 'UTC' }
    : { day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC' });
}

function title(it) { return state.lang === 'ar' ? it.title_ar : it.title_en; }
function summary(it) { return state.lang === 'ar' ? it.summary_ar : it.summary_en; }

// ── data ──────────────────────────────────────────────────────────────────
async function load() {
  const rows = await (await fetch('assets/data/investments.json')).json();
  view.all = rows.map((r, i) => ({ ...r, id: `d${i}`, title: r.title_en, _t: Date.parse(r.date) }))
    .sort((a, b) => b._t - a._t);
  try {
    const doc = await loadNews();
    view.feeds = doc.sources || [];
    view.news = doc.items;
  } catch { /* the track works without the news server */ }
}

function filtered() {
  const q = view.q.trim().toLowerCase();
  return view.all.filter((it) =>
    (!view.types.size || view.types.has(it.type))
    && (!view.regions.size || view.regions.has(it.region))
    && !timelineHidden(it)
    && matches(it, q));
}

// ── rendering ─────────────────────────────────────────────────────────────
function deal(it) {
  const t = T();
  const amount = it.amount
    ? `<span class="amt" dir="auto">${esc(money(it.amount, it.currency))}</span>`
    : it.valuation
      ? `<span class="amt" dir="auto">${esc(money(it.valuation, it.valuation_currency))}</span>${it.type === 'market' ? '' : `<small class="amt-cap">${esc(t.valuation)}</small>`}`
      : `<span class="amt none" title="${esc(t.undisclosed)}">—</span>`;
  const valuation = it.amount && it.valuation && it.type !== 'market'
    ? `<span class="val">${esc(t.valuation)}: <b>${esc(money(it.valuation, it.valuation_currency))}</b></span>` : '';
  const when = dateLabel(it);
  return `<article class="deal" style="--cat:${TYPE_COLOR[it.type]}">
    <div class="deal-amt">${amount}</div>
    <span class="deal-dot" aria-hidden="true"></span>
    <div class="deal-card">
      <p class="deal-meta"><span class="cat">${esc(t.types[it.type])}</span>${when ? `<span>${esc(when)}</span>` : ''}<span>${esc(t.regions[it.region] || '')}</span></p>
      <h3 class="deal-title">${esc(title(it))}</h3>
      <p class="deal-sum">${esc(summary(it))}</p>
      <p class="deal-foot"><span class="deal-org">${esc(orgsOf(it).map((o) => t.orgs[o] || o).join(' · '))}</span>${valuation}
        ${it.link ? `<a href="${esc(safeUrl(it.link))}" target="_blank" rel="noopener noreferrer">${esc(t.source)} ↗</a>` : ''}</p>
    </div>
  </article>`;
}

function render() {
  const items = filtered();
  $('#count').textContent = T().deals(items.length);
  if (!items.length) { $('#track').innerHTML = `<p class="empty">${esc(T().empty)}</p>`; return; }
  let html = '', year = null;
  for (const it of items) {
    const y = new Date(it._t).getUTCFullYear();
    if (y !== year) {
      if (year !== null) html += '</div>';
      const n = items.filter((x) => new Date(x._t).getUTCFullYear() === y).length;
      html += `<div class="year-block"><h2 class="year-mark"><span>${y}</span><small>${esc(T().deals(n))}</small></h2>`;
      year = y;
    }
    html += deal(it);
  }
  $('#track').innerHTML = `${html}</div>`;
}

// Recent funding headlines from the live feed (last 7 days) — links only, not on the track.
function renderNewsDeals() {
  const week = Date.now() - 7 * 86400e3;
  const list = view.news.filter((n) => n._t >= week && !newsHidden(n)
    && DEAL_WORDS.test(n.title_ar || '') + DEAL_WORDS.test(n.title_en || '') + DEAL_WORDS.test(n.title) > 0)
    .slice(0, 8);
  $('#newsDeals').hidden = !list.length;
  $('#newsDealsList').innerHTML = list.map((n) => {
    const t = (state.lang === 'ar' && n.title_ar) || (state.lang === 'en' && n.title_en) || n.title;
    return `<li><a href="${esc(safeUrl(n.url))}" target="_blank" rel="noopener noreferrer"><span dir="auto">${esc(t)}</span>
      <small>${esc(n.source_name)} · ${esc(fmtDate(n._t, { day: 'numeric', month: 'short' }))}</small></a></li>`;
  }).join('');
}

let renderTypeChips, renderRegionChips, sources;
function buildFilters() {
  const count = (pred) => view.all.filter(pred).length;
  renderTypeChips = chipGroup($('#typeChips'),
    TYPES.filter((ty) => count((it) => it.type === ty)).map((ty) => ({
      value: ty, label: T().types[ty], color: TYPE_COLOR[ty], count: count((it) => it.type === ty),
    })), view.types, render);
  renderRegionChips = chipGroup($('#regionChips'),
    REGIONS.map((r) => ({ value: r, label: T().regions[r], count: count((it) => it.region === r) })),
    view.regions, render);
}

async function boot() {
  initChrome('invest', (what) => {
    if (what === 'lang') { renderTypeChips(); renderRegionChips(); render(); renderNewsDeals(); sources.refresh(); }
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
    onChange: () => { render(); renderNewsDeals(); },
  });
  render();
  renderNewsDeals();
  let qTimer;
  $('#search').addEventListener('input', (e) => {
    clearTimeout(qTimer);
    qTimer = setTimeout(() => { view.q = e.target.value; render(); }, 150);
  });
}

boot();
