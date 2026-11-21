# PhaseWorld theme

Use this document to reproduce the visual language on another site. It is a **quiet, high-contrast monochrome developer interface**: structured like technical documentation, with warm near-black surfaces, measured typography, hairline dividers, and colour reserved for semantic status only.

## Non-negotiable design rules

- Default to dark mode; provide the companion light mode below.
- Use a neutral gray ramp for surfaces and typography. Do not introduce a brand accent, gradients, glass effects, glow, or decorative colour.
- Reserve green, amber, and red for live/success, warning, and failure states respectively. They are signals, not decoration.
- Prefer 1px rules, spacious columns, compact mono metadata, and low-contrast hover fills over heavy cards or shadows.
- Titles use a medium, not bold, weight. The page should feel precise and calm rather than loud or playful.
- Most content is presented as a document: an eyebrow, a title, a short lede, then sections separated by whitespace and hairlines.

## Fonts

Load these two families (or use the supplied fallback stacks):

```css
@import url('https://fonts.googleapis.com/css2?family=Instrument+Sans:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap');
```

| Use | Family | Weight / size |
| --- | --- | --- |
| Headings, controls, labels | Instrument Sans | Mostly `500` |
| Body copy | Instrument Sans | `400`, `16px`, `1.65` line-height |
| Code, keys, timestamps, metadata, section indices | JetBrains Mono | `400`, usually `11–13px` |

Use tabular figures for data and dates. Keep normal body text at `16px`; metadata should feel noticeably smaller, but stay legible. Large headings should have slight negative tracking (`-0.02em`) and a tight line-height.

## Design tokens

Copy this foundation into a global stylesheet. The names are intentionally semantic and portable.

```css
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
```

### Token roles

| Token | Apply to |
| --- | --- |
| `--bg` | Main page and modal backgrounds |
| `--bg-deep` | Persistent chrome: sidebar, mobile top bar |
| `--bg-2` | Inputs, cards, code blocks, raised panels |
| `--bg-3` | Hover, selected, and active fills |
| `--line` | Ordinary dividers and panel seams |
| `--line-2` | Button, input, and focused-control borders |
| `--fg` | Headings, key values, primary action fill |
| `--fg-2` | Body copy and secondary controls |
| `--fg-3` | Metadata, placeholders, labels, subdued icons |

## Global foundation

```css
*, *::before, *::after { box-sizing: border-box; }
html { scroll-behavior: smooth; scroll-padding-top: 32px; }
body {
  margin: 0;
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
p { text-wrap: pretty; }
```

## Layout

Desktop uses a fixed **264px sidebar** beside a document column. The main document has `48px var(--gutter) 96px` padding and a `1360px` maximum width. When an in-page table of contents is present, make the content area a two-column grid: flexible content + `176px` sticky TOC, separated by `48px`.

Keep body prose to `64ch`; short ledes to `48ch`. The main section rhythm is intentionally generous:

| Element | Spacing |
| --- | --- |
| Document header bottom padding / separation | `40px / 64px` |
| Section separation | `80px` (`64px` on small screens) |
| Eyebrow to title | `20px` |
| Title to lede | `20px` |
| Lede to CTA row | `24px` |
| Section label to section heading | `12px` |
| Section heading to content | `24px` |

On screens at or below `1024px`, replace the static sidebar with a `52px` sticky top bar and an off-canvas drawer. Hide the in-page TOC at `1120px` and below. Collapse grids to one column at `900px` or `780px` depending on their density.

## Type scale and copy hierarchy

| Element | Treatment |
| --- | --- |
| Eyebrow / section index | Mono, `12px`, `--fg-3`; examples: `01 / Projects`, `Reference · HTTP · JSON` |
| Page title | `clamp(2rem, 2.8vw, 2.75rem)`, weight `500`, tight tracking |
| Section title | `clamp(1.35rem, 2vw, 1.5rem)`, weight `500` |
| Lede | `17px / 1.6`, `--fg-2` |
| Body / descriptions | `15–16px / 1.6–1.7`, `--fg-2` |
| Value / item title | Display face, `15–16px`, `500`, `--fg` |
| Labels / metadata | Mono, `11–13px`, `--fg-3` |

Use sentence case. Labels should be factual and compact; status text, keyboard keys, endpoint methods, paths, counts, dates, and IDs belong in mono. Do not use oversized marketing copy or all-caps display type.

## Component recipes

### Dividers, lists, and cards

- A normal list is an open layout with a top `1px solid var(--line)` rule. Each row has `20px 0` padding and a bottom rule.
- A segmented stat/specimen group uses `gap: 1px`, `background: var(--line)`, and `overflow: hidden`; each cell is `--bg-2`. This creates seams without thick borders.
- An ordinary card is `--bg-2`, `1px solid var(--line)`, `10px` radius, and `16–24px` padding. Use cards only for self-contained tools, forms, preview objects, or a compact identity panel.
- The portrait/identity card is the exception: `16px` radius and a stronger `--line-2` border.
- Code blocks use `--bg-2`, `--line`, `10px` radius, `24px` padding, JetBrains Mono at `13px / 1.8`, and horizontal scrolling.

### Buttons and inputs

Controls are modest, rectangular, and never pill-shaped. Primary action is inverted; secondary action stays neutral.

```css
.button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  height: 40px;
  padding: 0 16px;
  border: 1px solid var(--line-2);
  border-radius: var(--radius-sm);
  background: var(--bg-2);
  color: var(--fg);
  font: 500 14px var(--font-display);
  text-decoration: none;
  cursor: pointer;
  transition: background-color 140ms var(--ease), border-color 140ms var(--ease), color 140ms var(--ease);
}
.button:hover { background: var(--bg-3); }
.button--primary { background: var(--fg); border-color: var(--fg); color: var(--bg); }
.button--primary:hover { background: var(--fg-2); border-color: var(--fg-2); }
.field {
  height: 40px;
  padding: 0 12px;
  border: 1px solid var(--line-2);
  border-radius: var(--radius-sm);
  background: var(--bg-2);
  color: var(--fg);
  font: 400 15px var(--font-body);
}
.field::placeholder { color: var(--fg-3); }
.field:focus { outline: none; border-color: var(--fg-2); }
```

Use a compact button for utility actions: `32px` high, `10px` horizontal padding, body face at `13px`, transparent background, and a `--bg-3` fill on hover. Keyboard hints use a `4px` radius, `11px` mono, and a `--line-2` border.

### Navigation and selected states

Sidebar links are `36px` tall with `8px` horizontal padding, `6px` radius, `14px` display text, and a small icon. On hover, fill with `--bg-3`; when selected, retain that fill and add a subtle `inset 0 0 0 1px var(--line)`.

Tabs are more austere: transparent background, mono labels, and one active foreground-colored bottom border. Command-palette selections may instead use a `2px` foreground left rule plus `--bg-3` fill.

### Status and semantic colour

Represent status with a small solid dot plus mono text. Typical dot sizes are `6px` in navigation and `8px` in information cards. Use `--signal` for online/healthy, `--warning` for idle/caution, and `--danger` for errors, destructive confirmation, or critical notices. Do not recolor general UI controls to these values.

### Links and callouts

Text links retain the foreground colour and use an understated underline: offset `3px`, initial colour `--line-2`, full foreground only on hover. A quotation or editorial callout is not a filled card; give it a `1px` left rule, `24px` left padding, and a `20px`, medium-weight sentence.

## Motion, overlays, and accessibility

- Use the single `--ease` curve everywhere.
- Standard hover/focus transitions take `140ms`; palette or backdrop fades take `160ms`; a drawer or panel entrance can take `200–240ms`.
- Keep animation functional: hover feedback, modal/dropdown entrance, drawer movement, and reading progress only. No looping decorative motion.
- Dialogs and command palettes use `--overlay` behind a `--bg-2` surface, `--line-2` border, and `--shadow`. The command palette is at most `560px` wide.
- Keep the visible focus outline from the foundation. Do not replace it with colour-only state changes.
- Honor `prefers-reduced-motion` by disabling smooth scrolling and reducing all animation/transition durations to near zero.

```css
@media (prefers-reduced-motion: reduce) {
  html { scroll-behavior: auto; }
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
  }
}
```

## Copy-ready implementation brief

Paste this into an AI coding tool when applying the theme to another website:

> Re-theme this site using the PhaseWorld design system: a restrained monochrome dark-first developer/documentation UI. Use Instrument Sans for body, controls, and medium-weight headings; use JetBrains Mono only for metadata, labels, code, counts, and technical values. Use the exact PhaseWorld dark/light tokens from `theme.md`. Make `#141415` the default page surface, reserve `#0f0f10` for persistent chrome, and use hairline translucent dividers rather than prominent borders. Use no gradients, glow, glassmorphism, brand accent colours, or oversized marketing styling. Primary buttons are inverted foreground fills; secondary buttons are neutral surfaces. Lay pages out as spacious documents with mono eyebrows, concise titles, muted ledes, 64ch prose, 80px section rhythm, and rule-separated rows. Use compact 6–10px radii, 140ms easing-based feedback, accessible focus rings, and semantic green/amber/red only for status. On desktop, prefer a 264px sidebar; replace it with a 52px top bar and drawer below 1024px.

## Things that would break the theme

- Neon gradients, purple/pink/blue brand accents, colourful category chips, or a colored primary button.
- Large rounded "SaaS" cards everywhere, pills, heavy drop shadows, or blurred glass panels.
- Bold/black headings, all-caps UI labels, wide letter spacing, or mono used for body copy.
- Dense dashboards without document-like whitespace and divider structure.
- Animation used as ornament rather than feedback.
