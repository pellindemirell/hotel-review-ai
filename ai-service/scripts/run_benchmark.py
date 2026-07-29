"""
HCOS Benchmark Runner v1
Runs all benchmark tasks against the HODIP pipeline and reports scores.
Target scores from Product Requirements:
  Clause Split:     99%
  Department Det:   98%
  Root Cause:       90%
  SOP:              92%
  Recovery:         95%
  Severity:         96%
  Action:           90%
"""

from __future__ import annotations

import json
import sys
import os
from pathlib import Path

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.evaluation.metrics import evaluate_pipeline
from app.operational_intelligence.engine import HodipEngine

GOLD_PATH = Path(r"D:\KodYazılımStaj1\datasets\gold\annotated\annotated_batch_002.json")
BENCHMARK_DIR = Path(r"D:\KodYazılımStaj1\datasets\benchmark\v1")

TARGETS = {
    "clause_split": 0.99,
    "department": 0.98,
    "failure_type": 0.90,
    "severity": 0.96,
    "root_cause": 0.90,
}


def load_gold() -> list[dict]:
    with open(GOLD_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data


def run_pipeline(gold: list[dict]) -> list[dict]:
    """Run HODIP on each gold review and return predictions."""
    engine = HodipEngine()
    predictions = []
    total = len(gold)
    for i, ann in enumerate(gold):
        if (i + 1) % 500 == 0:
            print(f"  Pipeline: {i + 1}/{total}")
        try:
            result = engine.analyze(ann["review_text"])
        except Exception:
            result = {}
        predictions.append(result)
    return predictions


def run_benchmark(gold: list[dict], predictions: list[dict]) -> dict:
    """Run all benchmark tasks and return results."""
    results = {}
    for task in TARGETS:
        scores = evaluate_pipeline(gold, predictions, task)
        results[task] = scores
        target = TARGETS[task]
        met = scores.get("accuracy", 0) >= target
        status = "PASS" if met else "FAIL"
        print(f"  {task:20s}  acc={scores.get('accuracy', 0):.4f}  p={scores.get('precision', 0):.4f}  "
              f"r={scores.get('recall', 0):.4f}  f1={scores.get('f1', 0):.4f}  "
              f"target={target:.0%}  [{status}]")
    return results


def main():
    print("=" * 72)
    print("  HCOS Benchmark v1")
    print("=" * 72)
    print()

    # Load gold annotations (use first 1000 for benchmark speed)
    print("Loading gold annotations...")
    gold = load_gold()
    gold_sample = gold[:1000]
    print(f"  Gold: {len(gold)} total, {len(gold_sample)} for benchmark")

    # Run pipeline
    print("\nRunning HODIP pipeline on gold reviews...")
    predictions = run_pipeline(gold_sample)

    # Run benchmark
    print("\nBenchmark Results:")
    print("-" * 72)
    results = run_benchmark(gold_sample, predictions)

    # Save benchmark report
    BENCHMARK_DIR.mkdir(parents=True, exist_ok=True)
    report = {
        "version": "v1",
        "date": "2026-07-13",
        "num_samples": len(gold_sample),
        "targets": TARGETS,
        "results": results,
    }
    report_path = BENCHMARK_DIR / "benchmark_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\nBenchmark report saved: {report_path}")


if __name__ == "__main__":
    main()
