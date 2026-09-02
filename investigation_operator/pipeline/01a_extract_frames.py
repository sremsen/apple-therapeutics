#!/usr/bin/env python3
"""
Pull one frame per second out of each video. This ensures we capture conditional
actions, such as Molly spotting a bruise and adjusting.

    python pipeline/01a_extract_frames.py [--force] [--video VIDEO_ID]
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

INVESTIGATION = Path(__file__).resolve().parent.parent   # investigation_operator/
REPO = INVESTIGATION.parent                              # repository root
VIDEO_DIR = INVESTIGATION / "videos"
FRAME_DIR = INVESTIGATION / "frames"

VIDEO_SUFFIXES = {".mov", ".mp4", ".m4v", ".avi", ".mkv"}

FRAME_INTERVAL_SEC = 1.0

# The API downscales to a 1568px long edge anyway, so pre-scaling costs no
# quality and cuts the request size by about 40%.
FRAME_LONG_EDGE = 1456
JPEG_QUALITY = 3  # ffmpeg -q:v, 2 (best) to 31 (worst)


def probe(path: Path) -> tuple[float, int, int]:
    """Return (duration_sec, width, height)."""
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "format=duration:stream=width,height",
         "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True, check=True,
    )
    values = result.stdout.split()
    width, height, duration = int(values[0]), int(values[1]), float(values[2])
    return duration, width, height


def scaled_size(width: int, height: int) -> tuple[int, int]:
    """Fit the long edge to FRAME_LONG_EDGE, never upscaling. Even dimensions."""
    long_edge = max(width, height)
    if long_edge <= FRAME_LONG_EDGE:
        return width, height
    scale = FRAME_LONG_EDGE / long_edge
    return (int(width * scale) // 2 * 2, int(height * scale) // 2 * 2)


def extract(video: Path, out_dir: Path, override: float | None = None) -> tuple[int, float]:
    """Extract frames for one video. Returns (frame_count, interval_used)."""
    duration, width, height = probe(video)
    interval = override if override else FRAME_INTERVAL_SEC
    target_w, target_h = scaled_size(width, height)

    out_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(video),
         "-vf", f"fps=1/{interval:.6f},scale={target_w}:{target_h}",
         "-q:v", str(JPEG_QUALITY),
         str(out_dir / "seq_%04d.jpg")],
        check=True,
    )

    # The fps filter emits at exactly t = 0, 1, 2..., so a frame's index is its
    # timestamp. Checked against alice, which is 30fps constant rate.
    produced = sorted(out_dir.glob("seq_*.jpg"))
    for index, frame in enumerate(produced):
        timestamp = round(index * interval)
        frame.rename(out_dir / f"frame_{timestamp:03d}s.jpg")

    return len(produced), interval


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true",
                        help="re-extract even if frames already exist")
    parser.add_argument("--video", help="only process this video_id")
    parser.add_argument("--interval", type=float, metavar="SEC",
                        help=f"seconds between frames (default {FRAME_INTERVAL_SEC})")
    args = parser.parse_args()

    if not shutil.which("ffmpeg"):
        print("error: ffmpeg not found on PATH", file=sys.stderr)
        return 1

    videos = sorted(
        p for p in VIDEO_DIR.iterdir()
        if p.suffix.lower() in VIDEO_SUFFIXES
    ) if VIDEO_DIR.is_dir() else []

    if args.video:
        videos = [p for p in videos if p.stem == args.video]

    if not videos:
        print(f"error: no videos found in {VIDEO_DIR}. "
              "Run pipeline/00_prepare_videos.py first.", file=sys.stderr)
        return 1

    print(f"{'video_id':<12} {'duration':>9} {'interval':>9} {'frames':>7}  status")
    print("-" * 58)

    total = 0
    for video in videos:
        video_id = video.stem
        out_dir = FRAME_DIR / video_id
        existing = sorted(out_dir.glob("frame_*.jpg")) if out_dir.is_dir() else []

        if existing and not args.force:
            duration, _, _ = probe(video)
            shown = args.interval or FRAME_INTERVAL_SEC
            print(f"{video_id:<12} {duration:>8.1f}s {shown:>8.2f}s "
                  f"{len(existing):>7}  skipped (already extracted)")
            total += len(existing)
            continue

        if out_dir.is_dir():
            for stale in out_dir.glob("*.jpg"):
                stale.unlink()

        duration, _, _ = probe(video)
        count, interval = extract(video, out_dir, args.interval)
        print(f"{video_id:<12} {duration:>8.1f}s {interval:>8.2f}s {count:>7}  extracted")
        total += count

    print("-" * 58)
    print(f"{'TOTAL':<12} {'':>9} {'':>9} {total:>7}")
    print(f"\nFrames in {FRAME_DIR.relative_to(REPO)}/{{video_id}}/frame_XXXs.jpg")
    return 0


if __name__ == "__main__":
    sys.exit(main())
