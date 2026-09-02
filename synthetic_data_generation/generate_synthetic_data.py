"""
Generate the synthetic QA data, with Molly's consistency written in as the
ground truth the analysis sets out to find. The operator names match the six
videos on purpose: this stands in for the measurement a plant would have taken.
"""

from pathlib import Path

import numpy as np
import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "datasets"

SEED = 42

RUNS_PER_OPERATOR = 25
SLICES_PER_RUN = (15, 20)          # inclusive range
TARGET_WIDTH_MM = 4.0
RUN_MEAN_JITTER = 0.05             # run-to-run drift around the 4mm target
TOLERANCE_MM = (3.0, 5.0)          # 4mm +/- 1mm
TRANSFER_GATE_STD = 0.5            # a run passes if its slice-width std <= this
MIN_STD_MM = 0.15                  # floor so std never goes to zero or negative

# Per-operator consistency: (center, spread) of a run's slice-width std. The
# other three differ from each other, so the analysis cannot just split in two.
OPERATOR_STD_PROFILE = {
    "molly":   (0.30, 0.05),
    "georgia": (0.65, 0.08),
    "alice":   (0.75, 0.08),
    "tori":    (0.85, 0.08),
}

rng = np.random.default_rng(SEED)


# One row per run, with the ground truth set at the run level.
run_rows = []
for run_counter, (operator_id, (std_center, std_spread)) in enumerate(
    ((op, prof) for op, prof in OPERATOR_STD_PROFILE.items() for _ in range(RUNS_PER_OPERATOR)),
    start=1,
):
    run_rows.append(
        {
            "run_id": f"run_{run_counter:03d}",
            "operator_id": operator_id,
            "n_slices": int(rng.integers(SLICES_PER_RUN[0], SLICES_PER_RUN[1] + 1)),
            "target_mean_width_mm": rng.normal(TARGET_WIDTH_MM, RUN_MEAN_JITTER),
            "target_std_width_mm": max(rng.normal(std_center, std_spread), MIN_STD_MM),
        }
    )

runs_df = pd.DataFrame(run_rows)


# Expand each run into its individual slices.
slice_rows = []
slice_counter = 1
for run in runs_df.itertuples(index=False):
    widths = rng.normal(run.target_mean_width_mm, run.target_std_width_mm, run.n_slices)
    for slice_number, width_mm in enumerate(widths, start=1):
        slice_rows.append(
            {
                "slice_id": f"slice_{slice_counter:05d}",
                "run_id": run.run_id,
                "operator_id": run.operator_id,
                "slice_number": slice_number,
                "width_mm": round(float(width_mm), 3),
            }
        )
        slice_counter += 1

slices_df = pd.DataFrame(slice_rows)


# Recompute the per-run stats from the raw slices rather than trusting the
# parameters they were drawn from.
low, high = TOLERANCE_MM
per_run = (
    slices_df.assign(out_of_tol=lambda d: (d.width_mm < low) | (d.width_mm > high))
    .groupby("run_id")
    .agg(
        mean_width_mm=("width_mm", "mean"),
        std_width_mm=("width_mm", "std"),
        pct_out_of_tolerance=("out_of_tol", lambda s: 100 * s.mean()),
    )
    .reset_index()
)

runs_df = runs_df.merge(per_run, on="run_id")
runs_df["passes_transfer_gate"] = runs_df["std_width_mm"] <= TRANSFER_GATE_STD

# target_std_width_mm is the ground truth itself, so shipping it would let one
# groupby give away the finding. Neither target column stays in the CSV.
runs_df = runs_df.drop(columns=["target_mean_width_mm", "target_std_width_mm"])

# Rounded to the precision a caliper would actually report.
runs_df = runs_df.round({"mean_width_mm": 3, "std_width_mm": 3,
                         "pct_out_of_tolerance": 2})

DATA_DIR.mkdir(exist_ok=True)
runs_df.to_csv(DATA_DIR / "runs.csv", index=False)
slices_df.to_csv(DATA_DIR / "slices.csv", index=False)

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", None)

print(f"\nruns_df   {runs_df.shape[0]} rows x {runs_df.shape[1]} cols  -> datasets/runs.csv")
print(runs_df.head())

print(f"\nslices_df {slices_df.shape[0]} rows x {slices_df.shape[1]} cols  -> datasets/slices.csv")
print(slices_df.head())

print("\nSanity check -- ground truth by operator:")
summary = (
    runs_df.groupby("operator_id")
    .agg(
        n_runs=("run_id", "count"),
        mean_width_mm=("mean_width_mm", "mean"),
        mean_std_width_mm=("std_width_mm", "mean"),
        mean_pct_out_of_tolerance=("pct_out_of_tolerance", "mean"),
        pct_runs_passing_gate=("passes_transfer_gate", lambda s: 100 * s.mean()),
    )
    .round(3)
)
print(summary)
