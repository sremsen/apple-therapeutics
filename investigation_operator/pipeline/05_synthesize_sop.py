#!/usr/bin/env python3
"""
Turn the observed runs into an SOP, once for Molly and once for the other three
technicians. Both groups get the identical prompt, so any difference between the
two SOPs comes from the technicians and not from how we asked.

    python pipeline/05_synthesize_sop.py [--group GROUP] [--force]
"""

import argparse
import json
import sys
from pathlib import Path

INVESTIGATION = Path(__file__).resolve().parent.parent   # investigation_operator/
REPO = INVESTIGATION.parent                              # repository root
OUTPUT_DIR = INVESTIGATION / "output"
SOP_DIR = INVESTIGATION / "sops"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _config import (MODEL, MAX_TOKENS, EFFORT, VOCABULARY,  # noqa: E402
                     require_api_key)

# One person three times against three people once each. The prompt is told
# which, because "every run did this" means something different in each case.
GROUPS = {
    "molly":    ["molly1", "molly2", "molly3"],
    "baseline": ["alice", "georgia", "tori"],
}
GROUP_DESCRIPTION = {
    "molly":    "three runs by the SAME operator, on three different apples",
    "baseline": "three runs by THREE DIFFERENT operators, one run each",
}


# Prompts - edit these to tune synthesis behavior.

SYSTEM_PROMPT = """\
You write standard operating procedures from observed work. You are given what \
operators actually did, and you produce the procedure a new operator would follow \
to do the same job.

You write instructions, not descriptions. You do not invent steps that were never \
observed, and you do not quietly drop steps that were."""


def sop_task_prompt(group: str) -> str:
    return f"""\
Above are complete step-by-step breakdowns of {GROUP_DESCRIPTION[group]} slicing \
an apple. Each run is labeled. Every action carries timestamps, and some carry a \
condition describing something the operator was responding to.

Consolidate these runs into ONE standard operating procedure, keeping the same
three-level hierarchy the source breakdowns use:

  STEP   - a major phase of the procedure
  TASK   - a purposeful unit of work within a step
  ACTION - a single act to perform, written as an instruction

VOICE

Write instructions, not observations. "Place the apple flat on the board", not \
"The operator places the apple flat on the board". An SOP tells the next person \
what to do.

STRUCTURE TO RESOLVE

The source breakdowns describe work as it happened, so they contain three things \
an SOP should not:

  Repetition. An operator cuts several sections from one apple, so "section" and \
"slice" steps alternate. State this once as a loop - give the step a "repeats" \
value such as "Repeat for each section of the apple" - rather than listing every \
pass.

  One-off asides promoted to steps. Where a step contains a single action that is \
really a habit performed inside another step (wiping the blade, checking work in \
progress), fold it into the step it interrupts. It is an instruction, not a phase.

  Wording that differs between runs for the same work. Merge these into one step.

Record every such consolidation in synthesis_notes, one entry each, naming what \
you merged or demoted and why. Do not clean up silently - a reader must be able to \
see the difference between the source breakdowns and this procedure.

DECISION POINTS

Conditions in the source are the situations an operator responded to: bruising, an \
obstructing stem, a slice judged too thin. In an SOP these become decision points - \
the branches that make the procedure usable rather than a recipe.

For each, give the condition, the response to take, and the type:
  "adjusted"  - the operator changed what they did
  "dismissed" - the operator judged the condition and deliberately continued unchanged

Keep the dismissed ones. Knowing that a blemish can be assessed and correctly \
ignored is part of the procedure; without it a new operator discards good fruit.

COVERAGE

Give every step and every decision point an observed_in_runs count: how many of \
the three runs it appeared in. This separates core procedure from situational \
judgment, and it is the reader's guide to how firm each instruction is.

{VOCABULARY}"""


# Output schema.

DECISION_POINT = {
    "type": "object",
    "properties": {
        "condition": {"type": "string",
                      "description": "The situation that triggers this branch."},
        "response": {"type": "string",
                     "description": "What to do, as an instruction."},
        "type": {"type": "string", "enum": ["adjusted", "dismissed"]},
        "observed_in_runs": {"type": "integer"},
    },
    "required": ["condition", "response", "type", "observed_in_runs"],
    "additionalProperties": False,
}

TASK = {
    "type": "object",
    "properties": {
        "task": {"type": "string"},
        "actions": {"type": "array", "items": {"type": "string"},
                    "description": "The actions to perform, in order, "
                                   "written as instructions."},
        "decision_points": {"type": "array", "items": DECISION_POINT},
    },
    "required": ["task", "actions", "decision_points"],
    "additionalProperties": False,
}

SOP_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "steps": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "step": {"type": "string"},
                    "purpose": {"type": "string",
                                "description": "One sentence: why this step exists."},
                    "repeats": {
                        "type": ["string", "null"],
                        "description": "How the step loops, e.g. 'Repeat for each "
                                       "section of the apple'. Null if performed once.",
                    },
                    "observed_in_runs": {"type": "integer"},
                    "tasks": {"type": "array", "items": TASK},
                },
                "required": ["step", "purpose", "repeats", "observed_in_runs", "tasks"],
                "additionalProperties": False,
            },
        },
        "synthesis_notes": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Every consolidation made: steps merged, one-off asides "
                           "demoted, loops collapsed. One entry each, with the reason.",
        },
    },
    "required": ["title", "steps", "synthesis_notes"],
    "additionalProperties": False,
}


def synthesize(client, group: str, runs: dict[str, list]) -> dict:
    content = [{"type": "text",
                "text": f"RUN {i} - {video_id}:\n\n{json.dumps(actions, indent=2)}"}
               for i, (video_id, actions) in enumerate(runs.items(), 1)]
    content.append({"type": "text", "text": sop_task_prompt(group)})

    with client.messages.stream(
        model=MODEL, max_tokens=MAX_TOKENS,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": content}],
        output_config={"format": {"type": "json_schema", "schema": SOP_SCHEMA},
                       "effort": EFFORT},
    ) as stream:
        response = stream.get_final_message()

    usage = response.usage
    print(f"    tokens in={usage.input_tokens:,} out={usage.output_tokens:,}")
    return json.loads(next(b.text for b in response.content if b.type == "text"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--group", choices=list(GROUPS), help="only this group")
    parser.add_argument("--force", action="store_true",
                        help="re-run even if output already exists")
    args = parser.parse_args()

    if not require_api_key():
        return 1

    import anthropic
    client = anthropic.Anthropic()

    SOP_DIR.mkdir(exist_ok=True)
    print(f"model: {MODEL}  effort: {EFFORT}\n")

    for group in ([args.group] if args.group else GROUPS):
        out_path = SOP_DIR / f"sop_{group}.json"
        if out_path.exists() and not args.force:
            print(f"{group}: skipped (output exists)")
            continue

        runs = {}
        for video_id in GROUPS[group]:
            path = OUTPUT_DIR / f"{video_id}_merged_steps.json"
            if not path.exists():
                print(f"error: {path.name} missing. Run "
                      "pipeline/03_reconcile_steps.py first.", file=sys.stderr)
                return 1
            runs[video_id] = json.loads(path.read_text())

        total = sum(len(a) for a in runs.values())
        print(f"{group}: {len(runs)} runs, {total} actions -> Claude ...")

        sop = synthesize(client, group, runs)
        out_path.write_text(json.dumps(sop, indent=2) + "\n")

        decisions = sum(len(t["decision_points"])
                        for s in sop["steps"] for t in s["tasks"])
        print(f"    {len(sop['steps'])} steps, {decisions} decision points, "
              f"{len(sop['synthesis_notes'])} synthesis notes")
        print(f"    -> {out_path.relative_to(REPO)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
