# Reproduction contract

## What can match exactly

Dataset preparation must reproduce all stored train/validation/test/mean/std arrays exactly. The final core modules are unchanged. Deterministic validation choices, query schedules, predictions and quality metrics can be compared to the recorded values. Record sorting, ZIP timestamps, process IDs and checkpoint scheduling can alter container bytes/metadata without altering the target arrays or answers.

## What must be remeasured

The 138 joint timing runs, native concurrency/paced arrivals, memory diagnostics and 30-minute run depend on hardware, OS scheduling, file synchronization, Python runtime and instrumented buffers. Compare the distributions and operating conditions, not a promise of identical throughput. Three repeated timing runs are technical repeats. Twelve stations are correlated. No Linux/x86 timing confirmation is included in the paper evidence.

## Input and output separation

`run` copies low-level drivers/core into a new workspace, copies packaged observation arrays, and materializes only declared older calibration/selection inputs. It does not copy the experiment's published output into its destination. Every run writes logs, a protocol record and RUN.json. Existing destinations are rejected. Recorded evidence stays read-only. Helper `materialize` losslessly decodes large gzip records into an isolated runtime layout expected by the frozen drivers.

`tables` and `figures` recompute displays from recorded values and explicitly label themselves as rebuilds. `smoke` tests behavior and is explicitly not a full protocol. `provenance/VALIDATION.json` lists the checks actually executed during packaging. CI is provided as a future check configuration, not as evidence that GitHub-hosted execution has already occurred.

## Resource and failure semantics

History-only allocation, full joint state and native-only scheduling studies use distinct ledgers. Do not pool their accuracy/speed numbers. The logical ledger is not a physical RAM bound; whole-process memory includes telemetry and instrumentation. The K recovery bound assumes the latest completed valid image, and older corruption fallback can exceed K. Histogram code is a bounded-time-block V-optimal adaptation using the shared certificate, not a full external engine. Alternative arithmetic kernels require their own proof. History deletion, event-time insertion, distributed side effects, and combined certified/journal/strict execution are outside the demonstrated contract.
