"""
The quality control loop Molly runs on herself: aim, see, measure, correct. I
read both SOPs and coded them by hand, so the patterns below are the sentences
that made each call rather than a general detector.
"""

import json
import re
from pathlib import Path

SOP_DIR = Path(__file__).resolve().parent / "sops"
GROUPS = ("molly", "baseline")

STAGES = [
    {
        "name": "Aim",
        "when": "before the cut",
        "pattern": r"presenting an uncut face|fresh face to the blade|"
                   r"cut face oriented toward the blade",
        "near": r"(hold|position)[^.]*(against the board|between the fingers)[^.]*",
        "near_note": "The blade is never mentioned.",
    },
    {
        "name": "See",
        "when": "during the cut",
        "pattern": r"bigger end of the section",
        "near": None,
        "near_note": "No directional rule at all.",
    },
    {
        "name": "Measure",
        "when": "after the cut",
        "pattern": r"check both sides of the blade|judge the quality of the slices",
        "near": None,
        "near_note": "No check on the slice produced.",
    },
]

# Correct is a decision, not an action, so it is found by asking what each
# procedure does about one slice that came out too thin.
CORRECT = {
    "name": "Correct",
    "when": "on out-of-spec product",
    "condition": r"too thin",
}


def load_sops() -> dict:
    """Load both SOPs. If you re-run 05, re-check the patterns above against
    the new wording - a reworded sentence reads as the stage being absent."""
    return {g: json.loads((SOP_DIR / f"sop_{g}.json").read_text()) for g in GROUPS}


def _sentences(sop):
    for step in sop["steps"]:
        for task in step["tasks"]:
            yield from task["actions"]


def _decisions(sop):
    for step in sop["steps"]:
        for task in step["tasks"]:
            yield from task["decision_points"]


def read_stages(sop) -> list[dict]:
    """Return one row per stage: is it present, and which sentence says so.

    `evidence` is what to display; `match` is the verbatim SOP sentence, so
    callers can find the task it lives in instead of re-typing the quote.
    """
    rows = []
    for spec in STAGES:
        hit = next((s for s in _sentences(sop) if re.search(spec["pattern"], s, re.I)), None)
        if hit:
            rows.append({"name": spec["name"], "when": spec["when"],
                         "present": True, "evidence": hit, "match": hit})
            continue
        near = (next((s for s in _sentences(sop) if re.search(spec["near"], s, re.I)), None)
                if spec["near"] else None)
        evidence = f"{near} {spec['near_note']}" if near else spec["near_note"]
        rows.append({"name": spec["name"], "when": spec["when"],
                     "present": False, "evidence": evidence, "match": near})

    dp = next((d for d in _decisions(sop)
               if re.search(CORRECT["condition"], d["condition"], re.I)), None)
    if dp:
        rows.append({"name": CORRECT["name"], "when": CORRECT["when"],
                     "present": dp["type"] == "adjusted",
                     "evidence": dp["response"], "match": dp["response"]})
    else:
        rows.append({"name": CORRECT["name"], "when": CORRECT["when"],
                     "present": False, "match": None,
                     "evidence": "No decision covering a slice that came out too thin."})
    return rows
