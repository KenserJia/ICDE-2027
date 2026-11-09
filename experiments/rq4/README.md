# RQ4

- `joint-quality`: Validation-frozen joint recent/histogram quality and snapshots. Run from the repository root with `python reproduce.py run joint-quality --output runs/joint-quality`.
- `joint-faults`: 216 joint process-stop/corruption/format recovery cases. Run from the repository root with `python reproduce.py run joint-faults --output runs/joint-faults`.
- `local-replay`: 25 separate durable-journal process-stop checks. Run from the repository root with `python reproduce.py run local-replay --output runs/local-replay`.
- `storage-faults`: Standalone two-slot storage process-stop and reader tests. Run from the repository root with `python reproduce.py run storage-faults --output runs/storage-faults`.
- `long-duration`: Thirty-minute strict native bounded-telemetry component run. Run from the repository root with `python reproduce.py run long-duration --output runs/long-duration`.
