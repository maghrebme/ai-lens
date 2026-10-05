// Ai-Lens — the sources reference: a footer button opens a dialog listing every
// organisation behind the timeline and every news feed, each with a checkbox.
// Unticked sources are hidden on both pages and remembered in this browser.

import { $, esc, safeUrl, T } from './common.js';

export const ORG_ALIASES = { 'Google AI': 'Google', 'Google DeepMind': 'Google', DeepMind: 'Google' };
export const orgsOf = (it) => it.org.split(' · ').map((o) => ORG_ALIASES[o] || o);

const ORG_GROUPS = {
  gulf: ['TII', 'MBZUAI', 'IFM', 'G42', 'UAE', 'Saudi Arabia'],
  northafrica: ['Morocco', 'Egypt', 'Nexus Core Systems', 'Hassan Allam Utilities', 'A15'],
  gov: ['EU', 'China', 'US', 'UK', 'Japan', 'France', 'Governments', 'Vatican', 'United Nations', 'UNESCO'],
  research: ['Academia', 'SRI', 'Bell Labs', 'Future of Life Institute', 'Nobel'],
};
const groupOf = (o) => Object.keys(ORG_GROUPS).find((g) => ORG_GROUPS[g].includes(o)) || 'companies';

const KEYS = { orgs: 'lens.exOrgs', feeds: 'lens.exFeeds' };
const read = (k) => { try { return new Set(JSON.parse(localStorage.getItem(k) || '[]')); } catch { return new Set(); } };
const excluded = { orgs: read(KEYS.orgs), feeds: read(KEYS.feeds) };
function save() {
  try {
    localStorage.setItem(KEYS.orgs, JSON.stringify([...excluded.orgs]));
    localStorage.setItem(KEYS.feeds, JSON.stringify([...excluded.feeds]));
  } catch { /* private mode: the choice lasts for this page only */ }
}

// A milestone disappears only when every organisation behind it is unticked;
// a launch picked up from the news also follows its feed.
export function timelineHidden(it) {
  if (it.live && excluded.feeds.has(it.source)) return true;
  return orgsOf(it).every((o) => excluded.orgs.has(o));
}
export const newsHidden = (it) => excluded.feeds.has(it.source);

const orgName = (o) => T().orgs[o] || o;

/**
 * Wire the footer button. `getOrgs()` → [{name, count}], `getFeeds()` →
 * [{id, name, lang, url, count, ok}]; `onChange()` re-renders the page.
 */
export function initSources({ getOrgs, getFeeds, onChange }) {
  const btn = $('#sourcesBtn');
  const dlg = document.createElement('dialog');
  dlg.id = 'srcDialog';
  dlg.className = 'src-dialog';
  dlg.setAttribute('aria-labelledby', 'srcTitle');
  document.body.append(dlg);

  const label = () => {
    const t = T();
    const n = getOrgs().length + getFeeds().length;
    const off = excluded.orgs.size + excluded.feeds.size;
    btn.textContent = `${t.srcButton} · ${n}`;
    $('#sourcesNote').textContent = off ? t.srcExcluded(off) : '';
  };

  const item = (kind, value, name, count, extra = '') => `<li><label>
      <input type="checkbox" data-kind="${kind}" value="${esc(value)}" ${excluded[kind].has(value) ? '' : 'checked'}>
      <span class="src-name">${name}</span>${extra}<small>${count}</small></label></li>`;

  const render = () => {
    const t = T();
    const orgs = getOrgs(), feeds = getFeeds();
    const groups = ['companies', 'research', 'gulf', 'northafrica', 'gov'].map((g) => {
      const list = orgs.filter((o) => groupOf(o.name) === g);
      return list.length ? `<div class="src-group"><h4>${esc(t.srcGroups[g])}</h4><ul class="src-list">${
        list.map((o) => item('orgs', o.name, esc(orgName(o.name)), o.count)).join('')}</ul></div>` : '';
    }).join('');
    const feedList = feeds.map((f) => item('feeds', f.id,
      `<span lang="${f.lang === 'ar' ? 'ar' : 'en'}">${esc(f.name)}</span>`, Number(f.count) || 0,
      `<span class="src-lang">${f.lang === 'ar' ? 'ع' : 'EN'}</span>${f.ok === false ? `<span class="src-down" title="${esc(t.srcDown)}">●</span>` : ''}
       ${f.url ? `<a class="src-link" href="${esc(safeUrl(f.url))}" target="_blank" rel="noopener noreferrer" title="RSS">↗</a>` : ''}`)).join('');
    dlg.innerHTML = `
      <div class="src-head">
        <h2 id="srcTitle">${esc(t.srcTitle)}</h2>
        <button type="button" class="icon-btn" data-act="close" aria-label="${esc(t.close)}">✕</button>
      </div>
      <p class="src-intro">${esc(t.srcIntro)}</p>
      <section class="src-sec" data-kind="orgs">
        <div class="src-sec-head"><h3>${esc(t.srcTimeline)} <small>${orgs.length}</small></h3>
          <span><button type="button" class="link-btn" data-act="all">${esc(t.selectAll)}</button> · <button type="button" class="link-btn" data-act="none">${esc(t.selectNone)}</button></span></div>
        <p class="src-sub">${esc(t.srcTimelineSub)}</p>
        ${groups}
      </section>
      <section class="src-sec" data-kind="feeds">
        <div class="src-sec-head"><h3>${esc(t.srcFeeds)} <small>${feeds.length}</small></h3>
          <span><button type="button" class="link-btn" data-act="all">${esc(t.selectAll)}</button> · <button type="button" class="link-btn" data-act="none">${esc(t.selectNone)}</button></span></div>
        <p class="src-sub">${esc(t.srcFeedsSub)}</p>
        <ul class="src-list">${feedList}</ul>
      </section>
      <div class="src-foot"><button type="button" class="btn primary" data-act="close">${esc(t.done)}</button></div>`;
  };

  dlg.addEventListener('change', (e) => {
    const cb = e.target.closest('input[type=checkbox]');
    if (!cb) return;
    const set = excluded[cb.dataset.kind];
    if (cb.checked) set.delete(cb.value); else set.add(cb.value);
    save(); label(); onChange();
  });
  dlg.addEventListener('click', (e) => {
    if (e.target === dlg) { dlg.close(); return; }
    const act = e.target.closest('[data-act]')?.dataset.act;
    if (act === 'close') dlg.close();
    if (act === 'all' || act === 'none') {
      const sec = e.target.closest('.src-sec');
      const kind = sec.dataset.kind;
      sec.querySelectorAll('input[type=checkbox]').forEach((cb) => {
        cb.checked = act === 'all';
        if (act === 'all') excluded[kind].delete(cb.value); else excluded[kind].add(cb.value);
      });
      save(); label(); onChange();
    }
  });
  btn.addEventListener('click', () => { render(); dlg.showModal(); });

  label();
  // A link ending in #sources opens the reference straight away.
  if (location.hash === '#sources') { render(); dlg.showModal(); }
  return { refresh: () => { label(); if (dlg.open) render(); } };
}
