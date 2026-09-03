#!/usr/bin/env python3
"""
Ask Claude what each technician says they are doing, from the transcript alone.
This pass never sees the frames, and it keeps their own words instead of the
canonical vocabulary.

    python pipeline/02b_extract_steps_from_transcript.py [--video ID] [--force]
"""

import argparse
import json
import sys
from pathlib import Path

INVESTIGATION = Path(__file__).resolve().parent.parent   # investigation_operator/
REPO = INVESTIGATION.parent                              # repository root
TRANSCRIPT_DIR = INVESTIGATION / "transcripts"
OUTPUT_DIR = INVESTIGATION / "output"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _config import (MODEL, MAX_TOKENS, EFFORT,  # noqa: E402
                     parse_json_response, require_api_key, steps_schema)


# ============================================================================
# PROMPTS - edit these to tune extraction behavior
# ============================================================================

SYSTEM_PROMPT = """\
You are a process analyst who documents manual procedures. You produce precise, \
timestamped breakdowns of what an operator reports doing, organized as a \
hierarchy of steps, tasks and actions.

You work only from what the operator says. You do not invent physical detail \
they did not mention."""


TRANSCRIPT_TASK_PROMPT = """\
Below is a transcript of one person narrating their own work while slicing an \
apple at a kitchen counter. Each line is prefixed with the time in seconds at \
which that speech begins.

Break down the process they describe as a hierarchy of STEPS, TASKS and ACTIONS:

  STEP   - a major phase of the process.
  TASK   - a purposeful unit of work within a step, grouping related actions.
  ACTION - a single act the operator describes performing.

Write every ACTION as one complete sentence beginning "The operator ...", in the \
present tense.

Use the operator's own words for the objects and techniques they name. If they \
say "chunk", write "chunk"; if they say "big end", write "big end". Do not \
translate their vocabulary into more standard terms - how this operator \
describes their own work is part of what is being recorded.

TIMESTAMPS

Take start_sec from the timestamp of the line in which the operator describes \
the action, and end_sec from the start of the next distinct action, or the end \
of the utterance. Note that speech often trails the act it describes by a second \
or two - do not try to correct for this. Report the times the transcript gives \
you.

WHAT TO INCLUDE, AND WHAT NOT TO

Report only actions the operator states or clearly implies they performed. If \
they describe a general habit ("I always start from the bigger end"), record it \
as an action only where the transcript indicates they are doing it in this run.

Do not infer actions that must have happened but are never mentioned. Silence in \
the narration is itself a finding - the reconcile pass depends on this pass \
reporting only what was actually said.

CONDITIONAL ACTIONS

Pay particular attention to anything the operator does in response to something \
they encounter, rather than as a routine part of the procedure - a bruise, a \
blemish, discoloration, an awkward shape, a piece that came out wrong, a piece \
judged the wrong size.

For each action, set:

  condition          - what the operator says they are responding to, or null if \
the action is simply a routine part of the procedure.
  condition_response - "adjusted" if they say the condition changed what they did;
                       "dismissed" if they notice something, judge it, and say it \
does not change their approach;
                       null if no condition is involved.

The "dismissed" case matters as much as "adjusted". An operator saying "that's \
just frost, so it shouldn't affect my cutting" has evaluated a condition and \
decided against acting - record that, do not discard it."""


# Same fields as the frames pass so the two merge cleanly. Only the action
# wording differs: this pass keeps the technician's own words.

STEPS_SCHEMA = steps_schema(
    "One sentence beginning 'The operator ...', in the operator's own vocabulary."
)


def extract_steps(client, transcript: str) -> list[dict]:
    content = [
        {"type": "text", "text": "TRANSCRIPT\n\n" + transcript},
        {"type": "text", "text": TRANSCRIPT_TASK_PROMPT},
    ]
    with client.messages.stream(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": content}],
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
    parser.add_argument("--force", action="store_true",
                        help="re-run even if output already exists")
    args = parser.parse_args()

    if not require_api_key():
        return 1

    import anthropic
    client = anthropic.Anthropic()

    paths = sorted(TRANSCRIPT_DIR.glob("*.txt"))
    if args.video:
        paths = [p for p in paths if p.stem == args.video]
    if not paths:
        print(f"error: no transcripts in {TRANSCRIPT_DIR}. "
              "Run pipeline/01b_transcribe.py first.", file=sys.stderr)
        return 1

    OUTPUT_DIR.mkdir(exist_ok=True)
    print(f"model: {MODEL}  effort: {EFFORT}\n")

    for path in paths:
        video_id = path.stem
        out_path = OUTPUT_DIR / f"{video_id}_narrated_steps.json"
        if out_path.exists() and not args.force:
            print(f"{video_id}: skipped (output exists)")
            continue

        transcript = path.read_text().strip()
        print(f"{video_id}: {len(transcript.split())} words -> Claude ...")

        actions = extract_steps(client, transcript)
        out_path.write_text(json.dumps(actions, indent=2) + "\n")

        conditional = sum(1 for a in actions if a.get("condition"))
        print(f"    {len(actions)} actions, {conditional} conditional"
              f"  -> {out_path.relative_to(REPO)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
