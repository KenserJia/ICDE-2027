# Reproduction guide

## Environment and validation levels

The tested local environment is macOS/arm64, Python 3.14.5, with the exact Python dependency pins in `requirements.txt`. Python >=3.12 is the declared minimum. Linux and other Python versions are CI targets, not locally demonstrated performance platforms. A working JDK/Maven and network access to Maven Central are needed only for the optional external Scotty study; DuckDB needs the `sql` extra. The core/data/evidence checks are offline after installation. No GPU is required by the bundled current-manuscript code.

Reserve several GB of disk: the source tree, 1.12 GiB raw archive, approximately 1.19 GiB expanded raw evidence, and a separate output workspace for each run. The 90-minute Household series and prior long-duration grids need additional output space. Absolute performance and p99 are hardware/filesystem/load dependent. Use a local filesystem supporting the atomic-replace/fsync operations in the original protocol; process-stop tests are not evidence for arbitrary hardware power loss.

There are three separate validation levels:

1. `verify`, tests, `smoke`, and `prepare-data`: package integrity, behavioral correctness, and exact data reconstruction.
2. `tables` and `figures`: reconstruct current displays from the recorded observations. This does not remeasure performance.
3. `run EXPERIMENT`: execute a fresh scientific protocol in a new workspace. Quality/counts can be compared deterministically where applicable; timing must be remeasured and interpreted in the new environment.

## Commands

Follow installation in the root README, then:

```sh
make test
python reproduce.py verify
python reproduce.py smoke --output runs/smoke
python reproduce.py prepare-data --output runs/rebuilt-data
python reproduce.py tables --output runs/tables
python reproduce.py figures --output runs/figures
python reproduce.py list
python reproduce.py run sum-age-quality --output runs/new-quality
python reproduce.py run paired-load --output runs/new-paired-load
```

Use a new output path for every invocation. Do not invoke frozen drivers directly inside the repository: they were written for a working experiment tree. The runner copies code/data into an isolated output workspace, materializes only declared reference inputs, and writes logs and `RUN.json`. Deterministic block-local partition caches are declared comparison inputs; their reuse is explicit, and they are bundled in source/data so raw evidence installation is unnecessary for quality reruns. No recorded timings, old pilot, completed checkpoints or result destinations are used to resume a new paired-load run. The validation-quality selections are frozen before timing; the timing pilot is newly calibrated on the rerun host.

The paired-load protocol uses 27 measured 60-second runs plus setup, pilot and drain. The separate Household prolonged series includes six 10-minute runs and one 30-minute run; allow at least 90 minutes plus setup/drain. The full optional prior grids are more expensive; protocol source constants and catalog notes are authoritative. Run all performance studies sequentially on an otherwise idle machine. No new timing estimates were inferred by replaying stored records.

## Complete raw inspection

```sh
python reproduce.py install-raw --archive ../mt-memory-raw-evidence-20261110.tar.gz
python reproduce.py verify --full
python reproduce.py audit-raw --output runs/raw-completion-audit
```

Installation checks archive SHA-256, exact member inventory, safe relative regular-file paths and individual file hashes. It refuses conflicting existing content. `verify` allows absent separately distributed raw files; `verify --full` requires all 7,131. `evidence/INDEX.json` maps original runtime paths to transport locations and gives the original content hash; `RAW_MANIFEST.json` lists binary Release members. Compressed text transparently loads through `mtmemory_artifact.io`.

## Current interpretation boundaries

SUM improves a valid certificate using already stored statistics; the fixed-layout comparison isolates the certificate change. Recent versus age-matched rollup can tie when they retain the same information. Certification rate, completion within20ms, and overall query p99 are reported separately at shared offered loads. The top load violates the p99 threshold in every recorded replicate; it must remain infeasible in rebuilt displays. Age-prior reversals, certificate costs, legacy diagnostics, checkpoint-corruption exceptions and unsupported numerical cases remain in the evidence. These studies do not establish a universal best policy, a hard process RAM cap, a distributed recovery theorem or a production latency guarantee.

`provenance/VALIDATION.json` states exactly what was executed during this packaging revision. Historical validations are retained under `provenance/history/v0.2.0/` with their original date and scope.
