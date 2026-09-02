"""
Generate the synthetic LIMS data. Variety is assigned at random and spread
evenly across runs, so the rule-out should find nothing.
"""

from pathlib import Path

import numpy as np
import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "datasets"

SEED = 7                           # distinct from the runs/slices generator

N_RUNS = 100                       # must match generate_synthetic_data.py
RUNS_PER_BATCH = 4                 # one delivery of apples covers a day of runs
N_BATCHES = N_RUNS // RUNS_PER_BATCH
FIRST_DAY = "2024-03-04"

VARIETIES = ("Red Delicious", "Granny Smith")

rng = np.random.default_rng(SEED)


# The bridge between LIMS batch_ids and QA run_ids.
map_rows = []
for batch_number in range(1, N_BATCHES + 1):
    # A batch's runs are spread across the sequence, so variety cannot line up
    # with any ordering already in runs.csv.
    for offset in range(RUNS_PER_BATCH):
        run_number = offset * N_BATCHES + batch_number
        map_rows.append(
            {"run_id": f"run_{run_number:03d}", "batch_id": f"B-2024-{batch_number:03d}"}
        )

run_batch_map = pd.DataFrame(map_rows).sort_values("run_id", ignore_index=True)


# One row per incoming batch. Varieties are balanced then shuffled, so the
# split is near 50/50 by construction rather than by luck.
varieties = np.array(
    [VARIETIES[0]] * (N_BATCHES // 2) + [VARIETIES[1]] * (N_BATCHES - N_BATCHES // 2)
)
rng.shuffle(varieties)

lims_df = pd.DataFrame(
    {
        "batch_id": [f"B-2024-{n:03d}" for n in range(1, N_BATCHES + 1)],
        "date": pd.bdate_range(FIRST_DAY, periods=N_BATCHES).strftime("%Y-%m-%d"),
        "apple_variety": varieties,
    }
)


DATA_DIR.mkdir(exist_ok=True)
lims_df.to_csv(DATA_DIR / "lims_batches.csv", index=False)
run_batch_map.to_csv(DATA_DIR / "run_batch_map.csv", index=False)

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", None)

print(f"\nlims_df       {lims_df.shape[0]} rows x {lims_df.shape[1]} cols  -> datasets/lims_batches.csv")
print(lims_df.head())
print(f"\n{lims_df.apple_variety.value_counts().to_string()}")

print(f"\nrun_batch_map {run_batch_map.shape[0]} rows x {run_batch_map.shape[1]} cols  -> datasets/run_batch_map.csv")
print(run_batch_map.head())
