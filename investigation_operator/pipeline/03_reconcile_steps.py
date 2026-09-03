#!/usr/bin/env python3
"""
Merge the two accounts of each video into one, tagging every action with where
it came from. An action tagged "visual" is a ghost step: the technician did it
without mentioning it.

    python pipeline/03_reconcile_steps.py [--video ID] [--force]
"""

import argparse
import json
import sys
from pathlib import Path

INVESTIGATION = Path(__file__).resolve().parent.parent   # investigation_operator/
REPO = INVESTIGATION.parent                              # repository root
OUTPUT_DIR = INVESTIGATION / "output"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _config import (MODEL, MAX_TOKENS, EFFORT, VOCABULARY,  # noqa: E402
                     parse_json_response, require_api_key, steps_schema)


# ============================================================================
# PROMPTS - edit these to tune merge behavior
# ============================================================================

SYSTEM_PROMPT = """\
You are a process analyst reconciling two independent accounts of the same piece \
of work: one derived from video frames, one from the operator's spoken narration. \
Neither account saw the other.

Your job is to produce a single account that is truer than either, and to record \
honestly which source each part came from."""


RECONCILE_TASK_PROMPT = f"""\
Above are two independent breakdowns of the same video of one person slicing an \
apple.

  VISUAL   - derived only from still frames. It saw the hands, the knife, the \
board and the pieces, and it knows when things happened.
  NARRATED - derived only from what the operator said aloud. It knows why they \
did things, but not necessarily when, and not what they left unsaid.

Merge them into one ordered breakdown.

WHICH SOURCE WINS

  Timing and physical action  -> the VISUAL account is authoritative.
      What the hands did, in what order, with which tool, at what second.

  Cause and intent            -> the NARRATED account is authoritative.
      Why a piece was set aside, whether a mark mattered, what counted as the \
right size, whether the operator considered something a problem.

Where the two disagree about *why* something happened, take the narrated \
explanation. The operator could see the apple close up; the overhead camera \
could not. Where they disagree about *when*, take the visual timing.

TIMESTAMPS DO NOT LINE UP EXACTLY

Narration timestamps mark when the operator SPOKE, which commonly trails the act \
they are describing by one to three seconds. Two entries a couple of seconds \
apart that describe the same act are the same action - merge them, and use the \
visual timing. Do not treat a small offset as evidence of two separate events.

SOURCE ATTRIBUTION

Give every merged action a "source":

  "both"     - both accounts describe this action.
  "visual"   - only the frames account describes it. The operator did it without \
mentioning it.
  "narrated" - only the narration describes it. The operator said it, but the \
frames did not capture it, or it was not visually distinguishable.

Never drop an action because only one source reported it. An action that appears \
in one account and not the other is the most informative kind of row in this \
output - it is the whole reason both passes were run.

CONDITIONS

If either account flagged an action as conditional, the merged action stays \
conditional. Prefer the narrated wording of the condition, since cause is the \
narration's authority.

For condition_response, if the two disagree, follow the narration - whether the \
operator regarded something as worth acting on is a fact about their judgment, \
not about the pixels. An operator who says "I'm going to discard that" has \
adjusted, even if the frames read the moment as routine.

{VOCABULARY}

Write merged actions in the canonical vocabulary above, even where the narrated \
account used different words."""


# Same rows as the two input passes, plus `source`. That field is what the
# whole pipeline exists to produce.

MERGED_STEPS_SCHEMA = steps_schema(
    "One sentence beginning 'The operator ...', using the canonical vocabulary.",
    extra_properties={
        "source": {
            "type": "string",
            "enum": ["visual", "narrated", "both"],
            "description": "Which account(s) surfaced this action.",
        }
    },
)


def reconcile(client, visual: list, narrated: list) -> list[dict]:
    content = [
        {"type": "text",
         "text": "VISUAL ACCOUNT (from frames):\n\n" + json.dumps(visual, indent=2)},
        {"type": "text",
         "text": "NARRATED ACCOUNT (from the operator's speech):\n\n"
                 + json.dumps(narrated, indent=2)},
        {"type": "text", "text": RECONCILE_TASK_PROMPT},
    ]
    with client.messages.stream(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": content}],
        output_config={
            "format": {"type": "json_schema", "schema": MERGED_STEPS_SCHEMA},
            "effort": EFFORT,
        },
    ) as stream:
        response = stream.get_final_message()

    usage = response.usage
    print(f"    tokens in={usage.input_tokens:,} out={usage.output_tokens:,}")
    return parse_json_response(response)["actions"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", help="only process this video_id")
    parser.add_argument("--force", action="store_true",
                        help="re-run even if output already exists")
    args = parser.parse_args()

    if not require_api_key():
        return 1

    import anthropic
    client = anthropic.Anthropic()

    video_ids = sorted(p.stem.replace("_visual_steps", "")
                       for p in OUTPUT_DIR.glob("*_visual_steps.json"))
    if args.video:
        video_ids = [v for v in video_ids if v == args.video]
    if not video_ids:
        print("error: no *_visual_steps.json in output/. Run "
              "pipeline/02a_extract_steps_from_frames.py first.",
              file=sys.stderr)
        return 1

    print(f"model: {MODEL}  effort: {EFFORT}\n")

    for video_id in video_ids:
        visual_path = OUTPUT_DIR / f"{video_id}_visual_steps.json"
        narrated_path = OUTPUT_DIR / f"{video_id}_narrated_steps.json"
        out_path = OUTPUT_DIR / f"{video_id}_merged_steps.json"

        if not narrated_path.exists():
            print(f"{video_id}: skipped (no narrated steps - run "
                  f"pipeline/02b_extract_steps_from_transcript.py first)")
            continue
        if out_path.exists() and not args.force:
            print(f"{video_id}: skipped (output exists)")
            continue

        visual = json.loads(visual_path.read_text())
        narrated = json.loads(narrated_path.read_text())
        print(f"{video_id}: {len(visual)} visual + {len(narrated)} narrated -> Claude ...")

        actions = reconcile(client, visual, narrated)
        out_path.write_text(json.dumps(actions, indent=2) + "\n")

        by_source = {s: sum(1 for a in actions if a.get("source") == s)
                     for s in ("visual", "narrated", "both")}
        conditional = sum(1 for a in actions if a.get("condition"))
        print(f"    {len(actions)} actions  "
              f"both={by_source['both']} visual={by_source['visual']} "
              f"narrated={by_source['narrated']}  {conditional} conditional")
        print(f"    -> {out_path.relative_to(REPO)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
