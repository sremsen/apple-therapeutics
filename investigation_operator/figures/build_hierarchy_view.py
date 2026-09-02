#!/usr/bin/env python3
"""
Build the figure showing Molly's SOP as steps, tasks and actions. Actions that
carry a part of her quality control loop are marked.

    python investigation_operator/figures/build_hierarchy_view.py
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _stages import STAGES, load_sops  # noqa: E402

OUT = Path(__file__).resolve().parent / "hierarchy_view.html"

# What each stage means, keyed to the name _stages.py gives it. Which action
# carries a stage is decided there, not here.
STAGE_NOTES = {
    "Aim": "Sets the geometry of the cut before making it.",
    "See": "Keeps the size of each cut visible while cutting.",
    "Measure": "Checks the slice that was just produced.",
}


def stage_for(text):
    for spec in STAGES:
        if re.search(spec["pattern"], text, re.I):
            return (spec["name"], STAGE_NOTES.get(spec["name"], ""))
    return None

# Figure geometry. One SVG with a viewBox, so it scales to any width - change
# ASPECT alone to reshape it.
W = 1202
ASPECT = 16 / 9
H = round(W / ASPECT)

TICK_W, GAP_ACTION, GAP_TASK, GAP_STEP = 26, 10, 26, 46
Y_STEP, H_STEP = 34, 86
Y_TASK, H_TASK = 132, 62
Y_TICK, H_TICK = 208, 92
Y_DOT = 316
Y_CALL = 350
Y_RULE = 452
Y_KEY = 484
Y_LEGEND = H - 26


def esc(t):
    return (t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def main():
    sop = load_sops()["molly"]

    ticks, tasks, steps = [], [], []
    x = 0
    for si, step in enumerate(sop["steps"], 1):
        step_x0 = x
        for ti, task in enumerate(step["tasks"], 1):
            task_x0 = x
            for text in task["actions"]:
                stage = stage_for(text)
                ticks.append({"x": x, "stage": stage})
                x += TICK_W + GAP_ACTION
            x -= GAP_ACTION
            tasks.append({"x": task_x0, "w": x - task_x0, "label": f"{si}.{ti}",
                          "task": task["task"],
                          "decisions": [d["type"] for d in task["decision_points"]]})
            x += GAP_TASK
        x -= GAP_TASK
        steps.append({"x": step_x0, "w": x - step_x0, "n": si, "step": step["step"]})
        x += GAP_STEP
    total = x - GAP_STEP
    scale = W / total                      # normalize to the viewBox width
    for coll in (ticks, tasks, steps):
        for it in coll:
            it["x"] *= scale
            if "w" in it:
                it["w"] *= scale
    tick_w = TICK_W * scale

    svg = []
    for st in steps:
        svg.append(f'<rect class="b-step" x="{st["x"]:.1f}" y="{Y_STEP}" '
                   f'width="{st["w"]:.1f}" height="{H_STEP}" rx="3"/>')
        svg.append(f'<text class="t-step" x="{st["x"]+11:.1f}" y="{Y_STEP+26}">'
                   f'{esc(st["step"])}</text>')
        svg.append(f'<text class="t-sub" x="{st["x"]+11:.1f}" y="{Y_STEP+H_STEP-12}">'
                   f'STEP {st["n"]}</text>')
    for t in tasks:
        svg.append(f'<rect class="b-task" x="{t["x"]:.1f}" y="{Y_TASK}" '
                   f'width="{t["w"]:.1f}" height="{H_TASK}" rx="3"/>')
        svg.append(f'<text class="t-task" x="{t["x"]+9:.1f}" y="{Y_TASK+22}">{t["label"]}</text>')
        n = len(t["decisions"])
        if n:
            start = t["x"] + t["w"] / 2 - (n * 11 - 4) / 2
            for i, kind in enumerate(t["decisions"]):
                cls = "d-adj" if kind == "adjusted" else "d-dis"
                svg.append(f'<circle class="{cls}" cx="{start+i*11+3.5:.1f}" '
                           f'cy="{Y_DOT}" r="3.6"/>')
    for tk in ticks:
        cls = "k-hl" if tk["stage"] else "k"
        svg.append(f'<rect class="{cls}" x="{tk["x"]:.1f}" y="{Y_TICK}" '
                   f'width="{tick_w:.1f}" height="{H_TICK}" rx="1.5"/>')

    for i, tk in enumerate([t for t in ticks if t["stage"]]):
        cx = tk["x"] + tick_w / 2
        top = Y_CALL + (i % 2) * 42
        svg.append(f'<line class="lead" x1="{cx:.1f}" y1="{Y_TICK+H_TICK+6}" '
                   f'x2="{cx:.1f}" y2="{top-13}"/>')
        lx = max(6, min(cx - 8, W - 210))
        svg.append(f'<text class="t-call" x="{lx:.1f}" y="{top}">{tk["stage"][0]}</text>')
        words, line, lines = tk["stage"][1].split(), "", []
        for wd in words:
            if len(line + " " + wd) > 34:
                lines.append(line); line = wd
            else:
                line = (line + " " + wd).strip()
        lines.append(line)
        for j, ln in enumerate(lines[:2]):
            svg.append(f'<text class="t-callsub" x="{lx:.1f}" y="{top+14+j*12}">{esc(ln)}</text>')

    svg.append(f'<line class="rule" x1="0" y1="{Y_RULE}" x2="{W}" y2="{Y_RULE}"/>')
    for i, t in enumerate(tasks):
        col, row = divmod(i, 5)
        kx, ky = 6 + col * 600, Y_KEY + row * 21
        svg.append(f'<text class="t-keyn" x="{kx}" y="{ky}">{t["label"]}</text>')
        svg.append(f'<text class="t-key" x="{kx+34}" y="{ky}">{esc(t["task"])}</text>')

    lx = 6
    for icon, label in (("hl", "Action carrying a stage of the control loop"),
                        ("adj", "Judgment — acted on"),
                        ("dis", "Judgment — evaluated, no change")):
        if icon == "hl":
            svg.append(f'<rect class="k-hl" x="{lx}" y="{Y_LEGEND-9}" width="11" height="11" rx="2"/>')
        else:
            svg.append(f'<circle class="d-{icon}" cx="{lx+5.5}" cy="{Y_LEGEND-3.5}" r="4.4"/>')
        svg.append(f'<text class="t-legend" x="{lx+19}" y="{Y_LEGEND}">{esc(label)}</text>')
        lx += 26 + len(label) * 6.4

    n_dec = sum(len(t["decisions"]) for t in tasks)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(TEMPLATE
                   .replace("__SVG__", "\n  ".join(svg))
                   .replace("__W__", str(W)).replace("__H__", str(H))
                   .replace("__NA__", str(len(ticks))).replace("__NT__", str(len(tasks)))
                   .replace("__NS__", str(len(steps))).replace("__ND__", str(n_dec)))
    print(f"{len(steps)} steps · {len(tasks)} tasks · {len(ticks)} actions · "
          f"{n_dec} decisions · viewBox {W}x{H} ({ASPECT:.3f}:1)")
    print(f"-> {OUT}")


TEMPLATE = r'''<title>Anatomy of a Cut</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;450;500;600&family=JetBrains+Mono:wght@400;500&display=swap">
<style>
:root{--bg:#faf9f7;--border:#e3e1dc;--text:#16181a;--text-2:#5d6266;--text-3:#8d9296;
      --shadow:0 1px 2px rgba(20,22,24,.05),0 6px 18px rgba(20,22,24,.05)}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  --bg:#0c0d0e;--border:#25282a;--text:#f2f3f2;--text-2:#9aa0a3;--text-3:#6e7478;
  --shadow:0 1px 2px rgba(0,0,0,.45)}}
:root[data-theme="dark"]{--bg:#0c0d0e;--border:#25282a;--text:#f2f3f2;--text-2:#9aa0a3;
  --text-3:#6e7478;--shadow:0 1px 2px rgba(0,0,0,.45)}
*{box-sizing:border-box}
body{background:var(--bg);color:var(--text);font-family:Inter,ui-sans-serif,system-ui,sans-serif;
     font-size:14px;line-height:1.6;-webkit-font-smoothing:antialiased;letter-spacing:-.008em}
.page{max-width:1000px;margin:0 auto;padding:64px 28px 96px;display:flex;flex-direction:column;gap:46px}
.eyebrow{font-family:"JetBrains Mono",ui-monospace,monospace;font-size:11px;letter-spacing:.1em;
         text-transform:uppercase;color:var(--text-3)}
h1{margin:0;font-size:32px;font-weight:600;letter-spacing:-.024em;text-wrap:balance}
.lede{margin:0;max-width:64ch;color:var(--text-2);font-size:15.5px}
h2{margin:0;font-size:12px;font-weight:550;letter-spacing:.07em;text-transform:uppercase;color:var(--text-3)}
p{margin:0;color:var(--text-2);max-width:68ch}
strong{color:var(--text);font-weight:550}
section{display:flex;flex-direction:column;gap:16px}

/* One SVG on a white ground in both themes: it scales rather than scrolling,
   holds an exact aspect ratio, and screenshots cleanly. */
.chart{background:#fff;border:1px solid #e3e1dc;border-radius:12px;box-shadow:var(--shadow);
       padding:22px 24px;width:min(1300px,calc(100vw - 44px));margin-left:50%;
       transform:translateX(-50%)}
.chart svg{display:block;width:100%;height:auto}
.b-step{fill:#c3c6bc;stroke:#a5a999;stroke-width:2;stroke-dasharray:0}
.b-task{fill:#bccbcd;stroke:#9ab0b3;stroke-width:2}
.k{fill:#3d4548;opacity:.9}
.k-hl{fill:#b3dd1f;stroke:#7d9a12;stroke-width:1}
.d-adj{fill:#b8532f;stroke:#b8532f;stroke-width:1.5}
.d-dis{fill:#fff;stroke:#b8532f;stroke-width:1.5}
.lead{stroke:#7d9a12;stroke-width:1;opacity:.6}
.rule{stroke:#e0ded8;stroke-width:1}
text{font-family:Inter,system-ui,sans-serif}
.t-step{font-size:13.5px;font-weight:600;fill:#16181a;letter-spacing:-.01em}
.t-sub{font-family:"JetBrains Mono",monospace;font-size:9.5px;letter-spacing:.07em;fill:#5a5f62}
.t-task{font-family:"JetBrains Mono",monospace;font-size:11.5px;font-weight:500;fill:#16181a}
.t-call{font-size:12.5px;font-weight:600;fill:#16181a}
.t-callsub{font-size:11px;fill:#5a5f62}
.t-keyn{font-family:"JetBrains Mono",monospace;font-size:11px;font-weight:500;fill:#16181a}
.t-key{font-size:12px;fill:#5a5f62}
.t-legend{font-size:11.5px;fill:#5a5f62}
.counts{display:flex;gap:26px;flex-wrap:wrap;font-family:"JetBrains Mono",monospace;
        font-size:11.5px;color:var(--text-3);letter-spacing:.03em}
.counts b{color:var(--text);font-weight:500}
@media(max-width:680px){.page{padding:40px 18px 64px}h1{font-size:25px}
  .chart{width:calc(100vw - 32px);padding:14px}}
</style>

<div class="page">
<header style="display:flex;flex-direction:column;gap:13px">
  <div class="eyebrow">apple-therapeutics &middot; operator investigation</div>
  <h1>Anatomy of a Cut</h1>
  <p class="lede">One expert operator&rsquo;s procedure, decomposed. Three runs on video became
  __NA__ atomic actions, grouped into __NT__ tasks and __NS__ steps &mdash; and __ND__ points
  where she stops to make a judgment.</p>
</header>

<section>
  <div class="chart">
    <svg viewBox="0 0 __W__ __H__" role="img"
         aria-label="An expert operator's procedure broken into __NS__ steps, __NT__ tasks and __NA__ atomic actions, with the control-loop stages and judgment points marked.">
  __SVG__
    </svg>
  </div>
  <div class="counts">
    <span><b>__NS__</b> steps</span><span><b>__NT__</b> tasks</span>
    <span><b>__NA__</b> atomic actions</span><span><b>__ND__</b> judgment points</span>
  </div>
  <p>Widths are proportional to the number of actions each block contains, and gaps widen at task
  and step boundaries &mdash; so the spacing of the barcode is the structure of the work, not decoration.</p>
</section>

<section>
  <h2>Why decompose it this way</h2>
  <p><strong>Steps</strong> are the phases a written procedure would name. <strong>Tasks</strong>
  group contiguous actions serving one purpose. <strong>Atomic actions</strong> are single acts,
  each two to five seconds of video.</p>
  <p>The level a written SOP usually omits is the last one: the <strong>judgment points</strong>.
  Three of the highlighted actions are how this operator controls her own output &mdash; she aims
  the apple before cutting, keeps the cut visible while cutting, and checks the slice after. The
  fourth stage is not an action at all. It is a decision: a slice judged too thin is set aside
  rather than kept.</p>
</section>
</div>
'''

if __name__ == "__main__":
    main()
