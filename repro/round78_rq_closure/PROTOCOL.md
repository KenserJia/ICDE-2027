# RQ2/RQ3/RQ5 closure protocol

This experiment closes three open questions without a scientific-success gate.
All workload selection is performed on a calibration split and every frozen
choice is written before confirmation measurements are summarized.

## Common contract

- History state budget: 65,536 bytes, including reserved arrays, two snapshot
  slots, metadata, and declared workspace.
- Complete service budget: 131,072 bytes under the accounting implemented by
  `IntegratedService.account`.
- Four channels, public Bike Sharing and Beijing PM2.5 observations.
- A query asks for the mean over `[prefix-delay-window, prefix-delay)` and must
  return `ANSWERED/EXACT/APPROX` or `UNKNOWN`; an unanswered query is never
  assigned zero error.
- Fixed and dynamic layouts use the same base width, fine width, physical
  overlay capacity, query-history allocation, and charged bytes.
- There is no pass/fail threshold. Confidence intervals and effect signs are
  descriptive evidence, not admission gates.

## RQ3 boundary scan

The calibration split scans hotspot distance, hotspot width, and dwell time.
`fixed` retains recent fine buckets; `dynamic` scores fine buckets from the
bounded query-history ring. The frozen labels are selected deterministically:

1. **stable**: steady near-history workload;
2. **critical**: non-trivial switching workload whose paired mean MSE
   difference is closest to zero, preferring a confidence interval crossing
   zero;
3. **dynamic-dominant**: workload with the smallest dynamic-minus-fixed paired
   mean, preferring an upper confidence bound below zero.

The frozen JSON is then evaluated on the validation split. Selection and
confirmation are never performed on the same observations.

## RQ5 2 x 2 end-to-end comparison

The three frozen RQ3 workloads are replayed on independent test observations.
The two factors are history allocation (`fixed`, `dynamic`) and checkpoint
admission (`sync`, `strict`). Every cell includes exact facts, history update,
history query, checkpoint serialization, two-slot persistence, and recovery.
One-client runs report quality and cost; eight-client runs report service cost.
The fixed+sync cell is the simple end-to-end reference. Results are reported as
a quality--throughput--tail-latency--write-amplification frontier.

## RQ2 historical-range scan

Declared reach is scanned from 512 to 16,384 events at a fixed 65,536-byte
history budget. Feasible base/overlay layouts, ExactTail, and an
exponential-histogram SUM/COUNT reference are evaluated. Layout choice uses
validation observations; its precision and coverage are confirmed on test
observations. The current wording, "under fixed memory, how do historical
coverage and query precision trade off?", is retained only if the scan exposes
a reproducible reach--precision/coverage frontier. Otherwise the emitted
judgment supplies the narrower supported wording.

## Scope

The observations are public real data and the query schedules are controlled.
The durability fault model is a single-host process with a local filesystem.
The experiment does not claim distributed consensus, device failure tolerance,
or universal dominance of dynamic allocation.
