"""run_custom.py

مستخدَم لتشغيل محاكاة مخصّصة بسهولة باستخدام ملف إعداد بسيط (YAML أو JSON)
ويحفظ مخرجات كل تشغيل في مجلد timestamped مع ملف config.json وresults.csv.

استخدام:
    python run_custom.py --config configs/example.yaml

إن لم يمرر config، يستخدم القيم الافتراضية المذكورة في AnalogSimulationConfig.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path

import yaml
import numpy as np

from src.analog_simulation import (
    AnalogSimulationConfig,
    run_simulation,
    TrialResult,
)

RESULTS_DIR = Path("results")


def load_config(path: Path | None) -> AnalogSimulationConfig:
    if path is None:
        return AnalogSimulationConfig()

    text = path.read_text(encoding="utf-8")

    if path.suffix in {".yml", ".yaml"}:
        raw = yaml.safe_load(text)
    elif path.suffix == ".json":
        raw = json.loads(text)
    else:
        raise ValueError("Config file must be .yaml/.yml or .json")

    # Map known keys into AnalogSimulationConfig
    kwargs = {}
    for key in (
        "duration_seconds",
        "numerical_points",
        "min_true_delay_seconds",
        "max_true_delay_seconds",
        "min_search_delay_seconds",
        "max_search_delay_seconds",
        "search_points",
        "trials",
        "channel_1_gain",
        "channel_2_gain",
        "channel_1_noise_std",
        "channel_2_noise_std",
        "fit_gain",
        "refine_minimum",
        "random_seed",
    ):
        if key in raw:
            kwargs[key] = raw[key]

    # Signal config nested handling (optional)
    if "signal_config" in raw:
        kwargs["signal_config"] = raw["signal_config"]

    return AnalogSimulationConfig(**kwargs)


def results_to_csv(results: list[TrialResult], output_path: Path) -> None:
    import csv

    fieldnames = [
        "trial_index",
        "true_delay_seconds",
        "estimated_delay_seconds",
        "timing_error_seconds",
        "timing_error_microseconds",
        "distance_error_millimeters",
        "minimum_energy",
        "refined_energy",
    ]

    with output_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for r in results:
            writer.writerow({
                "trial_index": r.trial_index,
                "true_delay_seconds": r.true_delay_seconds,
                "estimated_delay_seconds": r.estimated_delay_seconds,
                "timing_error_seconds": r.timing_error_seconds,
                "timing_error_microseconds": r.timing_error_microseconds,
                "distance_error_millimeters": r.distance_error_millimeters,
                "minimum_energy": r.minimum_energy,
                "refined_energy": r.refined_energy if r.refined_energy is not None else "",
            })


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=None, help="مسار ملف الإعداد YAML/JSON")
    parser.add_argument("--name", type=str, default=None, help="اسم تشغيل مخصص (يضاف إلى اسم المجلد)")
    args = parser.parse_args()

    config_path = args.config
    config = load_config(config_path)

    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")

    run_name = args.name or f"run_{timestamp}"
    out_dir = RESULTS_DIR / f"{timestamp}_{run_name}"
    out_dir.mkdir(parents=True, exist_ok=False)

    # حفظ config كـ JSON في المجلد
    config_json = json.loads(json.dumps(config.__dict__, default=lambda o: o.__dict__))
    (out_dir / "config.json").write_text(json.dumps(config_json, indent=2), encoding="utf-8")

    # شغّل المحاكاة
    print(f"Running simulation, saving results to: {out_dir}")
    results = run_simulation(config=config)

    # حفظ نتائج كل تجربة كـ CSV
    results_csv = out_dir / "trial_results.csv"
    results_to_csv(results, results_csv)

    print("Done. You can now run `python -m src.plot_results` after copying/merging CSV into results/ if desired.")


if __name__ == "__main__":
    main()
