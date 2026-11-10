# MT-Memory

Code and experimental records for *Bounded State Management for Mutable Facts and Historical Stream Queries with Strict Recovery Bounds*.

## Install and check

Use Python 3.12 or newer. Run these commands from the repository root:

```sh
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[test,figures,sql]'
python reproduce.py verify
make test
python reproduce.py smoke --output runs/smoke
python reproduce.py tables --output runs/tables
python reproduce.py figures --output runs/figures
```

Output directories must be new. `tables` and `figures` rebuild the six tables and two figures from recorded results. They do not repeat the performance measurements. To rebuild the processed data from the bundled UCI source archives, run `python reproduce.py prepare-data --output runs/data`.

## Run experiments

`python reproduce.py list` lists 28 experiments. Each has a descriptive identifier and a fixed set of reference inputs. For example:

```sh
python reproduce.py run sum-age-quality --output runs/quality
python reproduce.py run paired-load --output runs/load
```

See [the experiment map](docs/EXPERIMENTS.md) for the correspondence between experiments and paper claims, and [the reproduction guide](docs/REPRODUCIBILITY.md) for dependencies, runtimes and measurement scope.

## Download the evidence

The [v0.3.1 release](https://github.com/KenserJia/ICDE-2027/releases/tag/v0.3.1) provides the source/data ZIP. Complete binary evidence is the unchanged [raw archive from v0.3.0](https://github.com/KenserJia/ICDE-2027/releases/download/v0.3.0/mt-memory-raw-evidence-20261110.tar.gz). Use both for full inspection. The source ZIP alone contains the data and records needed for the quick checks and display reconstruction.

```sh
python reproduce.py install-raw --archive ../mt-memory-raw-evidence-20261110.tar.gz
python reproduce.py verify --full
python reproduce.py audit-raw --output runs/request-audit
```

The raw archive contains 7,131 files. Its checksum and member inventory are in `evidence/RAW_MANIFEST.json`. The per-request audit recomputes certification, completion within 20 ms and scheduled query p99 across 27 runs and 8,019,000 requests.

## Repository layout

| Location | Contents |
| --- | --- |
| `src/mtmemory_icde/core/` | Scientific implementation |
| `src/mtmemory_artifact/` | Command line, isolated execution, integrity checks, data preparation and analysis |
| `experiments/catalog.json` | Experiment identifiers, commands and reference inputs |
| `repro/` | Original experiment drivers, retained at their recorded paths |
| `data/` | Three UCI source archives, processed arrays and attribution |
| `evidence/` | Results index and compact records |
| `analysis/recorded/`, `figures/recorded/` | Table and figure sources |
| `tests/` | Service and artifact tests |
| `provenance/` | Source hashes, environment and validation records |

The original driver paths are retained because the experiment protocols record their hashes and some drivers import one another. Use the named experiments instead of invoking those files directly. Each run receives a separate workspace.

The records include same-statistic certificate controls, matched-age ties, workload reversals and infeasible high-load points. They remain part of the evidence.

## Licenses and attribution

Original software and documentation are MIT-licensed. UCI data and derived records use CC BY 4.0; the bundled Scotty source retains Apache 2.0. See [data attribution](data/README.md), `LICENSE`, `LICENSES.json` and `THIRD_PARTY_NOTICES.md`.

AI assistance is described in [ACKNOWLEDGMENTS.md](ACKNOWLEDGMENTS.md). Release changes are listed in [CHANGELOG.md](CHANGELOG.md). [中文快速说明](README_zh.md).
