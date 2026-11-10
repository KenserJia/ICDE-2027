# Alignment, selection objective, and joint useful-query throughput

This follow-up addresses W2 and W3. The original service implementation is frozen
and unchanged. Both families use the same extrema certificate, facts, image codec,
RPO coordinator and logical payload accounting. The comparator remains a bounded
time-block V-optimal adaptation, not the upstream implementation of a complete DBMS.

## W2

Use all 13 existing entities, chronological training/validation/test splits,
128/256 KiB, reaches 4096/16384, and the original feasible layout grids. Compare:

* `mixed`: the original half 16-aligned, half irregular query distribution;
* `random_phase`: the same two width lists, with unconstrained random starts;
* `random_uniform`: independent uniform integer widths 16..128 and random starts.

Each schedule balances 256 ingestion phases and equal near/middle/far panels.
For each distribution and family select layouts independently on validation by
MSE, G(0.1), or mean normalized total bound. Ties use charged bytes then layout ID.
Freeze all 936 choices before any follow-up test evaluation. Evaluate three query
seeds (4608 queries per choice), retain U/G at .01/.05/.1/.2, and separately report
the aligned and irregular strata. These are new controls on the existing holdout,
not new independent datasets. Training variance is the only normalizer.

The vectorized disjoint-cell implementation evaluates the same outward equations
without using its timing as a service-speed measurement. Every unique selected
prediction/bound is checked by the independent integer-prefix float32 oracle.
Check sampled reconstruction results against the live service separately. Quality
tables use entity macro means; no independent-station population CI is claimed.

## W3

Fix Bike and Beijing station 0 in advance. Use the 128 KiB/4096 and
256 KiB/16384 cases, random-uniform query distribution, and validation-MSE and
validation-G(0.1) selections. Deduplicate identical configurations without deleting
the objectives they represent. No test result removes a selected configuration.

Use eight clients, 95% history queries, 4% real test observations, and 1% fact
mutations. Test observations never cycle. Prepare training+validation images
before timing and use identical request-generation seeds across implementations.
Both sync and strict use K=500. Thread interleavings are uncontrolled and raw logs
support prefix-specific exact-oracle checks. The fact catalog is 256 keys.

Each configuration/policy has three 30000-request closed-loop runs. G-selected
configurations additionally have three paced runs at each of 5000 and 20000 total
requests/s for four seconds. Paced timestamps are fixed before request execution;
scheduled-to-completion latency includes waiting and accumulated backlog. All
issued requests drain. Count useful queries only when normalized total bound is
<=.1. Report useful completions/actual elapsed time and useful completions within
5/20 ms scheduled-to-completion deadlines. The final forced checkpoint drain is
timed separately. The ledger is not a physical RAM cap.

Timing subprocesses run serially. Preserve all runs, raw per-request arrays,
full repeat ranges, negative results, state roundtrips and observed RPO gaps.
No other scientific experiment is run concurrently with these timings.

## Entry points

Run from the revision root with the original project's Python environment:

```
python repro/w2w3_20261110/quality.py
python repro/w2w3_20261110/performance.py
python repro/w2w3_20261110/validate.py
python repro/w2w3_20261110/analyze.py
```

Frozen source and candidate manifests precede measurements. Existing complete
cases can be inspected or resumed; for an independent repeat copy source/data
into a new revision root with an empty results directory.
