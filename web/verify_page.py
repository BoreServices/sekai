"""Verification page shell.

The verification site runs under a strict Content-Security-Policy (inline
styles only, no scripts, no external requests except images), so this module
builds markup with the shared design system but skips the font links and adds
the step indicator plus success/error marks.
"""

from __future__ import annotations

from html import escape

from web.design import document

VERIFY_CSS = """
main.shell{max-width:640px}
.verify{max-width:520px; margin:min(6vh,56px) auto 0}
.verify-card{
  background:var(--bg-2);border:1px solid var(--line-2);border-radius:var(--radius-lg);padding:28px;
}
.steps{display:flex; flex-wrap:wrap; gap:14px; list-style:none; padding:0; margin:0 0 24px}
.step{display:flex; align-items:center; gap:8px; font-size:.76rem; font-weight:500; color:var(--fg-3)}
.step-dot{
  width:22px; height:22px; border-radius:4px; display:grid; place-items:center;
  font-family:var(--font-mono); font-size:.7rem;
  background:var(--bg-3); border:1px solid var(--line); color:var(--fg-3);
}
.step.done{color:var(--fg-2)}
.step.done .step-dot{background:var(--signal);border-color:var(--signal);color:var(--bg)}
.step.current{color:var(--fg)}
.step.current .step-dot{
  background:var(--fg); border-color:var(--fg); color:var(--bg);
}
.verify-head{display:flex; align-items:center; gap:14px; margin-bottom:6px}
.verify-icon{
  width:52px; height:52px; border-radius:14px; object-fit:cover;
  border:1px solid var(--line); background:var(--bg-2); flex:none;
}
.mark{
  width:52px; height:52px; border-radius:50%; display:grid; place-items:center;
  font-family:var(--font-display); font-size:26px; font-weight:500; margin-bottom:16px;
}
.mark.ok{background:var(--signal);color:var(--bg)}
.mark.bad{background:var(--danger);color:var(--bg)}
.verify-card.result{text-align:center}
.verify-card.result .steps{justify-content:center}
.verify-card.result .verify-head{justify-content:center}
.verify-card.result .mark{width:64px;height:64px;font-size:30px;margin:0 auto 18px}
.verify-card.result .btn{margin-inline:auto}
.verify-card h1{font-size:clamp(1.5rem,4vw,1.85rem); margin:4px 0 12px}
.verify-card p{font-size:.95rem; margin-bottom:10px}
.verify-card p.strong{color:var(--fg)}
.verify-card .btn{margin-top:16px}
altcha-widget{display:block; min-height:70px; margin:0 0 4px}
.fine{font-size:.78rem; color:var(--fg-3); margin-top:10px}
.note{
  margin-top:22px; padding-top:16px; border-top:1px solid var(--line);
  font-size:.78rem; color:var(--fg-3); line-height:1.55;
}
.verify-hero{display:flex; align-items:center; gap:14px; margin-bottom:18px}
.hero-mark{
  width:48px; height:48px; border-radius:14px; display:grid; place-items:center;
  font-size:22px; background:var(--bg-2); border:1px solid var(--line); flex:none;
}
.lede{font-size:1rem; color:var(--fg-2)}
.steps-list{display:grid; gap:12px; padding:0; margin:22px 0 0; list-style:none; counter-reset:step}
.steps-list li{
  display:grid; grid-template-columns:26px 1fr; gap:11px; align-items:start;
  font-size:.9rem; color:var(--fg-2); counter-increment:step;
}
.steps-list li::before{
  content:counter(step); width:26px; height:26px; border-radius:50%;
  display:grid; place-items:center; font-family:var(--font-mono); font-size:.74rem;
  font-weight:600; color:var(--fg); background:var(--bg-3);
  border:1px solid var(--line); margin-top:1px;
}
.steps-list strong{color:var(--fg)}
@media (max-width:560px){
  .verify-card{padding:22px}
  .steps{gap:10px}
  .verify-card.result .mark{width:56px; height:56px; font-size:26px}
}
"""

STEP_LABELS = ("Open your link", "Discord sign-in", "Done")


def _steps(current: int) -> str:
    items = []
    for index, label in enumerate(STEP_LABELS, start=1):
        state = "done" if index < current else "current" if index == current else ""
        marker = "✓" if index < current else str(index)
        classes = "step" + (f" {state}" if state else "")
        items.append(
            f'<li class="{classes}"><span class="step-dot" aria-hidden="true">'
            f"{marker}</span>{escape(label)}</li>"
        )
    return (
        '<ol class="steps" aria-label="Verification progress">' + "".join(items) + "</ol>"
    )


def render_verify_page(
    *,
    title: str,
    heading: str,
    body: str,
    icon_url: str | None = None,
    error: bool = False,
    success: bool = False,
    step: int = 1) -> str:
    icon = (
        f'<img class="verify-icon" src="{escape(icon_url, quote=True)}" alt="">'
        if icon_url
        else ""
    )
    mark = ""
    if success:
        mark = '<div class="mark ok" aria-hidden="true">✓</div>'
    elif error:
        mark = '<div class="mark bad" aria-hidden="true">!</div>'
    heading_html = escape(heading)
    if icon:
        head = f'<div class="verify-head">{icon}<p class="eyebrow">Verification</p></div>'
    else:
        head = '<p class="eyebrow">Verification</p>'
    result = " result" if (success or error) else ""
    card = (
        f'<div class="verify"><div class="verify-card{result}">'
        f"{_steps(min(step, len(STEP_LABELS))) if step else ''}"
        f"{mark}{head}"
        f"<h1>{heading_html}</h1>"
        f"{body}"
        '<p class="note">Purpurite never sees your Discord password. Only your '
        "username and avatar are read for this check.</p>"
        "</div></div>"
    )
    return document(
        title,
        card,
        active="verify",
        description=(
            "Verify yourself with your Discord account and get the member role "
            "added automatically."
        ),
        fonts=False,
        motion=False,
        extra_css=VERIFY_CSS)
