// Ai-Lens — runs in <head> before the first paint: applies the saved (or
// system) theme and language so the page never flashes in the wrong one.
// Mirrors the logic in common.js; kept tiny and dependency-free.
(function () {
  var root = document.documentElement;
  var query = new URLSearchParams(location.search);
  var saved = {};
  try {
    saved.theme = localStorage.getItem('lens.theme');
    saved.lang = localStorage.getItem('lens.lang');
  } catch (e) { /* private mode: fall back to defaults */ }
  var theme = query.get('theme') || saved.theme
    || (matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark');
  if (theme === 'dark' || theme === 'light') root.setAttribute('data-theme', theme);
  if ((query.get('lang') || saved.lang) === 'en') {
    root.lang = 'en';
    root.dir = 'ltr';
  }
}());
