from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from run_supplement import summarize_checkpoint, summarize_trace


def write_csv(path, rows, fields):
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field) for field in fields})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    checkpoint_rows = json.loads((output / "checkpoint/raw.json").read_text())
    unit_rows = json.loads((output / "trace/unit-summary.json").read_text())
    checkpoint = summarize_checkpoint(checkpoint_rows)
    trace = summarize_trace(unit_rows)
    (output / "checkpoint/summary.json").write_text(json.dumps(checkpoint, indent=2) + "\n")
    (output / "trace/summary.json").write_text(json.dumps(trace, indent=2) + "\n")
    figure = output / "figure-data"; figure.mkdir(exist_ok=True)
    write_csv(figure / "checkpoint-frontier.csv", checkpoint,
              ["policy", "interval", "clients", "runs", "throughput_median_ops_s",
               "p99_median_ms", "p99_9_median_ms", "maximum_gap_observed",
               "checkpoint_p50_median_ms", "write_bytes_per_mutation_median",
               "complete_transient_bound_max"])
    write_csv(figure / "trace-methods.csv", trace["methods"],
              ["method", "units", "coverage_mean", "mse_mean", "nrmse_mean",
               "query_p50_us_median", "query_p95_us_median", "charged_bytes_max"])
    phase_rows = []
    for comparator, row in trace["paired_online_overlay"].items():
        for phase, phase_row in row["by_phase"].items():
            phase_rows.append({"comparator": comparator, "phase": phase, **phase_row})
    write_csv(figure / "trace-paired-phases.csv", phase_rows,
              ["comparator", "phase", "mean_mse_difference", "bootstrap95", "online_wins"])
    if (output / "FINAL_SUMMARY.json").exists():
        final = json.loads((output / "FINAL_SUMMARY.json").read_text())
        final["checkpoint_policy_summary"] = checkpoint
        final["trace_summary"] = trace
        (output / "FINAL_SUMMARY.json").write_text(json.dumps(final, indent=2) + "\n")
    print(json.dumps({"status": "reanalyzed", "output": str(output)}, indent=2))


if __name__ == "__main__":
    main()

