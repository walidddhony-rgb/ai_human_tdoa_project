"""Updated run_custom.py

Improvements:
- Accept direct CLI overrides for core AnalogSimulationConfig fields
  (e.g., --trials, --numerical-points, --min-true-delay-seconds, ...)
- Add --workers to run trials in parallel by splitting trials across workers.
- Overrides take precedence over config file values.
- Writes combined trial_results.csv when using parallel workers.

Usage examples:
  python run_custom.py --config configs/example.yaml --name my_sweep
  python run_custom.py --trials 200 --workers 4 --name parallel_run

Note: parallel mode uses multiprocessing.ProcessPoolExecutor and may start multiple
Python processes; ensure your environment has enough CPU and memory.
"""

from __future__ import annotations

import argparse
import csv
import json
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import yaml

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
    kwargs: Dict[str, Any] = {}
    keys = (
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
    )

    for key in keys:
        if key in raw:
            kwargs[key] = raw[key]

    # Signal config nested handling (optional)
    if "signal_config" in raw:
        kwargs["signal_config"] = raw["signal_config"]

    return AnalogSimulationConfig(**kwargs)


def results_to_csv(results: List[TrialResult], output_path: Path) -> None:
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


# Helper run function used by worker processes. Must be top-level for pickling.
def _worker_run_simulation(config_kwargs: Dict[str, Any]) -> List[Dict[str, Any]]:
    # Import inside worker to ensure module state is fresh
    from src.analog_simulation import AnalogSimulationConfig, run_simulation

    cfg = AnalogSimulationConfig(**config_kwargs)
    results = run_simulation(cfg)

    # Convert TrialResult dataclasses to plain dicts
    out = []
    for r in results:
        out.append({
            "trial_index": r.trial_index,
            "true_delay_seconds": r.true_delay_seconds,
            "estimated_delay_seconds": r.estimated_delay_seconds,
            "timing_error_seconds": r.timing_error_seconds,
            "timing_error_microseconds": r.timing_error_microseconds,
            "distance_error_millimeters": r.distance_error_millimeters,
            "minimum_energy": r.minimum_energy,
            "refined_energy": r.refined_energy if r.refined_energy is not None else None,
        })
    return out


def merge_worker_results(dicts: List[List[Dict[str, Any]]]) -> List[TrialResult]:
    # Flatten and convert back to TrialResult-like objects (we'll use simple namespace dataclass)
    from types import SimpleNamespace

    flat = [item for sub in dicts for item in sub]
    results: List[TrialResult] = []

    for idx, d in enumerate(flat, start=1):
        # create a SimpleNamespace with same attributes as TrialResult; it will work with metrics code
        obj = SimpleNamespace(
            trial_index=int(d.get("trial_index", idx)),
            true_delay_seconds=float(d.get("true_delay_seconds", 0.0)),
            estimated_delay_seconds=float(d.get("estimated_delay_seconds", 0.0)),
            timing_error_seconds=float(d.get("timing_error_seconds", 0.0)),
            timing_error_microseconds=float(d.get("timing_error_microseconds", 0.0)),
            distance_error_millimeters=float(d.get("distance_error_millimeters", 0.0)),
            minimum_energy=float(d.get("minimum_energy", 0.0)),
            refined_energy=d.get("refined_energy", None),
        )
        results.append(obj)

    return results


def parse_override_args(overrides: List[str]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for item in overrides:
        if "=" not in item:
            continue
        k, v = item.split("=", 1)
        # try to cast to number or bool
        if v.lower() in {"true", "false"}:
            val = v.lower() == "true"
        else:
            try:
                if "." in v:
                    val = float(v)
                else:
                    val = int(v)
            except Exception:
                val = v
        out[k] = val
    return out


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument("--config", type=Path, default=None, help="مسار ملف الإعداد YAML/JSON")
    parser.add_argument("--name", type=str, default=None, help="اسم تشغيل مخصص (يضاف إلى اسم المجلد)")

    # Direct overrides (key=value) applied after config file
    parser.add_argument("--override", type=str, action="append", default=[], help="Override config field as key=value (يمكن تكراره)")

    # Common parameters available as first-class options for convenience
    parser.add_argument("--trials", type=int, default=None, help="عدد التجارب (يتجاوز value في config)")
    parser.add_argument("--numerical-points", type=int, default=None, help="عدد نقاط الحساب العددي")
    parser.add_argument("--duration-seconds", type=float, default=None, help="مدة الإشارة بالثواني")

    # Parallel workers
    parser.add_argument("--workers", type=int, default=1, help="عدد العمليات المتوازية؛ 1 يعني تسلسلي")

    args = parser.parse_args()

    config = load_config(args.config)

    # Apply direct option overrides
    if args.trials is not None:
        config = AnalogSimulationConfig(**{**config.__dict__, "trials": args.trials})
    if args.numerical_points is not None:
        config = AnalogSimulationConfig(**{**config.__dict__, "numerical_points": args.numerical_points})
    if args.duration_seconds is not None:
        config = AnalogSimulationConfig(**{**config.__dict__, "duration_seconds": args.duration_seconds})

    # Apply key=value overrides
    overrides = parse_override_args(args.override)
    if overrides:
        # convert config to dict, update, then rebuild
        cfg_dict = dict(config.__dict__)
        cfg_dict.update(overrides)
        config = AnalogSimulationConfig(**cfg_dict)

    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    run_name = args.name or f"run_{timestamp}"
    out_dir = RESULTS_DIR / f"{timestamp}_{run_name}"
    out_dir.mkdir(parents=True, exist_ok=False)

    # save config.json
    config_json = json.loads(json.dumps(config.__dict__, default=lambda o: o.__dict__))
    (out_dir / "config.json").write_text(json.dumps(config_json, indent=2), encoding="utf-8")

    # Run simulation (serial or parallel)
    if args.workers <= 1:
        print(f"Running simulation (serial) with {config.trials} trials...")
        results = run_simulation(config=config)

    else:
        workers = args.workers
        total = config.trials
        base = total // workers
        remainder = total % workers

        # build per-worker configs
        worker_configs: List[Dict[str, Any]] = []
        seed = config.random_seed
        for i in range(workers):
            n = base + (1 if i < remainder else 0)
            cfg_dict = dict(config.__dict__)
            cfg_dict["trials"] = n
            # give each worker a different seed
            cfg_dict["random_seed"] = int(seed + i + 1)
            worker_configs.append(cfg_dict)

        print(f"Running simulation in parallel using {workers} workers (total {total} trials)")

        dict_results: List[List[Dict[str, Any]]] = []
        with ProcessPoolExecutor(max_workers=workers) as exc:
            futures = [exc.submit(_worker_run_simulation, wc) for wc in worker_configs]
            for fut in futures:
                dict_results.append(fut.result())

        # merge results into TrialResult-like objects
        results = merge_worker_results(dict_results)

    # save combined CSV
    results_csv = out_dir / "trial_results.csv"
    results_to_csv(results, results_csv)

    print(f"Done. Results saved to: {out_dir.resolve()}")


if __name__ == "__main__":
    main()
