#!/usr/bin/env python3
"""
Run the pipeline end to end, or as much of it as this machine can. Every stage's
output is committed, so you can clone this with no API key and no videos and
still reproduce every figure and finding.

    python run_all.py              # run whatever is runnable, skip finished work
    python run_all.py --analysis   # only the stages needing no API key or video
    python run_all.py --force      # redo everything runnable, including paid calls
    python run_all.py --dry-run    # show the plan, run nothing
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

# Checked here because this file is the front door and stays 3.9-parseable. The
# stages themselves use `X | None` annotations, which are a syntax error earlier.
if sys.version_info < (3, 10):
    sys.exit("error: needs Python 3.10 or newer, found "
             f"{sys.version_info.major}.{sys.version_info.minor}")

ROOT = Path(__file__).resolve().parent
PY = sys.executable

NEEDS_VIDEO = "source videos (not committed - too large for git)"

# Must match VIDEO_SUFFIXES in 00_prepare_videos.py, or run_all reports "no
# videos" for a directory that stage 00 would happily process.
VIDEO_SUFFIXES = {".mov", ".mp4", ".m4v", ".avi", ".mkv"}
NEEDS_KEY = "ANTHROPIC_API_KEY (these stages call the API and cost money)"
NEEDS_FRAMES = "extracted frames, which need the source videos"

# script, what it needs, what it produces, roughly what it costs
STAGES = [
    ("investigation_operator/pipeline/00_prepare_videos.py",              "video",    "videos/manifest.csv",        None),
    ("investigation_operator/pipeline/01a_extract_frames.py",             "video",    "frames/",                    None),
    ("investigation_operator/pipeline/01b_transcribe.py",                 "video",    "transcripts/",               None),
    ("investigation_operator/pipeline/02a_extract_steps_from_frames.py",  "key+frames", "output/*_visual_steps.json",  "~$1.50"),
    ("investigation_operator/pipeline/02b_extract_steps_from_transcript.py", "key",   "output/*_narrated_steps.json", "~$0.20"),
    ("investigation_operator/pipeline/03_reconcile_steps.py",             "key",      "output/*_merged_steps.json", "~$1.00"),
    ("investigation_operator/pipeline/04_flatten_to_csv.py",              None,       "datasets/process_steps.csv", None),
    ("investigation_operator/pipeline/05_synthesize_sop.py",              "key",      "investigation_operator/sops/*.json", "~$0.50"),
    ("investigation_operator/pipeline/06_sop_to_docx.py",                 "frames",   "deliverables/SOP - Slicing an Apple into Sections and Slices.docx", None),
    ("investigation_variable/apple_variety_investigation.py", None,  "printed report",             None),
    ("investigation_operator/operator_approach.py",     None,  "printed report",             None),
    ("investigation_operator/figures/build_hierarchy_view.py", None, "anatomy figure",     None),
    ("investigation_operator/figures/build_alignment_view.py", None, "comparison figure",  None),
    ("deliverables/check_adoption.py --demo",      None,       "printed report",             None),
]

# Stages that skip finished work and so accept --force. Listed rather than
# inferred, because passing --force to a script that lacks it is an error.
TAKES_FORCE = {
    "01a_extract_frames.py", "01b_transcribe.py",
    "02a_extract_steps_from_frames.py", "02b_extract_steps_from_transcript.py",
    "03_reconcile_steps.py", "04_flatten_to_csv.py", "05_synthesize_sop.py",
}


def have_key() -> bool:
    if os.environ.get("ANTHROPIC_API_KEY"):
        return True
    env = ROOT / ".env"
    return env.exists() and "ANTHROPIC_API_KEY" in env.read_text()


def blocker(need, key, video, frames):
    if need is None:
        return None
    if "key" in need and not key:
        return NEEDS_KEY
    if "video" in need and not video:
        return NEEDS_VIDEO
    if "frames" in need and not frames:
        return NEEDS_FRAMES
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--analysis", action="store_true",
                    help="skip the stages that need an API key or the source videos")
    ap.add_argument("--force", action="store_true", help="redo work already done")
    ap.add_argument("--dry-run", action="store_true", help="show the plan, run nothing")
    args = ap.parse_args()

    key = have_key()
    source_dir = ROOT / "investigation_operator/original_videos"
    frame_dir = ROOT / "investigation_operator/frames"
    video = source_dir.is_dir() and any(
        p.suffix.lower() in VIDEO_SUFFIXES for p in source_dir.iterdir())
    frames = frame_dir.is_dir() and any(frame_dir.iterdir())

    print("What this machine has")
    for label, ok, note in (("source videos", video, "extraction stages need these"),
                            ("extracted frames", frames, "the SOP figures need these"),
                            ("API key", key, "the four extraction stages need this")):
        print(f"  {'yes' if ok else 'no ':<4} {label:<18} {note}")

    plan, skipped = [], []
    for script, need, produces, cost in STAGES:
        why = blocker(need, key, video, frames)
        # Frames are committed, so a frames-only stage (06) still runs here.
        if args.analysis and need is not None and ("key" in need or "video" in need):
            # Name what the stage actually needs. 06 needs frames, not a key,
            # and saying otherwise sends you looking for the wrong thing.
            wants = {"key": NEEDS_KEY, "video": NEEDS_VIDEO,
                     "key+frames": f"{NEEDS_KEY}; also {NEEDS_FRAMES}"}[need]
            why = f"--analysis: needs {wants}"
        (skipped if why else plan).append((script, produces, cost, why))

    print(f"\nWill run {len(plan)} of {len(STAGES)} stages.")
    paid = [c for _, _, c, _ in plan if c]
    if paid:
        print(f"  {len(paid)} of them call the API. Rough cost: {', '.join(paid)}.")
    if skipped:
        print("\nSkipping:")
        for script, _, _, why in skipped:
            print(f"  {Path(script.split()[0]).name:<44} {why}")
        print("\n  Their outputs are committed, so the analysis below still runs on real data.")

    if args.dry_run:
        print("\n(dry run - nothing executed)")
        return 0

    print()
    for script, produces, cost, _ in plan:
        name, *extra = script.split()
        force = ["--force"] if args.force and Path(name).name in TAKES_FORCE else []
        cmd = [PY, str(ROOT / name)] + extra + force
        print("=" * 72)
        print(f"{script}   -> {produces}")
        print("=" * 72, flush=True)   # flush, or our headers land after their output
        result = subprocess.run(cmd, cwd=ROOT)
        if result.returncode != 0:
            print(f"\n{script} exited {result.returncode}. Stopping.", file=sys.stderr)
            return result.returncode
        print()

    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
