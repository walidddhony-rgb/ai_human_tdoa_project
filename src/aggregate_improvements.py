"""
src/aggregate_improvements.py

تحسينات للتجميع والتحليل: قراءة ملف robustness_sweep.csv (أو تشغيل aggregate_results.py لإنشائه)،
ثم توليد تقرير تحليلي بصيغة Markdown، ملخص JSON، وبعض الرسومات الإضافية (hist, CDF, scatter).

الاستخدام مثال:
    python -m src.aggregate_improvements --input results/robustness_sweep.csv --output results/analysis --top-n 5

خيارات مهمة:
  --input: ملف CSV الملخّص (افتراضي: results/robustness_sweep.csv)
  --output: مجلد لحفظ النتائج (سيُنشأ تلقائياً)
  --top-n: عدد أفضل وأسوأ الحلات لذكرها في التقرير
  --force-aggregate: إذا لم يوجد robustness_sweep.csv، يستدعي aggregate_results.py لإنتاجه
  --group-cols: قائمة أعمدة التجميع المفروضة (افتراضي يقرأ الأعمدة من CSV)

الاعتمادات: pandas, numpy, matplotlib
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from textwrap import indent

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def ensure_robustness_csv(input_path: Path, force_aggregate: bool) -> bool:
    if input_path.exists():
        return True

    if not force_aggregate:
        return False

    print(f"{input_path} not found — attempting to run aggregate_results.py to build it...")
    try:
        subprocess.check_call([sys.executable, "aggregate_results.py"])  # run from repo root
    except Exception as e:
        print("Failed to run aggregate_results.py:", e)
        return False

    return input_path.exists()


def load_data(input_path: Path) -> pd.DataFrame:
    df = pd.read_csv(input_path)
    return df


def make_output_dir(base: Path | None) -> Path:
    if base is None:
        base = Path("results") / "analysis"
    out = Path(base)
    if out.exists():
        # add timestamp
        ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        out = out.with_name(out.name + f"_{ts}")
    out.mkdir(parents=True, exist_ok=False)
    return out


def plot_histogram(series: pd.Series, title: str, output_path: Path) -> None:
    plt.figure(figsize=(8, 5))
    plt.hist(series.dropna(), bins=40, color="#2b8cbe", edgecolor="#ffffff")
    plt.title(title)
    plt.xlabel(series.name)
    plt.ylabel("Count")
    plt.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    plt.close()


def plot_cdf(series: pd.Series, title: str, output_path: Path) -> None:
    arr = np.sort(series.dropna())
    y = np.arange(1, arr.size + 1) / arr.size
    plt.figure(figsize=(8, 5))
    plt.plot(arr, y, marker=".")
    plt.title(title)
    plt.xlabel(series.name)
    plt.ylabel("CDF")
    plt.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    plt.close()


def plot_scatter(x: pd.Series, y: pd.Series, title: str, output_path: Path) -> None:
    plt.figure(figsize=(8, 6))
    plt.scatter(x, y, c="#e6550d", alpha=0.8, edgecolors="none")
    plt.xlabel(x.name)
    plt.ylabel(y.name)
    plt.title(title)
    plt.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    plt.close()


def generate_report(df: pd.DataFrame, out_dir: Path, top_n: int = 5) -> None:
    report_md = []
    report_md.append(f"# Analysis Report\nGenerated: {datetime.utcnow().isoformat()}Z\n")

    report_md.append("## Basic summary statistics\n")
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    desc = df[numeric_cols].describe().transpose()

    report_md.append("```")
    report_md.append(desc.to_string())
    report_md.append("```")

    # Top-N best and worst by mean_distance_error_mm if present
    key_col = "mean_distance_error_mm"
    if key_col in df.columns:
        report_md.append(f"## Top {top_n} best (lowest mean distance error)")
        best = df.nsmallest(top_n, key_col)
        report_md.append(best.to_markdown(index=False))

        report_md.append(f"\n## Top {top_n} worst (highest mean distance error)")
        worst = df.nlargest(top_n, key_col)
        report_md.append(worst.to_markdown(index=False))

    # Save markdown
    md_path = out_dir / "analysis_report.md"
    md_text = "\n\n".join(report_md)
    md_path.write_text(md_text, encoding="utf-8")

    # Save JSON summary
    summary = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "rows": int(df.shape[0]),
        "columns": df.columns.tolist(),
        "numeric_columns": numeric_cols,
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")


def run_analysis(input_csv: Path, output_base: Path | None, force_aggregate: bool, top_n: int) -> int:
    ok = ensure_robustness_csv(input_csv, force_aggregate)
    if not ok:
        print(f"Input CSV not found: {input_csv}")
        return 2

    df = load_data(input_csv)
    out_dir = make_output_dir(output_base)

    # Basic plots
    if "mean_distance_error_mm" in df.columns:
        plot_histogram(df["mean_distance_error_mm"], "Histogram of Mean Distance Error (mm)", out_dir / "hist_mean_error.png")
        plot_cdf(df["mean_distance_error_mm"], "CDF of Mean Distance Error (mm)", out_dir / "cdf_mean_error.png")

    if "failure_rate_above_1mm_percent" in df.columns and "mean_distance_error_mm" in df.columns:
        plot_scatter(df["mean_distance_error_mm"], df["failure_rate_above_1mm_percent"], "Mean Error vs Failure Rate", out_dir / "scatter_mean_vs_failure.png")

    # Save a copy of the input CSV for traceability
    (out_dir / input_csv.name).write_text(input_csv.read_text(encoding="utf-8"), encoding="utf-8")

    # Generate report
    generate_report(df, out_dir, top_n=top_n)

    print(f"Analysis saved to: {out_dir.resolve()}")
    return 0


def parse_args(argv: List[str] | None = None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=Path("results/robustness_sweep.csv"), help="مسار ملف robustness_sweep.csv")
    parser.add_argument("--output", type=Path, default=Path("results/analysis"), help="مجلد إخراج التحليل")
    parser.add_argument("--force-aggregate", action="store_true", help="إذا لم يوجد robustness_sweep.csv، استدعي aggregate_results.py لبنائه")
    parser.add_argument("--top-n", type=int, default=5, help="عدد أفضل/أسوأ الحالات في التقرير")
    return parser.parse_args(argv)


if __name__ == "__main__":
    args = parse_args()
    sys.exit(run_analysis(args.input, args.output, args.force_aggregate, args.top_n))
