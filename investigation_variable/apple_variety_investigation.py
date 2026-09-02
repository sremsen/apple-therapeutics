"""
Rule out apple variety before blaming the operator. Variety was assigned at
random when I generated the data, so finding nothing here is the expected
result and a check that the method works.

    python investigation_variable/apple_variety_investigation.py
"""

from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "datasets"

runs_df = pd.read_csv(DATA_DIR / "runs.csv")
lims_df = pd.read_csv(DATA_DIR / "lims_batches.csv")
run_batch_map = pd.read_csv(DATA_DIR / "run_batch_map.csv")


# LIMS is keyed on the apple batch and QA on the production run, so map
# batch_id to run_id to get one shared key.
lims_df = lims_df.merge(run_batch_map, on='batch_id')

# A join that fans out or drops rows would change every number below, so the
# row count and match rate are checked rather than eyeballed.
before = len(runs_df)
runs_df = runs_df.merge(lims_df, on='run_id', how='left')
assert len(runs_df) == before, f"join changed row count: {before} -> {len(runs_df)}"
assert runs_df['apple_variety'].notna().all(), "some runs have no LIMS batch"
print(f"{before} runs, all matched to a LIMS batch, no duplicates from the join.")


# The question is consistency, not size, so what matters is the spread of slice
# widths within a run rather than the mean.
by_variety = (
    runs_df.groupby("apple_variety")
    .agg(
        n_runs=("run_id", "count"),
        std_width_mm=("std_width_mm", "mean"),
        pct_runs_passing_gate=("passes_transfer_gate", lambda s: 100 * s.mean()),
    )
    .round(3)
)

print()
print(by_variety)


# 0.016 mm apart on a 4 mm target, and both varieties fail the transfer gate at
# about the same rate. Variety is not what is driving the variation.
gap = by_variety["std_width_mm"].max() - by_variety["std_width_mm"].min()
print(f"\nThe two varieties differ by {gap:.3f} mm on a 4 mm target. Ruled out -"
      f"\nthe remaining candidate is the operator.")
