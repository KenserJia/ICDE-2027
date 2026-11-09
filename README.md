# MT-Memory: current-paper reproducibility artifact

Repository: https://github.com/KenserJia/ICDE-2027 · Versioned release: [v0.2.0](https://github.com/KenserJia/ICDE-2027/releases/tag/v0.2.0).

[Download complete raw evidence](https://github.com/KenserJia/ICDE-2027/releases/download/v0.2.0/mt-memory-raw-evidence-20261109.tar.gz) · [中文说明](README_zh.md). The source code, processed datasets and compact records are below; large raw traces are attached to the versioned release.

This is the data/code snapshot supporting **Bounded State Management for Mutable Facts and Historical Stream Queries with Strict Recovery Bounds**. The manuscript snapshot is identified in `provenance/PAPER.json`. The package covers all five research questions, the six body tables, four body figures, and the complete recorded experiments supporting the stated claims. It does not include reviewer reports, manuscript-edit scripts, private environments, or unrelated neural-model explorations.

## Quick start

Python 3.12+ is required; the recorded environment is Python 3.14.5/macOS/arm64. A POSIX system is required for local file locking, process signals and fsync. Linux execution is supported by the code but original Linux timing measurements are not claimed.

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[test,figures,sql]'
python reproduce.py verify
python -m pytest -q tests repro/review6_20261109/test_optimized.py
python reproduce.py smoke --output runs/smoke
python reproduce.py tables --output runs/tables
python reproduce.py figures --output runs/figures
```

Use a new output directory each time. The runner refuses existing destinations and never resumes from the published records. Run timing experiments serially, without other experiments competing for the machine.

## Three reproduction levels

1. **Inspect/rebuild recorded evidence**: `verify`, `tables`, and `figures` validate the supplied files and recompute the body displays. This does not remeasure performance.
2. **Behavioral validation**: `smoke` and the tests exercise the actual service, exact-oracle certificates, active boundaries, cache invalidation, coherent images and recovery controls. A smoke run is not a full scientific run.
3. **Full scientific reruns**: `run EXPERIMENT --output DIR` executes the original protocol in an isolated workspace, with only its declared reference inputs preloaded. New selections and timings are generated from source. Deterministic quality/counts can be checked against the supplied records; throughput, interleavings, process memory and wall-clock operation counts are machine-specific.

```sh
python reproduce.py list
python reproduce.py run joint-quality --output runs/joint-quality
python reproduce.py run joint-faults --output runs/joint-faults
python reproduce.py run joint-performance --output runs/joint-performance
python reproduce.py run rq2-controlled --output runs/rq2-controlled
python reproduce.py run rq3-symmetric --output runs/rq3-symmetric
python reproduce.py run rq3-kernel --output runs/rq3-kernel
```

`experiments/catalog.json` provides every entry point, protocol command, reference input, output location and RQ. `docs/EXPERIMENTS.md` maps all entries to the paper. Full layout selection, kernel sensitivity and the 30-minute study can take substantial time; timings are not inferred from smoke checks. The Java Scotty baseline separately requires JDK/java/javac, Maven and Maven Central access. The SQL baseline uses the `sql` extra.

## Repository layout

```text
src/mtmemory_icde/core/   scientific service, certificates, summaries, checkpoints
src/mtmemory_artifact/    portable CLI, data preparation, evidence IO and checks
experiments/catalog.json runnable protocols grouped by research question
repro/                   low-level protocol drivers; historical IDs retained for traceability
data/raw/                exact UCI source archives
data/real/               exact processed/split arrays used by the paper
evidence/                indexed final entity/run records and raw-data manifest
analysis/                display regeneration and table definitions
figures/recorded/        four current body figures in editable/vector formats
docs/                    protocol guide, data dictionary, theory and upload instructions
provenance/              source identity, copy/portability audit and validation report
licenses/                dataset and third-party licenses
tests/                   scientific and artifact-contract regression tests
```

The old protocol IDs under `repro/` are implementation locations, not required user-facing execution order. Public entry points and the paper-evidence map are the navigation layer. Core scientific modules are byte-identical to the recorded final implementation; wrapper portability changes are documented in `provenance/PORTABILITY_PATCHES.json`.

## Complete raw evidence

The repository includes all final plain-text run/entity records; large text files are losslessly gzip-compressed and transparently read by the evidence loader. Per-request arrays, query truth/predictions, validation states and actual checkpoint images are supplied as a separate GitHub Release asset, **mt-memory-raw-evidence-20261109.tar.gz**. Nothing is synthesized to replace missing raw evidence. The manifest enumerates each file, size and SHA-256.

```sh
# Download the accompanying asset, then verify and import it:
python reproduce.py install-raw --archive /path/to/mt-memory-raw-evidence-20261109.tar.gz
python reproduce.py verify --full
# An actual published HTTPS asset URL can also be supplied:
python reproduce.py fetch-raw --url ACTUAL_RELEASE_ASSET_URL --download-to downloads/raw-evidence.tar.gz
```

Full reruns do not need this large archive: their reference inputs and real observations are already in the repository. The raw asset is required to inspect every original per-request binary and validate `--full`. After import these large files are ignored by Git; publish them as a Release asset rather than adding them to Git history.

## Data and licenses

Original software and associated project documentation use the **MIT License**. Reused UCI data and data-derived records retain **CC BY 4.0** with citations and transformations described in `data/README.md`. The frozen Scotty source retains **Apache 2.0**. The repository MIT license does not replace those licenses; see `THIRD_PARTY_NOTICES.md`.

## Interpretation and scope

The joint ledger reserves resident payload, extrema/facts/control metadata, two durable images, one pending image, workspace and optional cache payload. It is not an OS RAM cap. Queries are ingestion-order range means; certified history is append-only. The K loss bound requires the latest completed valid image; older corruption fallback can exceed K. Twelve Beijing stations are correlated. All wins, losses, ties and technical repeats remain in the evidence. History-only and joint-service ledgers, native-only scheduling diagnostics and joint timing are separate studies.

## GitHub publication

Follow `docs/GITHUB_UPLOAD.md`. Upload this directory as the repository content, attach the raw-evidence archive to the same versioned Release, and then replace the availability placeholder using `docs/AVAILABILITY.md`. No public URL, DOI, publication acceptance or individual author identity has been invented. See `CITATION.cff` and fill personal authors only after confirming them.
