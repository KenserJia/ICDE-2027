# Experiments and paper evidence

| Entry | RQs | Purpose |
|---|---|---|
| rq1-active | RQ1 | Populated active-cell and numerical boundary checks |
| rq2-controlled | RQ2 | Phase-controlled reach / exactness / error grid |
| rq2-model-ablation | RQ1,RQ2,RQ5 | Polynomial/L2 comparison and coarse/overlay/reservation ablations |
| rq2-fixed-width | RQ2 | Complete prior fixed-width supplemental curves |
| rq2-triptych-source | RQ2 | Complete fixed-demand supplemental precision/reach grid |
| rq3-calibration | RQ3 | Distance/dwell calibration and held-out confirmation |
| rq3-symmetric | RQ3 | Independent validation layout tuning for both policies |
| rq3-kernel | RQ3 | Fixed-layout bandwidth and query-history sensitivity |
| joint-quality | RQ1,RQ2,RQ4 | Validation-frozen joint recent/histogram quality and snapshots |
| joint-faults | RQ4 | 216 joint process-stop/corruption/format recovery cases |
| joint-performance | RQ5 | 102 primary/locality cases plus 36 cost-control cases |
| joint-numerics | RQ1,RQ5 | Supported-kernel checks, unsupported precision example and fusion equivalence |
| native-checkpoint | RQ5 | 54 matched million-request checkpoint component runs |
| native-memory | RQ5 | Nine isolated component memory diagnostics |
| native-concurrency | RQ5 | 120 component concurrency/query-mix conditions |
| native-paced | RQ5 | Paced 2s grid and 18 ten-second confirmations |
| certificate-component | RQ5 | 1008 serial certificate-kernel conditions |
| local-replay | RQ4 | 25 separate durable-journal process-stop checks |
| storage-faults | RQ4 | Standalone two-slot storage process-stop and reader tests |
| scotty | RQ5 | Unmodified Scotty 0.4 registered-window operator |
| duckdb | RQ5 | DuckDB 2.0.0 exact/reservoir range operators |
| long-duration | RQ4,RQ5 | Thirty-minute strict native bounded-telemetry component run |

All commands: `python reproduce.py run ENTRY --output runs/NEW_DIRECTORY`. Detailed commands and declared input dependencies are machine-readable in `experiments/catalog.json`. Timing entries must run serially. The long-duration entry takes 1800s by design; full selection and sensitivity grids are larger than the smoke profile.

The runtime drivers retain dated IDs to connect each output to its original protocol. Manuscript integration, reference collection, private backup and one-time source patch scripts are not distributed. Complete positive/negative/tied final rows are retained; only non-primary duplicate diagnostics and administrative/visual records are excluded. `provenance/EXCLUDED_NONPRIMARY.json` records that rule.
