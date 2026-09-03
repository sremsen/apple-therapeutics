"""
What does Molly do that the other three technicians do not? I recorded all six
videos myself and wrote Molly's consistency into the synthetic QA data, so this
tests whether the pipeline can find a difference I planted on purpose.

    python investigation_operator/operator_approach.py
"""

import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _stages import load_sops, read_stages  # noqa: E402
from _text import overlap  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
HERE = Path(__file__).resolve().parent
EXPERT = "molly"

# Used by every text comparison below. Three-letter words mostly produce false
# matches between two SOPs written independently, so they are dropped.
MIN_LEN = 3
THRESHOLD = 0.34

steps = pd.read_csv(REPO / "datasets/process_steps.csv")
manifest = pd.read_csv(HERE / "videos/manifest.csv")
steps = steps.merge(manifest[["video_id", "operator_id"]], on="video_id", how="left")
assert steps["operator_id"].notna().all(), "a video is missing from the manifest"

steps["group"] = (steps["operator_id"] == EXPERT).map({True: EXPERT, False: "baseline"})
steps["is_conditional"] = steps["condition"].notna()


# 1 -------------------------------------------------------------------------
# How often does each technician stop to judge something? Rate rather than
# count, because a longer clip contains more of everything.
print("=" * 70)
print("CONDITIONAL RATE BY VIDEO")
print("=" * 70)
by_video = (
    steps.groupby(["operator_id", "video_id"])
    .agg(actions=("action", "count"),
         conditional=("is_conditional", "sum"),
         adjusted=("condition_response", lambda s: (s == "adjusted").sum()),
         dismissed=("condition_response", lambda s: (s == "dismissed").sum()))
)
by_video["rate_%"] = (100 * by_video["conditional"] / by_video["actions"]).round(0)
print(by_video)

print()
print("BY GROUP")
by_group = (
    steps.groupby("group")
    .agg(videos=("video_id", "nunique"), actions=("action", "count"),
         conditional=("is_conditional", "sum"),
         adjusted=("condition_response", lambda s: (s == "adjusted").sum()),
         dismissed=("condition_response", lambda s: (s == "dismissed").sum()))
)
by_group["rate_%"] = (100 * by_group["conditional"] / by_group["actions"]).round(0)
print(by_group)

# Dismissing matters as much as adjusting. Looking at a frost spot and deciding
# it does not matter is still judgment, and condition_response records it.
print(f"\n{EXPERT} dismisses {by_group.loc[EXPERT, 'dismissed']} conditions, "
      f"baseline {by_group.loc['baseline', 'dismissed']}.")


# 2 -------------------------------------------------------------------------
# Where each action came from. Actions tagged "visual" are the ghost steps:
# done, never mentioned.
print()
print("=" * 70)
print("WHERE EACH ACTION CAME FROM")
print("=" * 70)
src = pd.crosstab(steps["video_id"], steps["source"])
print(src)


# 3 -------------------------------------------------------------------------
sops = load_sops()


def tasks_of(sop):
    return [(s["step"], t) for s in sop["steps"] for t in s["tasks"]]


print()
print("=" * 70)
print("SOP STRUCTURE")
print("=" * 70)
print(f"{'':<12}{'steps':>7}{'tasks':>7}{'actions':>9}{'decisions':>11}")
for g, sop in sops.items():
    ts = tasks_of(sop)
    print(f"{g:<12}{len(sop['steps']):>7}{len(ts):>7}"
          f"{sum(len(t['actions']) for _, t in ts):>9}"
          f"{sum(len(t['decision_points']) for _, t in ts):>11}")

# Matched on shared words, not exact text: "Cut slices from the section" and
# "Cut the section into slices" are the same step written two ways.
step_names = {g: [s["step"] for s in sop["steps"]] for g, sop in sops.items()}
pairs = list(zip(step_names[EXPERT], step_names["baseline"]))
matched = sum(overlap(m, b, MIN_LEN) >= 0.25 for m, b in pairs)
print(f"\n{matched} of {len(pairs)} steps line up in order. The two procedures "
      f"differ below\nthe step level, so the step name cannot tell them apart.")


# 4 -------------------------------------------------------------------------
# Tasks in one procedure with no counterpart in the other.
def unmatched(a, b, threshold=THRESHOLD):
    out = []
    for _, ta in tasks_of(a):
        best = max((overlap(ta["task"], tb["task"], MIN_LEN)
                    for _, tb in tasks_of(b)), default=0)
        if best < threshold:
            out.append(ta["task"])
    return out


print()
print("=" * 70)
print("TASKS WITH NO COUNTERPART IN THE OTHER PROCEDURE")
print("=" * 70)
for label, only in ((EXPERT, unmatched(sops[EXPERT], sops["baseline"])),
                    ("baseline", unmatched(sops["baseline"], sops[EXPERT]))):
    print(f"only in {label} ({len(only)}):")
    for t in only:
        print(f"   {t}")


# 5 -------------------------------------------------------------------------
# Both procedures say to hold the piece. Only one says what to hold it toward,
# so the blade mentions are counted and the instructions printed to be read.
print()
print("=" * 70)
print("HOW THE PIECE IS HELD - WHAT EACH PROCEDURE SAYS")
print("=" * 70)
HOLDING = r"(hold|cradle|grip|pinch|present|position|steady|brace)"
for g, sop in sops.items():
    lines = [a for _, t in tasks_of(sop) for a in t["actions"] if re.search(HOLDING, a, re.I)]
    blade = sum(1 for a in lines if "blade" in a.lower())
    print(f"\n{g}  ({len(lines)} instructions about holding, {blade} mentioning the blade)")
    for a in lines:
        print(f"   · {a}")


# 6 -------------------------------------------------------------------------
# Molly's quality control loop, read out of each SOP by _stages.py. Correct is
# about a finished slice that came out wrong, not a remnant too small to cut.
print()
print("=" * 70)
print("CONTROL LOOP: AIM, SEE, MEASURE, CORRECT")
print("=" * 70)
stages = {}
for g, sop in sops.items():
    print(f"\n{g}")
    stages[g] = read_stages(sop)
    for row in stages[g]:
        mark = "present" if row["present"] else "ABSENT "
        print(f"   {row['name']:<9}{mark:<9} {row['evidence']}")

print()
for g, rows in stages.items():
    present = [r["name"] for r in rows if r["present"]]
    print(f"{g:<10}{len(present)}/{len(rows)} stages: {', '.join(present)}")
