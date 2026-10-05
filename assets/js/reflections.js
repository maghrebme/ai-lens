// Ai-Lens — the Reflections essay: language switching between the Arabic and
// English texts, the audio debate player, reading time, reading progress and
// the "current section" highlight in the contents list.

import { $, state, T, isRtl, initChrome } from './common.js';

const AUDIO = { ar: 'assets/audio/debate-ar.m4a', en: 'assets/audio/debate-en.m4a', fr: 'assets/audio/debate-fr.m4a' };
const reduceMotion = matchMedia('(prefers-reduced-motion: reduce)').matches;

const visible = () => document.querySelector(`.essay[data-lang="${state.lang}"]`);

// Show the text that matches the interface language.
function showLanguage() {
  document.querySelectorAll('[data-lang]').forEach((el) => { el.hidden = el.dataset.lang !== state.lang; });
  const words = visible().textContent.trim().split(/\s+/).length;
  // Arabic reads slower per word than English.
  $('#readTime').textContent = T().readTime(Math.max(1, Math.round(words / (isRtl() ? 180 : 230))));
  document.querySelectorAll('[data-i18n="contents"]').forEach((el) => { el.textContent = T().contents; });
  observeSections();
  updateProgress();
}

// ── audio ─────────────────────────────────────────────────────────────────
function selectAudio(lang, { autoplay = false } = {}) {
  const audio = $('#debateAudio');
  const src = AUDIO[lang];
  if (!audio.src.endsWith(src)) {
    audio.pause();
    audio.src = src;
  }
  document.querySelectorAll('.listen-tabs [data-audio]').forEach((b) => {
    b.setAttribute('aria-selected', String(b.dataset.audio === lang));
  });
  if (autoplay) audio.play().catch(() => { /* the browser may require another tap */ });
}

// ── reading progress ──────────────────────────────────────────────────────
function updateProgress() {
  const body = visible()?.querySelector('.essay-body');
  if (!body) return;
  const r = body.getBoundingClientRect();
  const done = Math.min(1, Math.max(0, (innerHeight - r.top) / (r.height + innerHeight * 0.4)));
  $('#readProgress').style.transform = `scaleX(${done})`;
}

// ── current section in the contents list ──────────────────────────────────
let io;
function observeSections() {
  io?.disconnect();
  const essay = visible();
  const links = new Map([...essay.querySelectorAll('.essay-toc a')].map((a) => [a.getAttribute('href').slice(1), a]));
  io = new IntersectionObserver((entries) => {
    entries.forEach((e) => {
      if (!e.isIntersecting) return;
      links.forEach((a) => a.removeAttribute('aria-current'));
      links.get(e.target.id)?.setAttribute('aria-current', 'true');
    });
  }, { rootMargin: '-20% 0px -70% 0px' });
  essay.querySelectorAll('.essay-body h2[id]').forEach((h) => io.observe(h));
}

// The contents list is a sidebar on wide screens and a collapsed toggle on phones.
const wide = matchMedia('(min-width: 1280px)');
function syncToc() {
  document.querySelectorAll('.essay-toc').forEach((d) => { d.open = wide.matches; });
}

function boot() {
  syncToc();
  wide.addEventListener('change', syncToc);
  initChrome('reflections', (what) => {
    if (what === 'lang') {
      showLanguage();
      if ($('#debateAudio').paused) selectAudio(state.lang);
    }
  });
  showLanguage();
  selectAudio(state.lang);
  $('.listen-tabs').addEventListener('click', (e) => {
    const b = e.target.closest('[data-audio]');
    if (b) selectAudio(b.dataset.audio, { autoplay: true });
  });
  // Smooth scrolling for the contents links, without changing the URL hash history.
  document.addEventListener('click', (e) => {
    const a = e.target.closest('.essay-toc a');
    if (!a) return;
    e.preventDefault();
    document.getElementById(a.getAttribute('href').slice(1))
      ?.scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth', block: 'start' });
  });
  let raf = 0;
  addEventListener('scroll', () => { if (!raf) raf = requestAnimationFrame(() => { raf = 0; updateProgress(); }); }, { passive: true });
  addEventListener('resize', updateProgress);
}

boot();
