#!/usr/bin/env python3
"""
Give each video a short id and link it into videos/. Three of the six clips are
Molly, so video_id is not operator_id - manifest.csv joins the two.

    python pipeline/00_prepare_videos.py [--dry-run]
"""

import argparse
import csv
import re
import subprocess
import sys
from pathlib import Path

INVESTIGATION = Path(__file__).resolve().parent.parent   # investigation_operator/
REPO = INVESTIGATION.parent                              # repository root
SOURCE_DIR = INVESTIGATION / "original_videos"
VIDEO_DIR = INVESTIGATION / "videos"
MANIFEST = VIDEO_DIR / "manifest.csv"

VIDEO_SUFFIXES = {".mov", ".mp4", ".m4v", ".avi", ".mkv"}
BASE_COLUMNS = ["video_id", "source_file", "duration_sec"]


def derive_video_id(stem: str) -> str:
    """'IMG_3390_Molly1' -> 'molly1'. Falls back to a slug of the whole stem."""
    match = re.match(r"^IMG_\d+_(.+)$", stem, flags=re.IGNORECASE)
    label = match.group(1) if match else stem
    slug = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")
    return slug or re.sub(r"[^a-z0-9]+", "_", stem.lower()).strip("_")


def probe_duration(path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(result.stdout.strip())


def load_existing_manifest() -> tuple[dict[str, dict], list[str]]:
    """Return existing rows keyed by video_id, plus any hand-added columns."""
    if not MANIFEST.exists():
        return {}, []
    with MANIFEST.open(newline="") as f:
        reader = csv.DictReader(f)
        rows = {r["video_id"]: r for r in reader if r.get("video_id")}
        extras = [c for c in (reader.fieldnames or []) if c not in BASE_COLUMNS]
    return rows, extras


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="show the derived mapping without writing anything")
    args = parser.parse_args()

    if not SOURCE_DIR.is_dir():
        print(f"error: {SOURCE_DIR} does not exist", file=sys.stderr)
        return 1

    sources = sorted(
        p for p in SOURCE_DIR.iterdir()
        if p.is_file() and p.suffix.lower() in VIDEO_SUFFIXES
    )
    if not sources:
        print(f"error: no video files found in {SOURCE_DIR}", file=sys.stderr)
        return 1

    # Two clips could reduce to the same id, so the IMG number breaks the tie.
    assigned: dict[str, Path] = {}
    for src in sources:
        video_id = derive_video_id(src.stem)
        if video_id in assigned:
            digits = re.search(r"\d+", src.stem)
            video_id = f"{video_id}_{digits.group() if digits else len(assigned)}"
        assigned[video_id] = src

    existing, extra_columns = load_existing_manifest()

    VIDEO_DIR.mkdir(exist_ok=True)
    rows = []
    print(f"{'video_id':<12} {'source_file':<26} {'duration':>9}")
    print("-" * 50)
    for video_id, src in sorted(assigned.items()):
        duration = probe_duration(src)
        link = VIDEO_DIR / f"{video_id}{src.suffix.lower()}"

        if not args.dry_run:
            # Symlink rather than copy, since these are 40-140 MB each.
            if link.is_symlink() or link.exists():
                link.unlink()
            link.symlink_to(Path("..") / SOURCE_DIR.name / src.name)

        row = {"video_id": video_id, "source_file": src.name,
               "duration_sec": f"{duration:.2f}"}
        # Carry forward operator_id and anything else added by hand.
        for column in extra_columns:
            row[column] = existing.get(video_id, {}).get(column, "")
        rows.append(row)
        print(f"{video_id:<12} {src.name:<26} {duration:>8.1f}s")

    if args.dry_run:
        print("\n(dry run - no links created, manifest not written)")
        return 0

    with MANIFEST.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=BASE_COLUMNS + extra_columns)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nLinked {len(rows)} videos into {VIDEO_DIR.relative_to(REPO)}/")
    print(f"Wrote {MANIFEST.relative_to(REPO)}"
          + (f" (preserved columns: {', '.join(extra_columns)})" if extra_columns else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
