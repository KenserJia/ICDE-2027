# Evidence dictionary

`evidence/INDEX.json` is the complete scientific record inventory. Each row contains the original runtime-relative filename, public stored filename, uncompressed SHA-256, uncompressed byte count and transport (`plain`, `gzip`, or `raw-release`). Gzip records are lossless; `mtmemory_artifact.io` transparently decodes them. `RAW_MANIFEST.json` identifies every binary Release member and the archive checksum. `MANIFEST.json` seals the repository files; it excludes itself and generated outputs/caches.

`PAPER_MAP.json` links each body display to exact record files and rerun IDs. Follow `experiments/catalog.json` for commands, isolated runtime output prefixes and required older reference inputs. Low-level filenames preserve original protocol identities. They do not imply that every historical diagnostic is a current body result.

## Record families

- `quality_test.json`: one record per dataset/entity, joint budget B (bytes), reach R (observations), and summary family. `id`/`config` layout metadata identify the validation choice. Metrics split query panels; NRMSE uses training variance, exact fraction is structural exactness, and normalized bounds are certificate widths in the same scale. `checks` and `violations` count exact-oracle comparisons. All 104 choices and 479232 checks are preserved.
- RQ2 `rq2_records.json`: full candidate, entity, seed, width/age/phase panel records; `selected` is validation-frozen. B uses bytes, R/width/delay use observation steps. Nested metric keys are defined by the original driver. Use the same panel key when comparing reach; the main fixed near-panel display uses the registered plotting driver.
- RQ3 selection and sensitivity records: dataset/entity/workload, policy, layout and held-out error; candidate tables retain unselected candidates. A pair is one entity under the same schedule. Technical seeds and correlated stations are not independent population samples.
- `performance_records.json`, `cost_control_records.json`, `cost_wide_records.json`: one row per method/mode/client/query-mix/repeat. Throughput is requests/s; timing fields named `_ms`, `_us`, `_ns` retain those units, and `_s` uses seconds. Latency percentile fields follow the driver-defined unit. Logical charge and whole-process memory are separate. Read each corresponding driver for exact instrumentation; never infer a unit solely from a CSV display label.
- `fault_records.json`: fault mode, variant, K, prefixes, loss and reconstruction checks, or an explicit failure result. `bound_claimed` identifies cases to which the K statement applies. Offset-stop mode `random` in the original file actually uses frozen targets K+7/K+10/K+13. Corrupt-newest fallback is outside that latest-image bound.
- `.npz`: either processed observation arrays or original per-query/request/validation traces. NumPy keys and shapes are retained unchanged; use `numpy.load(..., allow_pickle=False)` and the corresponding driver. `.chk` and `.pending` are intentionally retained real image bytes, including deliberate malformed/corrupt examples. Load them only through the supplied checked codec/fault harness.

## Scope of integrity checks

Metadata-only personal path redactions are logged in `provenance/METADATA_REDACTIONS.json`; scientific numerical observations are unchanged. Original core hashes are in `provenance/CORE_SHA256.json`. `COPY_MAP.json` separates original source hashes, transport changes, documented wrapper adaptations and files absent because they are non-scientific administration. `EXCLUDED_NONPRIMARY.json` lists omitted duplicate/administrative/visual files, not omitted final scientific outcomes.

##2026-11-10 extension

The index now includes the three additional study namespaces `w2w3_20261110`, `w1w4_20261110`, and `cert_age_slo_20261110`. Deterministic `.npz` partition inputs in `/cache/` or `/partition_cache/` are source/data members with plain transport; all remaining large binary records are raw-release members. `RAW_MANIFEST.json` now names the20261110 archive. Historical v0.2.0 validation is explicitly archived under `provenance/history/v0.2.0/`; its counts must not be used as validation of this new revision.

`docs/numerical_derivation.tex` is the retained2026-11-09technical note for the earlier joint certificate/checkpoint kernels. Its date and equations are preserved; it is not a current manuscript appendix or an additional current table map. SUM/age extensions are identified by the frozen current core/driver hashes and current manuscript.
