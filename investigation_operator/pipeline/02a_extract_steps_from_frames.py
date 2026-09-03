#!/usr/bin/env python3
"""
Ask Claude what it sees each technician doing, from the frames alone. This pass
never sees the transcript, so what it finds and the narration misses are the
ghost steps.

    python pipeline/02a_extract_steps_from_frames.py [--video VIDEO_ID] [--every N] [--force]
"""

import argparse
import base64
import json
import re
import sys
from pathlib import Path

INVESTIGATION = Path(__file__).resolve().parent.parent   # investigation_operator/
REPO = INVESTIGATION.parent                              # repository root
FRAME_DIR = INVESTIGATION / "frames"
OUTPUT_DIR = INVESTIGATION / "output"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _config import (MODEL, MAX_TOKENS, EFFORT, VOCABULARY,  # noqa: E402
                     parse_json_response, require_api_key, steps_schema)


# ============================================================================
# PROMPTS - edit these to tune extraction behavior
# ============================================================================

SYSTEM_PROMPT = """\
You are a process analyst who documents manual procedures from video. You produce \
precise, literal, timestamped breakdowns of what an operator physically does, \
organized as a hierarchy of steps, tasks and actions.

You describe only what is visually evident in the frames you are given. You do not \
speculate about intent, skill or reasoning that the images do not support."""


FRAMES_TASK_PROMPT = f"""\
The images above are sequential still frames from a single video of one person \
slicing an apple at a kitchen counter. The camera is fixed overhead and does not \
move. Each frame is labeled with its timestamp in seconds from the start of the \
video.

These are stills, so motion between frames is inferred rather than directly \
observed. Describe what the frames actually support.

Break the process down as a hierarchy of STEPS, TASKS and ACTIONS:

  STEP   - a major phase of the process.
           Shape: "Section the apple", "Cut sections into slices".
  TASK   - a purposeful unit of work within a step, grouping related actions.
           Shape: "Establish a flat face", "Clear cut slices from the board".
  ACTION - a single physical act, typically spanning 2 to 5 seconds.

Write every ACTION as one complete sentence beginning "The operator ...", in the \
present tense. Name the tool, the object acted on, and where it came from or went \
to, whenever those are visible.

Where both hands are doing something, say what each is doing - what the \
non-cutting hand is holding, bracing or positioning, as well as what the cutting \
hand is doing. How an operator uses their two hands together is the clearest \
visible difference between one operator and another.

Be specific about technique: how the blade meets the piece, whether the cut is a \
single downward press or a drawn stroke, how the piece is steadied, and how the \
grip changes between cuts. Prefer the concrete description over the general one - \
"presses the blade straight down through the section" rather than "cuts the \
section".

For example:

  "The operator pins the section against the board with the fingers of their left \
hand and presses the knife straight down through it with their right, cutting a \
slice."
  "The operator holds the section upright on its cut face in their left hand and \
draws the blade toward themselves in a single stroke, letting the slice fall to \
the board."
  "The operator slides the cut slice to the right side of the board with the flat \
of the knife."

Give every action a start_sec and an end_sec drawn from the frame timestamps that \
bracket it.

Do not collapse repetition. If the operator cuts eight similar slices, report eight \
separate actions each with its own timestamps - never a single action that says \
"repeats eight times".

{VOCABULARY}

CONDITIONAL ACTIONS

Pay particular attention to anything the operator does in response to something \
they encounter, rather than as a routine part of the procedure - an irregular \
surface, a bruise, discoloration, an awkward shape, a piece that came out wrong.

For each action, set:

  condition          - what the operator appears to be responding to, or null if \
the action is simply a routine part of the procedure.
  condition_response - "adjusted" if the condition visibly changed what they did;
                       "dismissed" if they appear to inspect something and then \
carry on without changing their approach;
                       null if no condition is involved.

Record a condition only where the frames give you visible reason to. Do not invent \
one in order to fill the field."""


# Enforced server-side, so the response is always valid JSON.

STEPS_SCHEMA = steps_schema(
    "One sentence beginning 'The operator ...', using the canonical vocabulary."
)


def frame_timestamp(path: Path) -> int:
    match = re.search(r"frame_(\d+)s", path.stem)
    return int(match.group(1)) if match else 0


def build_content(frames: list[Path]) -> list[dict]:
    """Label each frame with its timestamp, then add the task prompt.

    Without the labels Claude can order the frames but cannot say when anything
    happened, so start_sec and end_sec depend on them.
    """
    content: list[dict] = []
    for frame in frames:
        content.append({"type": "text", "text": f"Frame t={frame_timestamp(frame)}s:"})
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/jpeg",
                "data": base64.standard_b64encode(frame.read_bytes()).decode(),
            },
        })
    content.append({"type": "text", "text": FRAMES_TASK_PROMPT})
    return content


def extract_steps(client, frames: list[Path]) -> list[dict]:
    with client.messages.stream(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": build_content(frames)}],
        output_config={
            "format": {"type": "json_schema", "schema": STEPS_SCHEMA},
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
    parser.add_argument("--every", type=int, default=1, metavar="N",
                        help="use every Nth extracted frame (default 1 = all). "
                             "Frames are one second apart, so --every 3 samples "
                             "every 3 seconds.")
    parser.add_argument("--force", action="store_true",
                        help="re-run even if output already exists")
    parser.add_argument("--from", dest="t_from", type=float, metavar="SEC",
                        help="only use frames at or after this timestamp")
    parser.add_argument("--to", dest="t_to", type=float, metavar="SEC",
                        help="only use frames at or before this timestamp")
    parser.add_argument("--out", metavar="PATH",
                        help="write to this path instead of output/{id}_visual_steps.json")
    args = parser.parse_args()

    if not require_api_key():
        return 1

    import anthropic
    client = anthropic.Anthropic()

    video_ids = sorted(p.name for p in FRAME_DIR.iterdir()
                       if p.is_dir()) if FRAME_DIR.is_dir() else []
    if args.video:
        video_ids = [v for v in video_ids if v == args.video]
    if not video_ids:
        print(f"error: no frame folders in {FRAME_DIR}. "
              "Run pipeline/01a_extract_frames.py first.", file=sys.stderr)
        return 1

    OUTPUT_DIR.mkdir(exist_ok=True)
    print(f"model: {MODEL}  effort: {EFFORT}  sampling: every {args.every} frame(s)\n")

    for video_id in video_ids:
        out_path = Path(args.out) if args.out else OUTPUT_DIR / f"{video_id}_visual_steps.json"
        if out_path.exists() and not args.force:
            print(f"{video_id}: skipped (output exists)")
            continue

        frames = sorted(
            (FRAME_DIR / video_id).glob("frame_*.jpg"), key=frame_timestamp
        )[::args.every]
        if args.t_from is not None:
            frames = [f for f in frames if frame_timestamp(f) >= args.t_from]
        if args.t_to is not None:
            frames = [f for f in frames if frame_timestamp(f) <= args.t_to]
        print(f"{video_id}: {len(frames)} frames -> Claude ...")

        actions = extract_steps(client, frames)
        out_path.write_text(json.dumps(actions, indent=2) + "\n")

        conditional = sum(1 for a in actions if a.get("condition"))
        print(f"    {len(actions)} actions, {conditional} conditional"
              f"  -> {out_path.relative_to(REPO) if out_path.is_relative_to(REPO) else out_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
