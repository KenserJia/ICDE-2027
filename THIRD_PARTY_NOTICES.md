# License boundaries

## Project code and documentation: MIT

The root `LICENSE` applies to original MT-Memory software, experiment/analysis wrappers, tests and associated project documentation. Copyright wording is preserved as 2026 MT-Memory contributors; no personal authorship is invented.

## UCI observations and derived data: CC BY 4.0

`data/raw`, `data/real`, recorded query truth/predictions and data-derived evidence reuse the Bike Sharing and Beijing Multi-Site Air Quality datasets. These are distributed with attribution under CC BY 4.0, independently of the software license. `data/README.md` gives creators, DOIs, URLs, selected variables and modifications. `licenses/CC-BY-4.0.txt` preserves the terms. Project-generated experimental records are shared under CC BY 4.0 so the evidence archive has a consistent attribution route; no exclusive ownership over underlying third-party facts is claimed.

## Scotty: Apache 2.0

The unmodified archive `repro/round73_74/scotty-master.zip` (duplicated as a descriptive third-party asset) comes from TU-Berlin-DIMA/scotty-window-processor, commit b89b7fc2e2b0813ba0f56834c8f9bc9bfceee189, component version 0.4. The original archive and its copyright notices remain intact; `licenses/Apache-2.0.txt` preserves its license. See `third_party/scotty/PROVENANCE.json`. The project adapter is original MIT code. Compile-only local stubs are supplied for historical diagnostic inspection; the official reproduction uses Maven and real dependencies, not those stubs.

NumPy, psutil, DuckDB, Matplotlib, Pillow, pytest and Maven/Java are installed dependencies, not relicensed or bundled implementations. Their own terms continue to apply. Unrelated M1/neural vendor code and adapter weights are not required by the current manuscript and are not included. No reviewer reports, private environments or credentials are shipped.
