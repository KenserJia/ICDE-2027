# MT-Memory: ICDE 2027 reproducibility artifact

This **v0.3.0** package targets the current manuscript, *Bounded State Management for Mutable Facts and Historical Stream Queries with Strict Recovery Bounds*. It includes original code, three public data sources (14 entities), current and prior recorded experiments, and 28 isolated reproduction protocols. `provenance/PAPER.json` identifies the manuscript snapshot by SHA-256. The dated source/data ZIP and complete raw-evidence archive are available from the [v0.3.0 Release](https://github.com/KenserJia/ICDE-2027/releases/tag/v0.3.0).

## Quick start

Use Python 3.12 or newer. Local validation uses Python 3.14.5 on macOS/arm64 with the exact dependency pins in `requirements.txt`.

```sh
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[test,figures,sql]'
python reproduce.py verify
make test
python reproduce.py smoke --output runs/smoke
python reproduce.py prepare-data --output runs/rebuilt-data
python reproduce.py tables --output runs/tables
python reproduce.py figures --output runs/figures
python reproduce.py list
```

Run from the extracted repository root. Output destinations must be new. Integrity checks require no network. The smoke run checks certificate containment, active/wrapped restoration, and the recovery gate; it is not a throughput experiment. `tables` reconstructs all six current body tables from per-entity/per-run records and checks their displayed cells. `figures` regenerates the two current figures; font/platform differences may change pixels.

## Contents and complete evidence

| Directory | Role |
| --- | --- |
| `src/mtmemory_icde/core/` | Bounded history, certificates, service state and checkpoint mechanisms; 16 original modules |
| `src/mtmemory_artifact/` | Portable runner, data preparation, evidence loading and reconstruction |
| `repro/` | Frozen scientific experiment drivers, organized by study |
| `experiments/catalog.json` | 28 protocols with commands, explicit reference inputs and output destinations |
| `data/raw/`, `data/real/` | Three UCI source archives, processed arrays and source/transform metadata |
| `evidence/` | Indexed immutable records, protocols, text summaries and deterministic partition inputs |
| `analysis/recorded/`, `figures/recorded/` | Current paper display sources and explicitly retained older displays |
| `tests/` | Behavioral and artifact integrity tests |
| `provenance/`, `docs/`, `licenses/` | Snapshot hashes, validation scope, reuse notices and reproduction instructions |

The source/data package supports verification, preprocessing, current tables/figures and new quality runs without the large binary archive. Complete checkpoints, per-request arrays and raw binary traces are a separate Release asset: **`mt-memory-raw-evidence-20261110.tar.gz`**. It contains 7,131 files, listed with sizes and hashes in `evidence/RAW_MANIFEST.json`.

```sh
python reproduce.py install-raw --archive ../mt-memory-raw-evidence-20261110.tar.gz
python reproduce.py verify --full
python reproduce.py audit-raw --output runs/raw-completion-audit
```

Source/data ZIP and raw-evidence TAR.GZ are complementary parts of the complete artifact. Do not substitute the old dated archive for the current manifest. No login, personal webpage, tracking callback or API key is needed for the bundled evidence.

## Current controls and scope

The package retains same-statistic SPAN/SUM controls, the lightweight age-matched rollup, and quality selection separated from load/p99 feasibility. New records include 780 frozen quality choices, 228 fixed-layout controls, 78 matched-age cases, and 27 paired SUM service runs. These are controlled local workloads. The high-load infeasible points, age-matched ties, workload reversals and measured certificate costs remain available; the repository does not infer a production SLO or uniform method dominance.

Current quality and timing claims are distinguished in [the experiment map](docs/EXPERIMENTS.md). Detailed commands, dependencies, resource scope and hardware-sensitive results are in [REPRODUCIBILITY](docs/REPRODUCIBILITY.md). Prior display generators remain for historical traceability and are not relabeled as the current paper.

## Reuse and upload

Original project software/documentation is **MIT**. UCI data and data-derived records are **CC BY 4.0**; the bundled unmodified Scotty source is **Apache 2.0**. Preserve `LICENSE`, `THIRD_PARTY_NOTICES.md`, `LICENSES.json`, dataset citations and vendor notices. The MIT software license does not replace third-party terms.

See [publication details](PUBLICATION.md), the [ICDE supplemental-material audit](docs/ICDE_SUPPLEMENTAL_CHECKLIST.md), and [中文说明](README_zh.md). The preparation and manual-upload documents preserve the provenance of the local package. No artifact DOI has been assigned.
