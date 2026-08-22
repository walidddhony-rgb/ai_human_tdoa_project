"""
aggregate_results.py

يجمع ملفات trial_results.csv من مجلدات النتائج timestamped تحت results/
ويحوّلها إلى ملف ملخّص robustness_sweep.csv بصيغة متوافقة مع src/plot_results.py
ثم يستدعي وظيفة إعادة البناء في src.plot_results.

الاستخدام:
    python aggregate_results.py

خيارات (مستقبلية يمكن إضافتها): تحديد مجلد نتائج معين، تغيير عتبة الفشل، خروج بصيغة مختلفة.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np

RESULTS_DIR = Path("results")
OUTPUT_CSV = RESULTS_DIR / "robustness_sweep.csv"


def find_result_runs(results_dir: Path) -> List[Path]:
    if not results_dir.exists():
        return []

    runs = [p for p in results_dir.iterdir() if p.is_dir()]
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


def extract_params_from_config(config: Dict) -> Tuple[float, float]:
    # channel gain
    gain = None
    for key in ("channel_2_gain", "channel_gain", "gain"):
        if key in config:
            gain = config[key]
            break

    # noise std
    noise = None
    for key in ("channel_2_noise_std", "noise_std", "channel_2_noise", "channel_noise_std"):
        if key in config:
            noise = config[key]
            break

    # fallback to None -> np.nan
    try:
        gain_val = float(gain) if gain is not None else float('nan')
    except Exception:
        gain_val = float('nan')

    try:
        noise_val = float(noise) if noise is not None else float('nan')
    except Exception:
        noise_val = float('nan')

    return gain_val, noise_val


def aggregate_runs(runs: List[Path]) -> List[Dict]:
    # map from (gain, noise) -> list of distance values
    buckets: Dict[Tuple[float, float], List[float]] = {}

    for run in runs:
        config = read_config(run)
        gain, noise = extract_params_from_config(config)
        distances = read_trial_distances(run)

        if not distances:
            print(f"Skipping {run}: no trial_results.csv or empty")
            continue

        key = (gain, noise)
        buckets.setdefault(key, []).extend(distances)

    rows = []
    for (gain, noise), values in sorted(buckets.items()):
        arr = np.asarray(values, dtype=np.float64)
        mean_distance = float(np.mean(arr))
        perc95 = float(np.percentile(arr, 95))
        failure_rate = float(100.0 * np.sum(arr > 1.0) / arr.size)
        trials_count = int(arr.size)

        rows.append(
            {
                "channel_2_gain": gain,
                "noise_std": noise,
                "mean_distance_error_mm": mean_distance,
                "percentile_95_distance_error_mm": perc95,
                "failure_rate_above_1mm_percent": failure_rate,
                "trials_count": trials_count,
            }
        )

    return rows


def write_robustness_csv(rows: List[Dict], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "channel_2_gain",
        "noise_std",
        "mean_distance_error_mm",
        "percentile_95_distance_error_mm",
        "failure_rate_above_1mm_percent",
        "trials_count",
    ]

    with out_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            # ensure simple types
            writer.writerow({k: ("" if (v is None or (isinstance(v, float) and np.isnan(v))) else v) for k, v in r.items()})


def main() -> int:
    runs = find_result_runs(RESULTS_DIR)
    if not runs:
        print("No runs found under results/ directory. Create runs with run_custom.py first.")
        return 1

    print(f"Found {len(runs)} run directories. Scanning for trial_results.csv and config.json...")

    rows = aggregate_runs(runs)

    if not rows:
        print("No valid data found to aggregate. Exiting.")
        return 2

    write_robustness_csv(rows, OUTPUT_CSV)
    print(f"Wrote aggregated robustness CSV to: {OUTPUT_CSV.resolve()}")

    # Try to invoke plot_results to rebuild the images
    try:
        print("Rebuilding plots using src.plot_results...")
        # Import and call main
        from src import plot_results

        # plot_results.main will read results/robustness_sweep.csv by default
        plot_results.main()
    except Exception as e:
        print("Failed to run src.plot_results automatically:", e)
        print("You can run: python -m src.plot_results")

    return 0


if __name__ == "__main__":
    sys.exit(main())
