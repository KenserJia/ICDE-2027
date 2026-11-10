# Resource-limited W1/W4 follow-up

Scope explicitly authorized: W1 items1-3 (contribution, stronger baselines,
transferable configuration rule), W4 items1-4 (new source, independent tuning versus
frozen transfer, application queries, prolonged/burst execution). No general online
allocation algorithm or arbitrary channel/keyspace expansion is introduced.

The original production modules are unchanged. strong_baselines.py adds two
comparators through ComparisonService, reusing the exact query bound, facts,
checkpoint image format, RPO coordinator and resource accounting. Fixed bins
retain full-block coarse sums and uniform fine bins across reach. Bound bins run
block DP on the width-prior weighted mean-channel analytical range-bound sum.
The prior widths are frozen from the original request specification. This DP does
not optimize G(epsilon); no global accuracy/latency optimum is claimed.

BoundWorkspace reuses its inherited prefix/diff arrays as min/max scratch.
Its coefficient vector and full DP/backpointer arrays are charged. The initial
larger-workspace diagnostic and interrupted first run are preserved separately;
all final selections and timings follow the workspace reuse. Mathematical cuts
are unchanged, so the derived partition cache is reused. Scientific final records
are only under results/w1w4_20261110.

Quality uses all original13 entities plus the independent Household source,
two budget/reach cases128KiB/4096 and256KiB/16384, reduced feasible grids b128/256,
f8/16,k0/4/8/16,q1/2/4. Both MSE/G(.1) selections remain. A linear geometry rule
uses original-domain validation G labels and training roughness plus declared
query geometry, with coefficients frozen before Household validation/testing.
Household training statistics are permitted inputs, but its validation outcomes
do not fit the rule. The rule does not distinguish partition algorithms having
identical geometry. All228 selections precede test evaluation. Three query seeds
supply4608 requests per selection; exact rational samples and independent live
application tests audit reconstruction. No population CI over correlated sites.

Household UCI235 was downloaded from its official source, archive checked, SHA256
recorded. Full chronological60/20/20 split, causal forward-fill, training-only
channel normalization. Channels: active/reactive power,voltage,intensity. Actual
minutes are not dropped. Certified targets are these imputed stored observations,
not unknowable missing sensor readings. Facts are controlled synthetic updates.

Application examples use widths60/1440/10080minutes at3prespecified test prefixes,
with current and lagged windows. Report kW bound with input normalization/cast
conversion allowance. Thresholds .05/.1/.2kW are sensitivity settings, not a real
production SLO. Examples are functional checks rather than a year-wide query trace.

Long runs fix Household,256KiB/R16384,Recent and the highest HOUSEHOLD VALIDATION
G(.1) non-Recent comparator. A disjoint validation-data pilot fixes shared base/
burst rates, capped to avoid cycling test observations. Eight clients, strict
K500,95%queries/4%real observations/1%controlled fact mutations. Six10min matched
runs(3per method) plus one30min representative run execute serially, with two10s
bursts each. Scheduled latency includes queueing/backlog and all arrivals drain.
Per-minute outcomes, full-run latencies, checkpoint state/gap, RSS and prefix-
specific exact audits are retained. Telemetry and preallocated finite-run trace
buffers lie outside the logical payload ledger and inside measured process RSS.
No other scientific experiment runs concurrently with timing. Four-second and
longer studies are separate measurements; technical repeats do not create datasets.

## Interpretation boundaries

The fixed baseline has uniform fine bins and full-block coarse sums. It is a
restricted two-level comparator, not an optimized age-dependent hierarchy.
The bound DP uses the original eight widths16/17/31/32/63/64/127/128 as a fixed
uniform prior. Test widths are uniformly sampled integers16..128; this prior
mismatch is retained. Its objective is additive mean-channel analytical bound,
whereas reported G uses RMS total channel bounds and a tolerance crossing.
Neither prior weighting nor the objective is a universal certification optimum.

The rule is a four-feature least-squares ranking fitted to598 original-source
validation candidate outcomes across13 units. It is not a calibrated probability,
an online learner, or a causal explanation of the coefficient signs. Household
training roughness is an input; Household validation outcomes do not fit the
coefficients. The test is one held-out source under the declared query geometry,
not leave-one-domain cross-validation or unseen-query-distribution robustness.
The independent source retains equal near/middle/far age-panel weights from the
original request specification. It is data-source transfer under the declared
request prior; ages are not uniformly distributed over the entire reach.

Each primary prolonged run is600seconds,8000base and40000burst requests/s,
with bursts at120--130 and420--430seconds. Recent uses(256,8,8); validation
selection chooses SSE(256,q4) as the non-Recent comparator. The thirty-minute
Recent run uses4000base/20000burst at600--610 and1200--1210seconds. It is a
separate descriptive observation, not a seventh member of the primary comparison.

Timely certified-query goodput counts individual queries meeting both normalized
error tolerance0.1 and scheduled completion20ms, divided by elapsed time. It does
not imply whole-workload p99<=20ms. Report both; retain burst queueing losses.
Maximum RPO gap comes from the coordinator's synchronized maximum-gap field,
not potentially non-atomic telemetry snapshots. Full request arrays and1second
RSS/backlog samples are retained. Sampled backlog/RSS can miss instantaneous
peaks. Finite-run measurement arrays are outside the ledger and inside process
RSS; neither prolonged execution nor its RSS demonstrates a physical RAM cap.

Long checkpoints retain counts, observed maximum gap, final drain, and restored
arrays. Their transient individual cost records are not a full long-run trace.
A separate three-by100000request per-method diagnostic records checkpoint
capture/persist/total costs after the prolonged experiment and is labeled
separately. Do not pool its checkpoint percentiles with prolonged timings.

## Reproduction

Run from the project root with its dependencies installed and PYTHONPATH=src.
Scripts depend on the accompanying prior W2/W3 quality implementation and
review7 exact oracle. New entry points are prepare_data.py, quality.py,
application.py, longrun.py, checkpoint_diagnostic.py, analyze.py, and
revise_paper.py in this directory, in that order. Longrun deliberately executes
serially and takes90minutes plus setup/audits. Run no other scientific timing
experiment concurrently. Scripts reuse frozen output files; reproduce in a
fresh results directory or a fresh project copy, preserving the supplied records.
Do not delete supplied results to reproduce in place.

Household attribution: G. Hebrail and A. Berard, Individual Household Electric
Power Consumption, UCI Machine Learning Repository,2006, doi:10.24432/C58K54,
CC BY4.0. The accompanying DATA.json identifies source, preprocessing, and
raw-archive SHA256. Derived household.npz and the official complete archive
are included. An incomplete download and the superseded workspace diagnostic
are excluded from the final revision package.
