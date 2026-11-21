"""Shared PhaseWorld developer interface design system for every page the bot serves.

A quiet, high-contrast monochrome developer interface: structured like technical
documentation, with warm near-black surfaces, measured typography, hairline dividers,
and colour reserved for semantic status only.
"""

from __future__ import annotations

from html import escape

from config.settings import settings

ICON_URL = "https://cdn.phaseworld.top/purpurite/SekaiBot.png"
DEFAULT_DESCRIPTION = (
    f"{settings.bot_name} — moderation, tickets, music, levels, giveaways and "
    "website verification in one Discord prefix bot."
)

FONT_LINKS = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">\n'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
    '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
    "family=Instrument+Sans:wght@400;500;600&amp;family=JetBrains+Mono:wght@400;500&amp;"
    'display=swap">'
)

BASE_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Instrument+Sans:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap');

:root {
  /* Dark theme — default */
  --bg: #141415;
  --bg-deep: #0f0f10;
  --bg-2: #19191b;
  --bg-3: #232325;
  --line: rgba(237, 237, 237, 0.08);
  --line-2: rgba(237, 237, 237, 0.16);
  --fg: #ededed;
  --fg-2: #a1a1a6;
  --fg-3: #85858b;

  --signal: #4cc38a;
  --warning: #d4a72c;
  --danger: #e5484d;
  --selection-bg: #ededed;
  --selection-fg: #141415;

  --font-display: 'Instrument Sans', 'Inter', system-ui, -apple-system, sans-serif;
  --font-body: 'Instrument Sans', 'Inter', system-ui, -apple-system, sans-serif;
  --font-mono: 'JetBrains Mono', 'Fira Code', ui-monospace, 'Cascadia Code', Consolas, monospace;

  --side: 264px;
  --gutter: clamp(24px, 4vw, 40px);
  --measure: 64ch;
  --radius-sm: 6px;
  --radius: 10px;
  --radius-lg: 16px;
  --ease: cubic-bezier(0.22, 1, 0.36, 1);
  --shadow: 0 24px 64px rgba(0, 0, 0, 0.6);
  --overlay: rgba(0, 0, 0, 0.72);
  color-scheme: dark;
}

[data-theme='light'] {
  --bg: #fafafa;
  --bg-deep: #f4f4f5;
  --bg-2: #ffffff;
  --bg-3: #e9e9ea;
  --line: rgba(23, 23, 23, 0.08);
  --line-2: rgba(23, 23, 23, 0.16);
  --fg: #171717;
  --fg-2: #525252;
  --fg-3: #737373;

  --signal: #16a34a;
  --warning: #a16207;
  --danger: #dc2626;
  --selection-bg: #171717;
  --selection-fg: #fafafa;
  --shadow: 0 20px 48px rgba(0, 0, 0, 0.14);
  --overlay: rgba(23, 23, 23, 0.32);
  color-scheme: light;
}

*, *::before, *::after { box-sizing: border-box; }
html {
  -webkit-text-size-adjust: 100%;
  scroll-behavior: smooth;
  scroll-padding-top: 32px;
}
body {
  margin: 0;
  min-height: 100vh;
  overflow-x: clip;
  background: var(--bg);
  color: var(--fg);
  font: 400 16px/1.65 var(--font-body);
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}
::selection { background: var(--selection-bg); color: var(--selection-fg); }
:focus-visible { outline: 2px solid var(--fg); outline-offset: 2px; }

h1, h2, h3, h4 {
  margin: 0;
  color: var(--fg);
  font-family: var(--font-display);
  font-weight: 500;
  line-height: 1.15;
  text-wrap: balance;
}
h1 { letter-spacing: -0.02em; line-height: 1.06; }
p { text-wrap: pretty; margin: 0; color: var(--fg-2); }

a {
  color: inherit;
  text-underline-offset: 3px;
  text-decoration-color: var(--line-2);
  transition: text-decoration-color 140ms var(--ease);
}
a:hover { text-decoration-color: var(--fg); }
img { display: block; max-width: 100%; }

/* Scrollbars */
* { scrollbar-width: thin; scrollbar-color: var(--fg-3) var(--bg-deep); }
::-webkit-scrollbar { width: 8px; height: 8px; }
::-webkit-scrollbar-track { background: var(--bg-deep); }
::-webkit-scrollbar-thumb { background: var(--fg-3); border-radius: 4px; border: 2px solid var(--bg-deep); }

.skip {
  position: absolute; left: -9999px; top: 0; z-index: 100;
  background: var(--bg-2); color: var(--fg); padding: 10px 16px;
  border: 1px solid var(--line-2); border-radius: var(--radius-sm);
  font: 500 14px var(--font-display); text-decoration: none;
}
.skip:focus { left: 16px; top: 16px; }

/* Desktop Persistent Sidebar */
.site-header {
  position: fixed; inset: 0 auto 0 0; z-index: 30;
  width: var(--side);
  border-right: 1px solid var(--line);
  background: var(--bg-deep);
}
.site-header .bar {
  height: 100%; padding: 28px 16px;
  display: flex; flex-direction: column; gap: 28px;
}
.brand {
  display: inline-flex; align-items: center; gap: 10px;
  text-decoration: none; color: var(--fg);
  font: 500 15px var(--font-display);
}
.brand-mark {
  width: 30px; height: 30px; display: grid; place-items: center;
  background: var(--fg); color: var(--bg);
  font: 500 13px var(--font-mono); border-radius: 4px; flex: none;
}
.site-nav { display: grid; gap: 2px; }
.site-nav a {
  height: 36px; display: flex; align-items: center; gap: 10px;
  padding: 0 8px; border-radius: 6px;
  color: var(--fg-2); font: 500 14px var(--font-display);
  text-decoration: none;
  transition: background-color 140ms var(--ease), color 140ms var(--ease), box-shadow 140ms var(--ease);
}
.site-nav a svg {
  width: 16px; height: 16px; flex: none; color: var(--fg-3);
  transition: color 140ms var(--ease);
}
.site-nav a:hover {
  background: var(--bg-3); color: var(--fg);
}
.site-nav a:hover svg { color: var(--fg); }
.site-nav a[aria-current='page'] {
  background: var(--bg-3); box-shadow: inset 0 0 0 1px var(--line);
  color: var(--fg);
}
.site-nav a[aria-current='page'] svg { color: var(--fg); }

/* Theme toggle button */
.theme-toggle {
  height: 32px; margin-top: auto; padding: 0 10px;
  border: 1px solid transparent; border-radius: var(--radius-sm);
  background: transparent; color: var(--fg-3);
  font: 400 12px var(--font-mono); text-align: left;
  cursor: pointer; display: inline-flex; align-items: center; gap: 8px;
  transition: background-color 140ms var(--ease), color 140ms var(--ease), border-color 140ms var(--ease);
}
.theme-toggle:hover {
  background: var(--bg-3); color: var(--fg); border-color: var(--line);
}

/* Mobile 52px Sticky Top Bar & Off-canvas Drawer */
.site-topbar {
  display: none;
  position: sticky; top: 0; z-index: 40;
  width: 100%; height: 52px;
  padding: 0 16px;
  border-bottom: 1px solid var(--line);
  background: var(--bg-deep);
  align-items: center; justify-content: space-between;
}
.site-topbar .brand { font-size: 14px; }
.topbar-actions { display: flex; align-items: center; gap: 8px; }
.drawer-toggle {
  width: 36px; height: 36px; display: grid; place-items: center;
  background: var(--bg-2); border: 1px solid var(--line-2);
  border-radius: var(--radius-sm); color: var(--fg); cursor: pointer;
  padding: 0;
  transition: background-color 140ms var(--ease);
}
.drawer-toggle:hover { background: var(--bg-3); }

.drawer-backdrop {
  display: none; position: fixed; inset: 0; z-index: 50;
  background: var(--overlay); opacity: 0; pointer-events: none;
  transition: opacity 160ms var(--ease);
}
.drawer-backdrop.active {
  display: block; opacity: 1; pointer-events: auto;
}
.site-drawer {
  position: fixed; inset: 0 auto 0 0; z-index: 60;
  width: min(300px, 84vw); height: 100%;
  background: var(--bg-deep); border-right: 1px solid var(--line);
  padding: 20px 16px; display: flex; flex-direction: column; gap: 24px;
  transform: translateX(-100%);
  transition: transform 220ms var(--ease);
  box-shadow: var(--shadow);
}
.site-drawer.open {
  transform: translateX(0);
}
.drawer-head {
  display: flex; align-items: center; justify-content: space-between;
}
.drawer-close {
  width: 32px; height: 32px; display: grid; place-items: center;
  background: transparent; border: 1px solid var(--line);
  border-radius: var(--radius-sm); color: var(--fg-2); cursor: pointer;
}
.drawer-close:hover { background: var(--bg-3); color: var(--fg); }

/* Document Shell & Columns */
.shell {
  width: calc(100% - var(--side));
  max-width: calc(1360px + var(--gutter) * 2);
  margin-left: var(--side);
  padding: 48px var(--gutter) 96px;
}
main.shell { min-height: calc(100vh - 120px); }

/* In-page Document Layout (flexible content + 176px sticky TOC) */
.doc-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 176px;
  gap: 48px;
  align-items: start;
}
.doc-content { min-width: 0; }
.doc-toc {
  position: sticky; top: 48px;
  display: grid; gap: 6px;
  padding-left: 14px;
  border-left: 1px solid var(--line);
}
.doc-toc-title {
  color: var(--fg-3); font: 400 11px var(--font-mono);
  letter-spacing: 0.02em;
  margin-bottom: 6px;
}
.doc-toc a {
  display: block; color: var(--fg-3);
  font: 400 13px var(--font-display);
  text-decoration: none; padding: 3px 0;
  transition: color 140ms var(--ease);
}
.doc-toc a:hover { color: var(--fg); }

/* Spacing Rhythm & Typography Scale */
.eyebrow {
  margin-bottom: 20px;
  color: var(--fg-3);
  font: 400 12px var(--font-mono);
}
.section-label {
  margin-bottom: 12px;
  color: var(--fg-3);
  font: 400 12px var(--font-mono);
}
.section { margin-top: 80px; }
.section-head {
  display: flex; align-items: flex-end; justify-content: space-between;
  gap: 24px; flex-wrap: wrap; margin-bottom: 24px;
}
h2.section-title { font-size: clamp(1.35rem, 2vw, 1.5rem); font-weight: 500; }
.section-note { max-width: 48ch; color: var(--fg-3); font-size: 14px; }

.page-title {
  font-size: clamp(2rem, 2.8vw, 2.75rem);
  font-weight: 500;
  letter-spacing: -0.02em;
  line-height: 1.06;
  margin-bottom: 20px;
}
.page-lede {
  max-width: 48ch;
  font-size: 17px;
  line-height: 1.6;
  color: var(--fg-2);
  margin-bottom: 24px;
}
.prose { max-width: var(--measure); }
.prose p + p { margin-top: 14px; }

/* Buttons & Controls (modest, rectangular, never pill-shaped) */
.button, .btn {
  display: inline-flex; align-items: center; justify-content: center; gap: 8px;
  height: 40px; padding: 0 16px;
  border: 1px solid var(--line-2);
  border-radius: var(--radius-sm);
  background: var(--bg-2);
  color: var(--fg);
  font: 500 14px var(--font-display);
  text-decoration: none; cursor: pointer; white-space: nowrap;
  transition: background-color 140ms var(--ease), border-color 140ms var(--ease), color 140ms var(--ease);
}
.button:hover, .btn:hover { background: var(--bg-3); }
.button--primary, .btn.primary {
  background: var(--fg); border-color: var(--fg); color: var(--bg);
}
.button--primary:hover, .btn.primary:hover {
  background: var(--fg-2); border-color: var(--fg-2); color: var(--bg);
}
.button--compact, .btn.compact {
  height: 32px; padding: 0 10px; font-size: 13px;
  background: transparent;
}
.button--compact:hover, .btn.compact:hover { background: var(--bg-3); }
.button--ghost, .btn.ghost {
  background: transparent; border-color: var(--line-2);
}
.button--ghost:hover, .btn.ghost:hover { background: var(--bg-3); }
.button.block, .btn.block { width: 100%; }

/* Input fields */
.field, input[type='text'], input[type='search'], input[type='password'] {
  height: 40px; padding: 0 12px;
  border: 1px solid var(--line-2);
  border-radius: var(--radius-sm);
  background: var(--bg-2);
  color: var(--fg);
  font: 400 15px var(--font-body);
  transition: border-color 140ms var(--ease);
}
.field::placeholder, input::placeholder { color: var(--fg-3); }
.field:focus, input:focus { outline: none; border-color: var(--fg-2); }

/* Mono keys & badges */
kbd, .kbd {
  display: inline-flex; align-items: center; justify-content: center;
  padding: 2px 6px; border: 1px solid var(--line-2); border-radius: 4px;
  background: var(--bg-2); color: var(--fg-3);
  font: 400 11px var(--font-mono); line-height: 1;
}

/* Status dots & indicators (colour reserved for semantic status only) */
.dot {
  width: 8px; height: 8px; flex: none; border-radius: 50%;
  background: var(--fg-3);
}
.dot.ok, .dot.signal { background: var(--signal); }
.dot.warn, .dot.warning { background: var(--warning); }
.dot.bad, .dot.danger { background: var(--danger); }

.pill {
  display: inline-flex; align-items: center; gap: 8px;
  padding: 4px 10px; border: 1px solid var(--line);
  border-radius: var(--radius-sm); background: var(--bg-2);
  color: var(--fg-2); font: 400 12px var(--font-mono);
}
.dev-tag {
  display: inline-flex; align-items: center;
  padding: 3px 6px; border: 1px solid var(--line-2);
  border-radius: 4px; color: var(--fg-3);
  font: 400 11px var(--font-mono);
}

/* Segmented Stat Group (gap: 1px, background: var(--line), cells: --bg-2) */
.stat-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
  gap: 1px;
  overflow: hidden;
  border: 1px solid var(--line);
  border-radius: var(--radius);
  background: var(--line);
}
.stat {
  min-height: 120px; padding: 18px 20px;
  background: var(--bg-2);
  transition: background-color 140ms var(--ease);
}
.stat:hover { background: var(--bg-3); }
.stat-label { color: var(--fg-3); font: 400 11px var(--font-mono); margin: 0; }
.stat-value {
  margin-top: 8px; color: var(--fg);
  font: 500 24px var(--font-mono);
  font-variant-numeric: tabular-nums;
  letter-spacing: -0.02em;
  overflow-wrap: anywhere;
}
.stat-sub { margin-top: 4px; color: var(--fg-3); font-size: 12px; }

/* Ordinary cards */
.card {
  padding: 20px 24px;
  border: 1px solid var(--line);
  border-radius: var(--radius);
  background: var(--bg-2);
}
.card-head {
  display: flex; align-items: center; justify-content: space-between;
  gap: 12px; margin-bottom: 14px;
}
.card-title { font: 500 15px var(--font-display); }
.card-note { color: var(--fg-3); font: 400 12px var(--font-mono); }
.card-body { display: grid; gap: 12px; }

/* Portrait/Identity card (16px radius and stronger line-2 border) */
.identity-card {
  padding: 24px;
  border: 1px solid var(--line-2);
  border-radius: var(--radius-lg);
  background: var(--bg-2);
}

/* Code blocks (bg-2, line, 10px radius, 24px padding, JetBrains Mono 13px / 1.8) */
pre, code.block {
  margin: 0;
  padding: 20px 24px;
  border: 1px solid var(--line);
  border-radius: var(--radius);
  background: var(--bg-2);
  color: var(--fg);
  font: 400 13px/1.8 var(--font-mono);
  overflow-x: auto;
}
code {
  padding: 2px 5px;
  border: 1px solid var(--line);
  border-radius: 4px;
  background: var(--bg-2);
  color: var(--fg);
  font: 400 0.88em var(--font-mono);
}

/* Hairline Lists & Dividers (top 1px solid var(--line), 20px 0 padding, bottom rule) */
.rule-list {
  border-top: 1px solid var(--line);
}
.rule-row {
  display: flex; align-items: center; justify-content: space-between;
  gap: 16px; padding: 18px 0;
  border-bottom: 1px solid var(--line);
  transition: background-color 140ms var(--ease);
}

/* Key-Value Rows */
.kv { display: grid; }
.kv-row {
  display: flex; align-items: baseline; justify-content: space-between;
  gap: 16px; padding: 10px 0;
  border-bottom: 1px solid var(--line);
  font-size: 14px;
}
.kv-row:last-child { border-bottom: 0; }
.kv-k { color: var(--fg-2); }
.kv-v {
  color: var(--fg); font: 400 12px var(--font-mono);
  font-variant-numeric: tabular-nums;
  overflow-wrap: anywhere; text-align: right;
}

/* Meter */
.meter { display: grid; gap: 6px; }
.meter-head {
  display: flex; justify-content: space-between; gap: 12px;
  color: var(--fg-2); font-size: 13px;
}
.meter-head .mono { color: var(--fg); }
.meter-track { height: 6px; overflow: hidden; background: var(--bg-3); border-radius: 2px; }
.meter-fill {
  width: 0; height: 100%; background: var(--fg-2);
  transition: width 140ms var(--ease), background-color 140ms var(--ease);
}

/* Callout / Quotation (1px left rule, 24px left padding, 20px medium sentence) */
.callout {
  border-left: 1px solid var(--line-2);
  padding-left: 24px;
  color: var(--fg);
  font: 500 20px/1.45 var(--font-display);
}

/* Utility classes */
.grid-2 { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 16px; }
.grid-3 { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 16px; }
.stack { display: grid; gap: 12px; }
.ok { color: var(--signal); }
.warn { color: var(--warning); }
.bad { color: var(--danger); }
.muted { color: var(--fg-3); }
.mono { font-family: var(--font-mono); font-variant-numeric: tabular-nums; }
.nowrap { white-space: nowrap; }
.sr-only {
  position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px;
  overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; border: 0;
}
.banner {
  display: none; align-items: center; gap: 10px;
  margin-bottom: 24px; padding: 12px 16px;
  border: 1px solid var(--line-2);
  border-radius: var(--radius-sm);
  background: var(--bg-2);
  color: var(--fg); font-size: 14px;
}
.banner.show { display: flex; }
.empty {
  padding: 24px; border: 1px dashed var(--line-2);
  border-radius: var(--radius-sm); color: var(--fg-3);
  font: 400 13px var(--font-mono); text-align: center;
}
.chips { display: flex; flex-wrap: wrap; gap: 8px; }
.chip {
  padding: 4px 8px; border: 1px solid var(--line);
  border-radius: 4px; background: var(--bg-2);
  color: var(--fg-2); font: 400 12px var(--font-mono);
}

/* Footer */
.site-footer {
  width: calc(100% - var(--side));
  max-width: calc(1360px + var(--gutter) * 2);
  margin-left: var(--side);
  padding: 32px var(--gutter) 48px;
  border-top: 1px solid var(--line);
}
.site-footer .inner {
  display: flex; align-items: center; justify-content: space-between;
  gap: 16px; flex-wrap: wrap;
  color: var(--fg-3); font: 400 13px var(--font-body);
}
.site-footer nav { display: flex; gap: 16px; flex-wrap: wrap; }
.site-footer a { color: var(--fg-2); text-decoration: none; }
.site-footer a:hover { color: var(--fg); }

/* Responsive adjustments */
@media (max-width: 1120px) {
  .doc-layout { display: block; }
  .doc-toc { display: none; }
}

@media (max-width: 1024px) {
  .site-header { display: none; }
  .site-topbar { display: flex; }
  .shell, .site-footer {
    width: 100%; margin-left: 0;
  }
}

@media (max-width: 900px) {
  .grid-2 { grid-template-columns: 1fr; }
}

@media (max-width: 780px) {
  .grid-3 { grid-template-columns: 1fr; }
}

@media (max-width: 860px) {
  .section { margin-top: 64px; }
  main.shell { padding-top: 36px; }
}

@media (max-width: 560px) {
  .shell { padding-left: 16px; padding-right: 16px; }
  .site-footer { padding-left: 16px; padding-right: 16px; }
  .card { padding: 16px; }
  .stat { padding: 14px 16px; }
  .stat-value { font-size: 21px; }
  .page-title { font-size: 2rem; }
}

/* Reduced motion preference */
@media (prefers-reduced-motion: reduce) {
  html { scroll-behavior: auto; }
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
  }
}
"""

MOTION_JS = """
<script>
(() => {
  const root = document.documentElement;
  const toggles = document.querySelectorAll('[data-theme-toggle]');
  let saved = null;
  try { saved = localStorage.getItem('purpurite-theme'); } catch (_) {}
  if (saved === 'light' || saved === 'dark') {
    root.dataset.theme = saved;
  } else if (window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches) {
    root.dataset.theme = 'light';
  }

  const sync = () => {
    const isLight = root.dataset.theme === 'light';
    toggles.forEach((t) => {
      t.textContent = isLight ? 'Use dark mode' : 'Use light mode';
      t.setAttribute('aria-pressed', String(isLight));
    });
  };

  toggles.forEach((t) => {
    t.addEventListener('click', () => {
      root.dataset.theme = root.dataset.theme === 'light' ? 'dark' : 'light';
      try { localStorage.setItem('purpurite-theme', root.dataset.theme); } catch (_) {}
      sync();
    });
  });
  sync();

  // Mobile Drawer Toggle
  const drawer = document.getElementById('site-drawer');
  const backdrop = document.getElementById('drawer-backdrop');
  const openBtn = document.querySelector('[data-drawer-toggle]');
  const closeBtn = document.querySelector('[data-drawer-close]');

  const closeDrawer = () => {
    if (!drawer) return;
    drawer.classList.remove('open');
    if (backdrop) backdrop.classList.remove('active');
    if (openBtn) openBtn.setAttribute('aria-expanded', 'false');
  };

  const openDrawer = () => {
    if (!drawer) return;
    drawer.classList.add('open');
    if (backdrop) backdrop.classList.add('active');
    if (openBtn) openBtn.setAttribute('aria-expanded', 'true');
  };

  openBtn?.addEventListener('click', () => {
    const isOpen = drawer && drawer.classList.contains('open');
    if (isOpen) closeDrawer(); else openDrawer();
  });
  closeBtn?.addEventListener('click', closeDrawer);
  backdrop?.addEventListener('click', closeDrawer);

  window.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeDrawer();
  });
})();
</script>
"""

_NAV_ICONS: dict[str, str] = {
    "bot": (
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" '
        'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
        '<path d="M4 17l6-6-6-6M12 19h8"/></svg>'
    ),
    "status": (
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" '
        'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
        '<polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>'
    ),
    "tickets": (
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" '
        'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
        '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>'
        '<polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/>'
        '<line x1="16" y1="17" x2="8" y2="17"/></svg>'
    ),
    "verify": (
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" '
        'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
        '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>'
    ),
    "dashboard": (
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" '
        'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
        '<rect x="3" y="3" width="7" height="7" rx="1"/>'
        '<rect x="14" y="3" width="7" height="7" rx="1"/>'
        '<rect x="3" y="14" width="7" height="7" rx="1"/>'
        '<rect x="14" y="14" width="7" height="7" rx="1"/></svg>'
    ),
}


def _site_url(active: str) -> str:
    return {
        "bot": settings.website_url,
        "status": settings.status_url,
        "tickets": settings.transcript_url,
        "verify": settings.verify_base_url or settings.website_url,
        "dashboard": settings.dashboard_url,
    }.get(active, settings.website_url)


def _meta(*, title: str, description: str, url: str, image: str) -> str:
    name = escape(settings.bot_name, quote=True)
    heading = escape(title, quote=True)
    text = escape(description, quote=True)
    link = escape(url, quote=True)
    asset = escape(image, quote=True)
    tags = (
        f'<meta name="description" content="{text}">',
        f'<link rel="canonical" href="{link}">',
        '<meta name="theme-color" content="#141415" media="(prefers-color-scheme: dark)">',
        '<meta name="theme-color" content="#fafafa" media="(prefers-color-scheme: light)">',
        f'<link rel="icon" type="image/png" href="{asset}">',
        f'<link rel="apple-touch-icon" href="{asset}">',
        '<meta property="og:type" content="website">',
        f'<meta property="og:site_name" content="{name}">',
        f'<meta property="og:title" content="{heading}">',
        f'<meta property="og:description" content="{text}">',
        f'<meta property="og:url" content="{link}">',
        f'<meta property="og:image" content="{asset}">',
        f'<meta property="og:image:alt" content="{name} icon">',
        '<meta name="twitter:card" content="summary">',
        f'<meta name="twitter:title" content="{heading}">',
        f'<meta name="twitter:description" content="{text}">',
        f'<meta name="twitter:image" content="{asset}">')
    return "\n".join(tags)


def _links() -> list[tuple[str, str, str]]:
    verify = settings.verify_base_url or settings.website_url
    return [
        ("bot", "Bot", settings.website_url),
        ("status", "Status", settings.status_url),
        ("tickets", "Tickets", settings.transcript_url),
        ("verify", "Verify", verify),
        ("dashboard", "Dashboard", settings.dashboard_url),
    ]


def nav(active: str = "") -> str:
    items = []
    for key, label, url in _links():
        marker = ' aria-current="page"' if key == active else ""
        icon = _NAV_ICONS.get(key, "")
        items.append(
            f'<a href="{escape(url, quote=True)}"{marker}>{icon}<span>{escape(label)}</span></a>'
        )
    return f'<nav class="site-nav" aria-label="Navigation">{"".join(items)}</nav>'


def header(active: str = "", *, theme_control: bool = True) -> str:
    name = escape(settings.bot_name)
    initial = escape(settings.bot_name[:1].upper() or "P")
    theme_btn = (
        '<button class="theme-toggle" type="button" data-theme-toggle '
        'aria-pressed="false">Use light mode</button>'
        if theme_control
        else ""
    )
    hamburger_icon = (
        '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" '
        'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
        '<line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/>'
        '<line x1="3" y1="18" x2="21" y2="18"/></svg>'
    )
    close_icon = (
        '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" '
        'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
        '<line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>'
    )

    desktop_sidebar = (
        '<header class="site-header"><div class="bar">'
        f'<a class="brand" href="{escape(settings.website_url, quote=True)}">'
        f'<span class="brand-mark" aria-hidden="true">{initial}</span>'
        f"<span>{name}</span></a>"
        f"{nav(active)}"
        f"{theme_btn}"
        "</div></header>"
    )

    mobile_topbar = (
        '<div class="site-topbar">'
        f'<a class="brand" href="{escape(settings.website_url, quote=True)}">'
        f'<span class="brand-mark" aria-hidden="true">{initial}</span>'
        f"<span>{name}</span></a>"
        '<div class="topbar-actions">'
        + (
            '<button class="theme-toggle" type="button" data-theme-toggle '
            'aria-pressed="false" style="margin:0;height:36px;padding:0 8px;">Theme</button>'
            if theme_control
            else ""
        )
        + f'<button class="drawer-toggle" type="button" aria-label="Toggle navigation drawer" aria-expanded="false" data-drawer-toggle>{hamburger_icon}</button>'
        "</div></div>"
    )

    drawer = (
        '<div class="drawer-backdrop" id="drawer-backdrop"></div>'
        '<aside class="site-drawer" id="site-drawer" aria-label="Mobile navigation">'
        '<div class="drawer-head">'
        f'<a class="brand" href="{escape(settings.website_url, quote=True)}">'
        f'<span class="brand-mark" aria-hidden="true">{initial}</span>'
        f"<span>{name}</span></a>"
        f'<button class="drawer-close" type="button" aria-label="Close navigation" data-drawer-close>{close_icon}</button>'
        "</div>"
        f"{nav(active)}"
        f"{theme_btn}"
        "</aside>"
    )

    return desktop_sidebar + mobile_topbar + drawer


def footer() -> str:
    name = escape(settings.bot_name)
    owner = escape(settings.owner_name)
    base = settings.website_url.rstrip("/")
    return (
        '<footer class="site-footer"><div class="inner">'
        f"<span>{name} · built by {owner}</span>"
        '<nav aria-label="Related links">'
        '<a href="/health">Health</a>'
        f'<a href="{escape(base + "/terms", quote=True)}">Terms</a>'
        f'<a href="{escape(base + "/privacy", quote=True)}">Privacy</a>'
        + "".join(
            f'<a href="{escape(url, quote=True)}">{escape(label)}</a>'
            for _, label, url in _links()
        )
        + "</nav></div></footer>"
    )


def toc_nav(items: list[tuple[str, str]]) -> str:
    """Render an in-page sticky table of contents (spec: 176px sticky TOC)."""
    links = "".join(
        f'<a href="#{escape(anchor, quote=True)}">{escape(title)}</a>'
        for anchor, title in items
    )
    return (
        '<nav class="doc-toc" aria-label="Table of contents">'
        '<div class="doc-toc-title">On this page</div>'
        f"{links}</nav>"
    )


def document(
    title: str,
    body: str,
    *,
    active: str = "",
    description: str | None = None,
    url: str | None = None,
    image: str = ICON_URL,
    extra_css: str = "",
    extra_head: str = "",
    fonts: bool = True,
    motion: bool = True,
    brand_header: bool = True,
    brand_footer: bool = True,
    toc: list[tuple[str, str]] | None = None) -> str:
    """Wrap page markup in the shared PhaseWorld documentation shell."""
    summary = description or DEFAULT_DESCRIPTION
    meta = _meta(
        title=title,
        description=summary,
        url=url or _site_url(active),
        image=image)
    head = [meta]
    if fonts:
        head.append(FONT_LINKS)
    if extra_head:
        head.append(extra_head)

    if toc:
        content_markup = (
            f'<div class="doc-layout">\n'
            f'<div class="doc-content">\n{body}\n</div>\n'
            f"{toc_nav(toc)}\n"
            f"</div>"
        )
    else:
        content_markup = body

    return (
        "<!doctype html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        '<meta name="color-scheme" content="dark light">\n'
        f"<title>{escape(title)}</title>\n"
        + "\n".join(head)
        + f"\n<style>\n{BASE_CSS}\n{extra_css}\n</style>\n"
        "</head>\n"
        "<body>\n"
        '<a class="skip" href="#main">Skip to content</a>\n'
        + (header(active, theme_control=motion) if brand_header else "")
        + f'\n<main id="main" class="shell">\n{content_markup}\n</main>\n'
        + (footer() if brand_footer else "")
        + (MOTION_JS if motion else "")
        + "\n</body>\n</html>"
    )
