"""
aggregate_results.py (updated)

يجمع ملفات trial_results.csv من مجلدات النتائج timestamped تحت results/
ويحوّلها إلى ملف ملخّص robustness_sweep.csv بصيغة متوافقة مع src/plot_results.py
ثم يستدعي وظيفة إعادة البناء في src.plot_results.

تحسينات في هذا التحديث:
- واجهة سطر أوامر (CLI): --results-dir, --failure-threshold, --ignore, --group-by
- يدعم تجميع النتائج حسب أعمدة config مختلفة (مثل channel_2_gain, channel_1_gain, noise_std)
- يعتمد على pandas لتسهيل التجميع (أضيف pandas إلى requirements.txt)

الاستخدام البسيط:
    python aggregate_results.py

مثال مع خيارات:
    python aggregate_results.py --results-dir results --failure-threshold 1.0 --group-by channel_2_gain,channel_1_gain --ignore old_run,temp

"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd


DEFAULT_RESULTS_DIR = Path("results")
OUTPUT_CSV = DEFAULT_RESULTS_DIR / "robustness_sweep.csv"


def find_result_runs(results_dir: Path, ignore: List[str]) -> List[Path]:
    if not results_dir.exists():
        return []

    runs = [p for p in results_dir.iterdir() if p.is_dir()]

    if ignore:
        filtered = []
        for r in runs:
            if any(ig in r.name for ig in ignore):
                print(f"Ignoring run {r} (matched ignore pattern)")
                continue
            filtered.append(r)
        runs = filtered

    # sort for reproducibility
    runs.sort()
    return runs


def read_config(run_dir: Path) -> Dict:
    config_path = run_dir / "config.json"
    if not config_path.exists():
        return {}
    try:
        return json.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def read_trial_distances(run_dir: Path) -> List[float]:
    csv_path = run_dir / "trial_results.csv"
    if not csv_path.exists():
        return []

    distances: List[float] = []
    with csv_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # try a few possible column names
            for key in ("distance_error_millimeters", "distance_error_mm", "distance_mm"):
                if key in row and row[key] not in (None, ""):
                    try:
                        distances.append(float(row[key]))
                    except ValueError:
                        pass
                    break
    return distances


def extract_params_from_config(config: Dict, key: str):
    # Support nested signal_config or flat keys
    if not config:
        return np.nan

    if key in config:
        return config[key]

    # try nested signal_config
    if "signal_config" in config and isinstance(config["signal_config"], dict):
        if key in config["signal_config"]:
            return config["signal_config"][key]

    # fallback
    return np.nan


def build_dataframe_from_runs(runs: List[Path], group_by: List[str]) -> pd.DataFrame:
    rows = []

    for run in runs:
        config = read_config(run)
        distances = read_trial_distances(run)

        if not distances:
            print(f"Skipping {run}: no trial_results.csv or empty")
            continue

        # for each trial, create a row with group columns
        for d in distances:
            row = {gb: extract_params_from_config(config, gb) for gb in group_by}
            row["distance_error_mm"] = float(d)
            rows.append(row)

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    return df


def aggregate_dataframe(df: pd.DataFrame, group_by: List[str], failure_threshold: float) -> pd.DataFrame:
    # group and compute stats: mean, 95th percentile, failure rate, count
    def perc95(x):
        return np.percentile(x, 95)

    agg = df.groupby(group_by)["distance_error_mm"].agg([
        ("mean_distance_error_mm", "mean"),
        ("percentile_95_distance_error_mm", lambda x: float(np.percentile(x, 95))),
        ("trials_count", "count"),
        ("failure_rate_above_threshold_percent", lambda x: float(100.0 * np.sum(np.array(x) > failure_threshold) / x.size)),
    ]).reset_index()

    # rename failure column to expected name
    agg = agg.rename(columns={"failure_rate_above_threshold_percent": "failure_rate_above_1mm_percent"})

    # ensure expected column names exist
    # primary expected names: channel_2_gain, noise_std
    if "channel_2_gain" not in agg.columns:
        # if group_by didn't include it, we can leave as-is
        pass

    return agg


def write_robustness_csv_from_df(agg: pd.DataFrame, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # map column names to expected output order if present
    columns = []
    for col in ["channel_2_gain", "noise_std", "channel_1_gain"]:
        if col in agg.columns:
            columns.append(col)

    # standard stats
    columns.extend([
        "mean_distance_error_mm",
        "percentile_95_distance_error_mm",
        "failure_rate_above_1mm_percent",
        "trials_count",
    ])

    agg.to_csv(out_path, columns=columns, index=False, float_format="%.6f")


def parse_group_by_arg(arg: str) -> List[str]:
    if not arg:
        return ["channel_2_gain", "noise_std"]
    return [s.strip() for s in arg.split(",") if s.strip()]


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS_DIR, help="مسار مجلد النتائج (افتراضي: results)")
    parser.add_argument("--failure-threshold", type=float, default=1.0, help="عتبة الفشل بالـ mm (افتراضي: 1.0)")
    parser.add_argument("--ignore", type=str, default="", help="قائمة أسماء مجلدات لتجاهلها (مفصولة بفواصل)")
    parser.add_argument("--group-by", type=str, default="channel_2_gain,noise_std", help="أعمدة التجميع مفصولة بفواصل (افتراضي: channel_2_gain,noise_std)")

    args = parser.parse_args(argv)

    ignore_list = [s.strip() for s in args.ignore.split(",") if s.strip()]
    group_by = parse_group_by_arg(args.group_by)

    runs = find_result_runs(args.results_dir, ignore_list)
    if not runs:
        print(f"No runs found under {args.results_dir}. Create runs with run_custom.py first.")
        return 1

    print(f"Found {len(runs)} run directories. Scanning for trial_results.csv and config.json...")

    df = build_dataframe_from_runs(runs, group_by)
    if df.empty:
        print("No valid trial data found to aggregate. Exiting.")
        return 2

    agg = aggregate_dataframe(df, group_by, args.failure_threshold)

    if agg.empty:
        print("Aggregation produced no rows. Exiting.")
        return 3

    out_csv = args.results_dir / "robustness_sweep.csv"
    write_robustness_csv_from_df(agg, out_csv)
    print(f"Wrote aggregated robustness CSV to: {out_csv.resolve()}")

    # Try to invoke plot_results to rebuild the images
    try:
        print("Rebuilding plots using src.plot_results...")
        from src import plot_results
        plot_results.main()
    except Exception as e:
        print("Failed to run src.plot_results automatically:", e)
        print("You can run: python -m src.plot_results")

    return 0


if __name__ == "__main__":
    sys.exit(main())
