#!/usr/bin/env python3
"""
Flatten every video's merged breakdown into one table. It does not attach
operator_id, because three of the clips are the same person - join that from
videos/manifest.csv.

    python pipeline/04_flatten_to_csv.py [--force]
"""

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

INVESTIGATION = Path(__file__).resolve().parent.parent   # investigation_operator/
REPO = INVESTIGATION.parent                              # repository root
OUTPUT_DIR = INVESTIGATION / "output"
DATASET_DIR = REPO / "datasets"
CSV_PATH = DATASET_DIR / "process_steps.csv"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _config import steps_schema  # noqa: E402

# The columns are whatever the merged rows carry, so adding a field upstream
# cannot leave it out of the dataset.
COLUMNS = ["video_id"] + list(
    steps_schema("", extra_properties={"source": {}})
    ["properties"]["actions"]["items"]["properties"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true",
                        help="overwrite an existing process_steps.csv")
    args = parser.parse_args()

    if CSV_PATH.exists() and not args.force:
        print(f"{CSV_PATH.relative_to(REPO)} exists. Pass --force to overwrite.")
        return 0

    merged = sorted(OUTPUT_DIR.glob("*_merged_steps.json"))
    if not merged:
        print("error: no *_merged_steps.json in output/. Run "
              "pipeline/03_reconcile_steps.py first.", file=sys.stderr)
        return 1

    rows = []
    for path in merged:
        video_id = path.stem.replace("_merged_steps", "")
        for action in json.loads(path.read_text()):
            rows.append({"video_id": video_id,
                         **{c: action.get(c) for c in COLUMNS if c != "video_id"}})

    DATASET_DIR.mkdir(exist_ok=True)
    with CSV_PATH.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    # Doubles as a sanity check. A video with no conditional actions usually
    # means a pass returned less than it should have.
    print(f"{'video_id':<10}{'actions':>8}{'cond':>6}{'adj':>5}{'dis':>5}"
          f"{'both':>6}{'visual':>8}{'narrated':>10}")
    print("-" * 58)
    for video_id in sorted({r["video_id"] for r in rows}):
        v = [r for r in rows if r["video_id"] == video_id]
        src = Counter(r["source"] for r in v)
        resp = Counter(r["condition_response"] for r in v)
        print(f"{video_id:<10}{len(v):>8}"
              f"{sum(1 for r in v if r['condition']):>6}"
              f"{resp['adjusted']:>5}{resp['dismissed']:>5}"
              f"{src['both']:>6}{src['visual']:>8}{src['narrated']:>10}")

    src = Counter(r["source"] for r in rows)
    resp = Counter(r["condition_response"] for r in rows)
    print("-" * 58)
    print(f"{'TOTAL':<10}{len(rows):>8}"
          f"{sum(1 for r in rows if r['condition']):>6}"
          f"{resp['adjusted']:>5}{resp['dismissed']:>5}"
          f"{src['both']:>6}{src['visual']:>8}{src['narrated']:>10}")
    print(f"\n-> {CSV_PATH.relative_to(REPO)}  ({len(rows)} rows, "
          f"{len(merged)} videos)")
    print("   join operator_id / operator_type from videos/manifest.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
