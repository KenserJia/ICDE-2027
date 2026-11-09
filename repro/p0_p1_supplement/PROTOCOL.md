# P0/P1 supplemental protocol

This bundle is deliberately separate from frozen experiments E01--E09.  It
adds submission-facing confirmation without changing the core mechanism.

## P0-A: checkpoint-policy comparison

The same integrated service, deterministic operation trace, complete state
budget, client count, storage path, and mutation-count RPO are used for four
policies:

- `none`: no durability mechanism;
- `async`: background periodic checkpointing without admission blocking;
- `strict`: background periodic checkpointing with the acknowledged-gap guard;
- `sync`: the mutation that reaches the interval is acknowledged only after a
  synchronous checkpoint.

Formal runs use intervals 100/500/2000, five independent seeds, and client
counts 1/8.  The primary metrics are completed throughput, service-time
percentiles, maximum acknowledged-to-durable mutation gap, checkpoint time,
snapshot bytes, write amplification, and complete transient bytes.

## P0-B: non-stationary trace-derived queries on public observations

Bike and all twelve Beijing station series are evaluated.  Validation and test
observations are concatenated, while the query schedule is generated
independently.  The schedule has near, far, and alternating near/far phases and
uses shifted range boundaries.  It is a controlled query trace over public
observations, not a production request log.

The compared representations are exact tail, exponential-histogram-style
summary, coarse-only, fixed recent fine precision, online replaceable fine
precision, and a finite-future oracle reference.  All are charged under the
same 64 KiB history budget.  Coverage, MSE, normalized RMSE, query latency,
replacement actions, per-phase quality, and paired bootstrap intervals are
reported.

## P0-C/P1: sustained cost profile

The same service is driven continuously under `none`, `async`, and `strict`
policies at interval 500.  The run records per-second throughput, sampled
latency percentiles, RSS, state accounting, checkpoint bytes, and observed RPO.
The CLI duration is explicit; short runs must not be described as 30--60 minute
soak evidence.

## Statistical policy

Independent process-level seeds are the timing replicate.  Summaries report
medians and non-parametric bootstrap 95% intervals across seeds.  Query-quality
comparisons use the public series/entity as the paired unit.  No threshold is
used to declare scientific success.  The twelve Beijing stations are spatially
correlated, so their entity-bootstrap interval is descriptive and is not a
population-level independence claim.

