#!/usr/bin/env python3
"""
Build the figure comparing Molly's SOP against the baseline, task by task. The
task pairings are written out below rather than computed, so that judgment is
reviewable.

    python investigation_operator/figures/build_alignment_view.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _stages import load_sops, read_stages  # noqa: E402

OUT = Path(__file__).resolve().parent / "alignment_view.html"

# Which task lines up with which, by name, with None for no counterpart. A name
# that no longer exists fails loudly below, where an index would just mis-pair.
ALIGNMENT = [
    ("Inspect the apple",                    "Inspect the apple for surface defects"),
    (None,                                   "Check the cutting board"),
    (None,                                   "Select the knife"),
    ("Position for the first cut",           None),
    ("Position the apple or core piece for cutting",
                                             "Position the apple or remaining piece for cutting"),
    ("Cut the section free",                 "Cut the section free"),
    ("Inspect and set aside the core piece", "Set aside the core piece"),
    ("Trim scrap from the section",          "Trim uneven edges from the section"),
    ("Cut slices from the section",          "Cut slices from the section"),
    ("Check and tidy the slices",            "Evaluate and clear remaining scrap"),
    ("Conclude slicing",                     "Gather the slices"),
    ("Remove scrap and pieces from the board", "Finish the cutting process"),
]


def flatten(sop):
    out = []
    for si, step in enumerate(sop["steps"]):
        for task in step["tasks"]:
            out.append({"task": task["task"], "step": step["step"], "si": si,
                        "actions": task["actions"],
                        "decisions": [{"c": d["condition"], "r": d["response"],
                                       "t": d["type"]} for d in task["decision_points"]]})
    return out


def stage_badges(sop, track):
    """Map task index -> (stage name, evidence), found rather than typed in.

    read_stages() picks the sentence carrying each stage; this finds the task it
    lives in, so a regenerated SOP moves the label instead of stranding it.
    """
    badges, correct = {}, {}
    for row in read_stages(sop):
        if not row["match"]:
            continue
        for i, task in enumerate(track):
            in_actions = row["match"] in task["actions"]
            in_decisions = any(d["r"] == row["match"] for d in task["decisions"])
            if not (in_actions or in_decisions):
                continue
            if row["name"] == "Correct":
                correct[i] = {"ok": row["present"], "text": row["evidence"]}
            else:
                badges[i] = (row["name"], row["evidence"])
            break
    return badges, correct


def main():
    sops = load_sops()
    tracks = {k: flatten(sop) for k, sop in sops.items()}
    badges = {k: stage_badges(sops[k], tracks[k]) for k in sops}

    # An unknown name means an SOP was regenerated and ALIGNMENT needs
    # revisiting. Worth stopping for, since a dropped column misstates the figure.
    index_of = {k: {t["task"]: i for i, t in enumerate(v)} for k, v in tracks.items()}
    columns = []
    for names in ALIGNMENT:
        col = {}
        for key, name in zip(("molly", "baseline"), names):
            if name is None:
                col[key] = None
                continue
            if name not in index_of[key]:
                raise SystemExit(
                    f"error: ALIGNMENT names a {key} task that no longer exists: "
                    f"{name!r}\n       update ALIGNMENT in {Path(__file__).name}")
            idx = index_of[key][name]
            stage_badge, correct_badge = badges[key]
            t = dict(tracks[key][idx])
            t["stage"] = stage_badge.get(idx)
            t["correct"] = correct_badge.get(idx)
            col[key] = t
        columns.append(col)

    totals = {k: {"actions": sum(len(t["actions"]) for t in v),
                  "decisions": sum(len(t["decisions"]) for t in v),
                  "adjusted": sum(1 for t in v for d in t["decisions"] if d["t"] == "adjusted")}
              for k, v in tracks.items()}

    stages = [
        {"name": m["name"], "when": m["when"],
         "molly": {"present": m["present"], "text": m["evidence"]},
         "baseline": {"present": b["present"], "text": b["evidence"]}}
        for m, b in zip(read_stages(sops["molly"]), read_stages(sops["baseline"]))
    ]

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(TEMPLATE
                   .replace("__COLUMNS__", json.dumps(columns))
                   .replace("__TOTALS__", json.dumps(totals))
                   .replace("__STAGES__", json.dumps(stages)))
    print(f"{len(columns)} columns  molly={totals['molly']} baseline={totals['baseline']}")
    print(f"-> {OUT}")


TEMPLATE = r'''<title>Where the Loop Closes</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;450;500;600&family=JetBrains+Mono:wght@400;500&display=swap">
<style>
:root{
  --bg:#fbfbfc;--surface:#fff;--surface-2:#f4f4f6;--border:#e4e4e8;--border-2:#d3d4da;
  --text:#101114;--text-2:#62656e;--text-3:#8b8e98;--accent:#5e6ad2;
  --good:#2f9e68;--bad:#d64545;--bad-bg:#fdeaea;--good-bg:#e9f6ef;
  --shadow:0 1px 2px rgba(16,17,20,.05),0 4px 12px rgba(16,17,20,.04);
}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  --bg:#08090a;--surface:#101113;--surface-2:#17181b;--border:#212226;--border-2:#2c2d33;
  --text:#f7f8f8;--text-2:#9498a3;--text-3:#6b6f7a;--accent:#7b85e0;
  --good:#4cb782;--bad:#ef6b6b;--bad-bg:#2a1616;--good-bg:#132318;
  --shadow:0 1px 2px rgba(0,0,0,.4);
}}
:root[data-theme="dark"]{
  --bg:#08090a;--surface:#101113;--surface-2:#17181b;--border:#212226;--border-2:#2c2d33;
  --text:#f7f8f8;--text-2:#9498a3;--text-3:#6b6f7a;--accent:#7b85e0;
  --good:#4cb782;--bad:#ef6b6b;--bad-bg:#2a1616;--good-bg:#132318;
  --shadow:0 1px 2px rgba(0,0,0,.4);
}
*{box-sizing:border-box}
body{background:var(--bg);color:var(--text);font-family:Inter,ui-sans-serif,system-ui,sans-serif;
     font-size:14px;line-height:1.6;-webkit-font-smoothing:antialiased;letter-spacing:-.008em}
.page{max-width:1000px;margin:0 auto;padding:64px 28px 96px;display:flex;flex-direction:column;gap:52px}
.eyebrow{font-family:"JetBrains Mono",ui-monospace,monospace;font-size:11px;letter-spacing:.1em;
         text-transform:uppercase;color:var(--text-3)}
h1{margin:0;font-size:32px;font-weight:600;letter-spacing:-.024em;text-wrap:balance}
.lede{margin:0;max-width:62ch;color:var(--text-2);font-size:15.5px}
h2{margin:0;font-size:12px;font-weight:550;letter-spacing:.07em;text-transform:uppercase;color:var(--text-3)}
p{margin:0;color:var(--text-2);max-width:68ch}
strong{color:var(--text);font-weight:550}
section{display:flex;flex-direction:column;gap:18px}

/* ---- the finding ---- */
.loop{--l-bd:#e4e4e8;--l-surface:#fff;--l-text:#101114;--l-text-2:#62656e;--l-text-3:#8b8e98;
      --l-good:#1f7a4d;--l-bad:#b93030;--l-good-bg:#eef7f2;--l-bad-bg:#fdf0f0;
      display:grid;grid-template-columns:110px 1fr 1fr;gap:1px;background:var(--l-bd);
      border:1px solid var(--l-bd);border-radius:11px;overflow:hidden}
.loop>div{background:var(--l-surface);padding:15px 17px;font-size:13.5px;color:var(--l-text-2)}
.loop .hd{font-family:"JetBrains Mono",monospace;font-size:10px;letter-spacing:.09em;
          text-transform:uppercase;color:var(--l-text-3)}
.loop .st{color:var(--l-text);font-weight:550;font-size:14px}
.loop .st small{display:block;font-weight:400;font-size:11.5px;color:var(--l-text-3);
                letter-spacing:0;margin-top:1px}
.loop .yes{background:var(--l-good-bg)}
.loop .no{background:var(--l-bad-bg);color:var(--l-bad)}
.mark{font-family:"JetBrains Mono",monospace;font-size:10px;letter-spacing:.06em;
      text-transform:uppercase;display:block;margin-bottom:4px}
.loop .mark.y{color:var(--l-good)}.loop .mark.n{color:var(--l-bad)}

.punch{border-left:3px solid var(--bad);background:var(--surface);padding:16px 20px;
       border-radius:0 8px 8px 0;font-size:15px;color:var(--text)}
.punch em{color:var(--text-2);font-style:normal}

/* ---- aligned tracks ---- */
.chart{background:var(--surface);border:1px solid var(--border);border-radius:11px;
       box-shadow:var(--shadow);padding:24px 22px;overflow-x:auto;
       width:min(1240px,calc(100vw - 44px));margin-left:50%;transform:translateX(-50%)}
.grid{display:flex;gap:7px;min-width:1000px}
.col{flex:1 1 0;min-width:76px;display:flex;flex-direction:column;gap:5px}
.trackrow{display:flex;justify-content:space-between;min-width:1000px;margin-bottom:9px}
.trackname{font-family:"JetBrains Mono",monospace;font-size:11px;letter-spacing:.07em;
           text-transform:uppercase;color:var(--text-3)}
.trackname b{color:var(--text);font-weight:500}
.band{border:1px solid var(--border-2);border-radius:5px;padding:6px 8px;font-size:10.5px;
      line-height:1.35;min-height:52px;background:var(--surface-2);color:var(--text-2);cursor:default}
.band:hover{border-color:var(--accent)}
.band.gap{border-style:dashed;background:transparent;color:var(--text-3);min-height:52px;
          display:flex;align-items:center;justify-content:center;font-size:16px}
.dots{display:flex;gap:3px;height:10px;align-items:center;flex-wrap:wrap;justify-content:center}
.dot{width:7px;height:7px;border-radius:50%;border:1.5px solid var(--accent);cursor:default}
.dot.adj{background:var(--accent)}
.mid{height:22px;display:flex;align-items:center;justify-content:center}
.mid span{font-family:"JetBrains Mono",monospace;font-size:9px;letter-spacing:.07em;
          text-transform:uppercase;color:var(--text-3);border-top:1px solid var(--border);
          width:100%;text-align:center;padding-top:5px}
#tip{position:fixed;z-index:50;max-width:330px;background:var(--surface);color:var(--text);
     border:1px solid var(--border-2);border-radius:7px;padding:10px 12px;font-size:12.5px;
     line-height:1.5;box-shadow:0 10px 28px rgba(0,0,0,.28);pointer-events:none;display:none}
#tip .k{font-family:"JetBrains Mono",monospace;font-size:9.5px;letter-spacing:.08em;
        text-transform:uppercase;color:var(--text-3);display:block;margin-bottom:4px}
.legend{display:flex;gap:24px;flex-wrap:wrap;font-size:12.5px;color:var(--text-2);align-items:center}
@media(max-width:680px){.page{padding:40px 18px 64px}h1{font-size:25px}
  .chart{width:calc(100vw - 32px)}.loop{grid-template-columns:1fr}}
</style>

<div class="page">
<header style="display:flex;flex-direction:column;gap:13px">
  <div class="eyebrow">apple-therapeutics &middot; operator investigation</div>
  <h1>Where the Loop Closes</h1>
  <p class="lede">Two procedures, each built from three runs on video. They perform the same
  steps in the same order. Only one of them acts on what it finds.</p>
</header>

<section>
  <h2>The difference, in four stages</h2>
  <div class="loop" id="loop"></div>
  <div class="punch"><strong>Both procedures throw away material that can&rsquo;t become a slice.
  Only one throws away a slice that came out wrong.</strong>
  <em>The instruction for discarding an unusable remnant is identical in both. What differs is
  what happens to a finished slice judged too thin: one culls it, the other notes it and keeps
  cutting the same way. Measurement that changes nothing isn&rsquo;t control, and an open loop is
  what produces run-to-run variation in width.</em></div>
</section>

<section>
  <h2>The same procedure, aligned task by task</h2>
  <div class="chart">
    <div class="trackrow" id="names"></div>
    <div id="grid" class="grid"></div>
  </div>
  <div class="legend">
    <span><span class="dot adj" style="display:inline-block;margin-right:7px;vertical-align:-1px"></span>Judgment &mdash; acted on</span>
    <span><span class="dot" style="display:inline-block;margin-right:7px;vertical-align:-1px"></span>Judgment &mdash; evaluated, no change</span>
    <span style="color:var(--text-3)">Dashed &mdash; no counterpart in the other procedure</span>
  </div>
  <p>Each block is a task, aligned so matching work lines up. The dots above and below are the
  moments the operator stopped to judge something. Hover for the text behind any of them.</p>
</section>
</div>

<div id="tip"></div>
<script>
const COLUMNS=__COLUMNS__,TOTALS=__TOTALS__;
const tip=document.getElementById('tip');
function show(e,k,b){tip.innerHTML='<span class="k">'+k+'</span>'+b;tip.style.display='block';
  const r=tip.getBoundingClientRect();
  tip.style.left=Math.min(e.clientX+14,innerWidth-r.width-12)+'px';
  tip.style.top=Math.min(e.clientY+14,innerHeight-r.height-12)+'px';}
const hide=()=>tip.style.display='none';

function band(t){
  const d=document.createElement('div');
  if(!t){d.className='band gap';d.textContent='—';return d;}
  d.className='band';d.textContent=t.task;
  d.onmousemove=e=>show(e,'Task','<strong>'+t.task+'</strong><br>'+t.step+'<br><br>'+
    t.actions.length+' actions'+(t.decisions.length?' · '+t.decisions.length+' judgment point'+
    (t.decisions.length>1?'s':''):''));
  d.onmouseleave=hide;return d;
}
function dots(t){
  const w=document.createElement('div');w.className='dots';
  if(!t)return w;
  t.decisions.forEach(d=>{
    const s=document.createElement('span');
    s.className='dot'+(d.t==='adjusted'?' adj':'');
    s.onmousemove=e=>show(e,d.t==='adjusted'?'Judgment · acted on':'Judgment · evaluated, no change',
      '<strong>If</strong> '+d.c+'<br><strong>Then</strong> '+d.r);
    s.onmouseleave=hide;w.appendChild(s);
  });
  return w;
}
const grid=document.getElementById('grid');
COLUMNS.forEach(col=>{
  const c=document.createElement('div');c.className='col';
  c.appendChild(dots(col.molly));
  c.appendChild(band(col.molly));
  const m=document.createElement('div');m.className='mid';m.innerHTML='<span></span>';c.appendChild(m);
  c.appendChild(band(col.baseline));
  c.appendChild(dots(col.baseline));
  grid.appendChild(c);
});
document.getElementById('names').innerHTML=
  '<div class="trackname"><b>Expert</b> &middot; one operator, three runs &middot; '+
  TOTALS.molly.decisions+' judgment points</div>'+
  '<div class="trackname">'+TOTALS.baseline.decisions+
  ' judgment points &middot; three operators, one run each &middot; <b>Baseline</b></div>';

const STAGES=__STAGES__;
const loop=document.getElementById('loop');
loop.innerHTML='<div class="hd"></div><div class="hd">Expert</div><div class="hd">Baseline</div>';
const cell=v=>'<div class="'+(v.present?'yes':'no')+'"><span class="mark '+
  (v.present?'y':'n')+'">'+(v.present?'present':'absent')+'</span>'+v.text+'</div>';
STAGES.forEach(s=>{
  loop.insertAdjacentHTML('beforeend',
    '<div class="st">'+s.name+'<small>'+s.when+'</small></div>'+cell(s.molly)+cell(s.baseline));
});
</script></script>
'''

if __name__ == "__main__":
    main()
