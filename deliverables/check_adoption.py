#!/usr/bin/env python3
"""
Did adopting Molly's SOP actually reduce slice-width variation? Point it at QA
runs from before and after the change and it reports whether the numbers moved,
and whether the move is bigger than noise.

    python deliverables/check_adoption.py --before old_runs.csv --after new_runs.csv
    python deliverables/check_adoption.py --demo   # no follow-up data yet, so split by operator
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# The technician the SOP came from, so --demo compares her against the three
# who do not work this way yet.
DEMO_ADOPTER = "molly"


def load(path: Path):
    import pandas as pd
    df = pd.read_csv(path)
    missing = {"n_slices", "std_width_mm", "mean_width_mm",
               "pct_out_of_tolerance", "passes_transfer_gate"} - set(df.columns)
    if missing:
        print(f"error: {path.name} is missing columns: {', '.join(sorted(missing))}",
              file=sys.stderr)
        sys.exit(1)
    return df


def pooled_std(df) -> float:
    """Within-run standard deviation, pooled across runs.

    Not the mean of the per-run stds, which understates spread. Pooling averages
    the variances by degrees of freedom and takes the root at the end.
    """
    import numpy as np
    dof = df["n_slices"] - 1
    return float(np.sqrt((dof * df["std_width_mm"] ** 2).sum() / dof.sum()))


def gate_rate(df) -> float:
    col = df["passes_transfer_gate"]
    return 100 * (col.astype(str).str.lower().isin(["true", "1", "yes"]).mean())


def report(before, after, label_before: str, label_after: str) -> None:
    from scipy import stats

    rows = [
        ("runs",                    len(before),                      len(after),          "",   None),
        ("slices",                  int(before["n_slices"].sum()),    int(after["n_slices"].sum()),    "",   None),
        ("pooled slice-width std",  pooled_std(before),               pooled_std(after),               "mm", "lower"),
        ("transfer gate pass rate", gate_rate(before),                gate_rate(after),                "%",  "higher"),
        ("out of tolerance",        before["pct_out_of_tolerance"].mean(), after["pct_out_of_tolerance"].mean(), "%", "lower"),
        ("mean width",              before["mean_width_mm"].mean(),   after["mean_width_mm"].mean(),   "mm", None),
    ]

    width = max(len(r[0]) for r in rows) + 2
    print(f"\n{'':<{width}}{label_before:>12}{label_after:>12}{'change':>12}")
    print("-" * (width + 36))
    for name, b, a, unit, better in rows:
        if unit == "":
            print(f"{name:<{width}}{b:>12}{a:>12}{'':>12}")
            continue
        delta = a - b
        verdict = ""
        if better:
            improved = delta < 0 if better == "lower" else delta > 0
            verdict = "  better" if improved else "  worse"
        print(f"{name:<{width}}{b:>11.2f}{unit}{a:>11.2f}{unit}{delta:>+11.2f}{unit}{verdict}")

    # Pooled std is the headline, but the test runs on the per-run values.
    # Mann-Whitney rather than a t-test, because a std is bounded below and skewed.
    u, p = stats.mannwhitneyu(before["std_width_mm"], after["std_width_mm"],
                              alternative="greater")
    print(f"\nMann-Whitney U on run-level slice-width std: p = {p:.4g}")
    if p < 0.05:
        print("The reduction is larger than run-to-run noise would explain.")
    else:
        print("Not distinguishable from noise yet. More runs, or the change has not taken.")

    print("\nWhat this does and does not tell you")
    print("  It measures whether variability fell. It cannot tell you the SOP caused it -")
    print("  anything else that changed in the same period is a candidate. Treat a pass")
    print("  here as the claim surviving a test, not as proof.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--before", type=Path, help="QA runs from before the change")
    parser.add_argument("--after", type=Path, help="QA runs from after the change")
    parser.add_argument("--demo", action="store_true",
                        help="split the existing dataset by operator instead")
    args = parser.parse_args()

    if args.demo:
        df = load(ROOT / "datasets" / "runs.csv")
        before = df[df["operator_id"] != DEMO_ADOPTER]
        after = df[df["operator_id"] == DEMO_ADOPTER]
        print("DEMONSTRATION - no follow-up data yet, so this splits the existing runs")
        print(f"by operator: everyone else vs {DEMO_ADOPTER}, who already works this way.")
        report(before, after, "others", DEMO_ADOPTER)
        return 0

    if not (args.before and args.after):
        parser.error("give --before and --after, or --demo")
    report(load(args.before), load(args.after), "before", "after")
    return 0


if __name__ == "__main__":
    sys.exit(main())
