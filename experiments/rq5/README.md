# RQ5

- `rq2-model-ablation`: Polynomial/L2 comparison and coarse/overlay/reservation ablations. Run from the repository root with `python reproduce.py run rq2-model-ablation --output runs/rq2-model-ablation`.
- `joint-performance`: 102 primary/locality cases plus36 cost-control cases. Run from the repository root with `python reproduce.py run joint-performance --output runs/joint-performance`.
- `joint-numerics`: Supported-kernel checks, unsupported precision example and fusion equivalence. Run from the repository root with `python reproduce.py run joint-numerics --output runs/joint-numerics`.
- `native-checkpoint`: 54 matched million-request checkpoint component runs. Run from the repository root with `python reproduce.py run native-checkpoint --output runs/native-checkpoint`.
- `native-memory`: Nine isolated component memory diagnostics. Run from the repository root with `python reproduce.py run native-memory --output runs/native-memory`.
- `native-concurrency`: 120 component concurrency/query-mix conditions. Run from the repository root with `python reproduce.py run native-concurrency --output runs/native-concurrency`.
- `native-paced`: Paced2s grid and18 ten-second confirmations. Run from the repository root with `python reproduce.py run native-paced --output runs/native-paced`.
- `certificate-component`: 1008 serial certificate-kernel conditions. Run from the repository root with `python reproduce.py run certificate-component --output runs/certificate-component`.
- `scotty`: Unmodified Scotty0.4 registered-window operator. Run from the repository root with `python reproduce.py run scotty --output runs/scotty`.
- `duckdb`: DuckDB2.0.0 exact/reservoir range operators. Run from the repository root with `python reproduce.py run duckdb --output runs/duckdb`.
- `long-duration`: Thirty-minute strict native bounded-telemetry component run. Run from the repository root with `python reproduce.py run long-duration --output runs/long-duration`.
