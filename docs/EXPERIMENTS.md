# Current paper and experiment map

All runtime paths below resolve through `evidence/INDEX.json`; text may be gzip-compressed without changing its indexed uncompressed content hash. Current table reconstruction reads per-run/per-entity records, recomputes cells, and checks the recorded LaTeX table body. Recorded displays live in `analysis/recorded/` and `figures/recorded/`.

| Current display / claim | Primary runtime evidence | Reproduction |
| --- | --- | --- |
| Table I: reach/error tradeoff | `results/review4_20261109/rq2_records.json` | `rq2-controlled`; `tables` |
| Table II: same-statistic certificate and layout controls | `results/cert_age_slo_20261110/quality_records.json`, `FIXED_CONTROL.json`, `AUDIT.json` | `sum-age-quality`; `tables` |
| Table III: request-age prior | same `quality_records.json`, with explicit `prior` keys | `sum-age-quality`; `tables` |
| Table IV: joint recovery and corrupt-image exceptions | `results/review7_20261109/fault_records.json` | `joint-faults`; `tables` |
| Table V: native/reference/fused certificate cost | `results/review7_20261109/cost_control_records.json`, `cost_wide_records.json` | `joint-performance`; `tables` |
| Table VI: quality/p99/timely-completion feasibility | `results/cert_age_slo_20261110/load_records.json`, `TIMELY_COMPLETION.json`, `LOAD_SUMMARY.json` | `paired-load`; `tables` |
| Figure1: joint service architecture | portable diagram source `repro/framework_20261109/current.py` | `figures` |
| Figure2: paired certification / completion / p99 region | all27 `load_records.json` rows, `LOAD_SUMMARY.json` | `paired-load`; `figures` |
| Exact/live checks, 78 age-matched cases | `results/cert_age_slo_20261110/AUDIT.json`, `MATCHED_AGE.json` | `sum-age-quality`; behavioral tests |
| Earlier alignment and stronger-baseline evidence | `results/w2w3_20261110/`, `results/w1w4_20261110/` | corresponding catalog entries |

Age-matched equality, far-heavy/uniform prior results, high-load infeasibility, slower SUM kernel cases and older diagnostics are retained. The age-matched control uses the same age-priority allocation; certification and latency constraints are not combined into a tuning objective. `TIMELY_COMPLETION.json` is a per-run compact derivation from the saved request arrays; original arrays remain in the raw archive for independent inspection. Source/data-only reconstruction and fresh scientific measurement are labeled separately in run outputs.

## Protocol catalog

The JSON catalog is authoritative for commands/reference inputs. Reruns write to isolated, new output directories.

| ID | Research questions | Purpose |
| --- | --- | --- |
| `rq1-active` | RQ1 | Populated active-cell and numerical boundary checks |
| `rq2-controlled` | RQ2 | Phase-controlled reach / exactness / error grid |
| `rq2-model-ablation` | RQ1, RQ2, RQ5 | Polynomial/L2 comparison and coarse/overlay/reservation ablations |
| `rq2-fixed-width` | RQ2 | Complete prior fixed-width supplemental curves |
| `rq2-triptych-source` | RQ2 | Complete fixed-demand supplemental precision/reach grid |
| `rq3-calibration` | RQ3 | Distance/dwell calibration and held-out confirmation |
| `rq3-symmetric` | RQ3 | Independent validation layout tuning for both policies |
| `rq3-kernel` | RQ3 | Fixed-layout bandwidth and query-history sensitivity |
| `joint-quality` | RQ1, RQ2, RQ4 | Validation-frozen joint recent/histogram quality and snapshots |
| `joint-faults` | RQ4 | 216 joint process-stop/corruption/format recovery cases |
| `joint-performance` | RQ5 | 102 primary/locality cases plus36 cost-control cases |
| `joint-numerics` | RQ1, RQ5 | Supported-kernel checks, unsupported precision example and fusion equivalence |
| `native-checkpoint` | RQ5 | 54 matched million-request checkpoint component runs |
| `native-memory` | RQ5 | Nine isolated component memory diagnostics |
| `native-concurrency` | RQ5 | 120 component concurrency/query-mix conditions |
| `native-paced` | RQ5 | Paced2s grid and18 ten-second confirmations |
| `certificate-component` | RQ5 | 1008 serial certificate-kernel conditions |
| `local-replay` | RQ4 | 25 separate durable-journal process-stop checks |
| `storage-faults` | RQ4 | Standalone two-slot storage process-stop and reader tests |
| `scotty` | RQ5 | Unmodified Scotty0.4 registered-window operator |
| `duckdb` | RQ5 | DuckDB2.0.0 exact/reservoir range operators |
| `long-duration` | RQ4, RQ5 | Thirty-minute strict native bounded-telemetry component run |
| `alignment-quality` | RQ1, RQ2 | 936 validation-frozen alignment/objective controls and exact/live audit |
| `alignment-performance` | RQ5 | 180 real-data closed-loop/paced span-certificate comparisons |
| `strong-quality` | RQ1, RQ2 | Fixed/SSE/bound-targeted layouts and independent Household source |
| `household-long` | RQ4, RQ5 | Seven prolonged Household span-certificate executions |
| `sum-age-quality` | RQ1, RQ2 | 780 frozen choices,228 fixed controls,78 matched-age cases, exact/live validation |
| `paired-load` | RQ4, RQ5 | 27 Household SUM paired load points and separate span/sum kernel diagnostic |

`python reproduce.py audit-raw --output runs/raw-completion-audit` independently reconstructs T20, timely-certified fraction, G(.1), and scheduled query p99 from all27raw `requests.npz` arrays (8,019,000requests), and checks every value against the indexed records. Install the matching raw archive first. This is a recorded-array audit, not new request execution.
