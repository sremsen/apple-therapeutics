#!/usr/bin/env python3
"""
Transcribe what each technician says while they work. Runs Whisper locally, so
there is no API key and no per-minute cost.

    python pipeline/01b_transcribe.py [--force] [--video VIDEO_ID] [--model REPO]
"""

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

INVESTIGATION = Path(__file__).resolve().parent.parent   # investigation_operator/
REPO = INVESTIGATION.parent                              # repository root
VIDEO_DIR = INVESTIGATION / "videos"
TRANSCRIPT_DIR = INVESTIGATION / "transcripts"

VIDEO_SUFFIXES = {".mov", ".mp4", ".m4v", ".avi", ".mkv"}

# large-v3 is the most accurate Whisper checkpoint, and these clips total under
# five minutes, so there is no reason to trade accuracy for speed.
MODEL_REPO = "mlx-community/whisper-large-v3-mlx"

# Whisper conditions on this text, which fixes the spelling of words it would
# otherwise mangle. Keep it about the domain, not about any one video.
INITIAL_PROMPT = (
    "A person narrates while slicing an apple on a cutting board: core, stem, "
    "seeds, bruise, blemish, peel, skin, wedge, slice, half, quarter, "
    "paring knife, chef's knife, cutting board."
)

# Whisper expects 16 kHz mono.
AUDIO_SAMPLE_RATE = 16000


def extract_audio(video: Path, wav_path: Path) -> None:
    subprocess.run(
        ["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(video),
         "-vn", "-ac", "1", "-ar", str(AUDIO_SAMPLE_RATE),
         "-c:a", "pcm_s16le", str(wav_path)],
        check=True,
    )


def format_transcript(segments: list[dict]) -> str:
    """One timestamped line per segment: '[12.4s] text'."""
    lines = []
    for segment in segments:
        text = segment["text"].strip()
        if text:
            lines.append(f"[{segment['start']:.1f}s] {text}")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true",
                        help="re-transcribe even if a transcript already exists")
    parser.add_argument("--video", help="only process this video_id")
    parser.add_argument("--model", default=MODEL_REPO,
                        help=f"Whisper MLX repo (default: {MODEL_REPO})")
    args = parser.parse_args()

    if not shutil.which("ffmpeg"):
        print("error: ffmpeg not found on PATH", file=sys.stderr)
        return 1

    import mlx_whisper  # imported late so --help stays fast

    videos = sorted(
        p for p in VIDEO_DIR.iterdir() if p.suffix.lower() in VIDEO_SUFFIXES
    ) if VIDEO_DIR.is_dir() else []
    if args.video:
        videos = [p for p in videos if p.stem == args.video]
    if not videos:
        print(f"error: no videos found in {VIDEO_DIR}. "
              "Run pipeline/00_prepare_videos.py first.", file=sys.stderr)
        return 1

    TRANSCRIPT_DIR.mkdir(exist_ok=True)
    print(f"whisper model: {args.model}\n")
    print(f"{'video_id':<12} {'segments':>9} {'words':>7} {'elapsed':>9}  status")
    print("-" * 56)

    for video in videos:
        video_id = video.stem
        txt_path = TRANSCRIPT_DIR / f"{video_id}.txt"
        json_path = TRANSCRIPT_DIR / f"{video_id}.json"

        if txt_path.exists() and not args.force:
            words = len(txt_path.read_text().split())
            print(f"{video_id:<12} {'-':>9} {words:>7} {'-':>9}  skipped (exists)")
            continue

        started = time.time()
        with tempfile.TemporaryDirectory() as tmp:
            wav = Path(tmp) / f"{video_id}.wav"
            extract_audio(video, wav)
            result = mlx_whisper.transcribe(
                str(wav),
                path_or_hf_repo=args.model,
                initial_prompt=INITIAL_PROMPT,
                word_timestamps=False,
                verbose=None,
            )

        segments = result.get("segments", [])
        txt_path.write_text(format_transcript(segments))
        json_path.write_text(json.dumps(
            {"video_id": video_id, "model": args.model,
             "language": result.get("language"),
             "text": result.get("text", "").strip(),
             "segments": [
                 {"start": s["start"], "end": s["end"], "text": s["text"].strip()}
                 for s in segments
             ]},
            indent=2,
        ))

        elapsed = time.time() - started
        words = len(result.get("text", "").split())
        print(f"{video_id:<12} {len(segments):>9} {words:>7} {elapsed:>8.1f}s  transcribed")

    print(f"\nTranscripts in {TRANSCRIPT_DIR.relative_to(REPO)}/{{video_id}}.txt")
    return 0


if __name__ == "__main__":
    sys.exit(main())
