from __future__ import annotations

import argparse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import resource
import statistics
import sys
import tempfile
import threading
import time

import numpy as np
import psutil


ROOT = Path(os.environ.get("MTMEM_ICDE_ROOT", Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(ROOT / "src"))

from mtmemory_icde.core.baselines import EHSum, ExactTail  # noqa: E402
from mtmemory_icde.core.checkpoint import TwoSlotStore  # noqa: E402
from mtmemory_icde.core.history import Config, TieredOverlayStore  # noqa: E402
from mtmemory_icde.core.rpo import CheckpointCoordinator  # noqa: E402
from mtmemory_icde.core.service import IntegratedService  # noqa: E402


def pct(values, q):
    if not values:
        return None
    return float(np.percentile(np.asarray(values, np.float64), q))


def distribution(values):
    return {"count": len(values), "p50": pct(values, 50), "p95": pct(values, 95),
            "p99": pct(values, 99), "p99_9": pct(values, 99.9),
            "maximum": max(values) if values else None}


def bootstrap_ci(values, statistic=np.median, seed=20261102, repetitions=10000):
    x = np.asarray(values, np.float64)
    if not len(x):
        return None
    if len(x) == 1:
        value = float(statistic(x))
        return [value, value]
    rng = np.random.default_rng(seed)
    draws = rng.choice(x, size=(repetitions, len(x)), replace=True)
    stats = np.apply_along_axis(statistic, 1, draws)
    return [float(np.percentile(stats, 2.5)), float(np.percentile(stats, 97.5))]


def row_for(index):
    x = float(index)
    return np.asarray([np.sin(x / 17), np.cos(x / 29), (index % 97) / 97,
                       np.sin(x / 71) + np.cos(x / 11)], np.float32)


class NullCoordinator:
    durable_seq = 0
    maximum_gap = None
    records = ()
    wait_records_ms = ()
    checkpoint_count_total = 0
    checkpoint_envelope_bytes_total = 0
    initial_checkpoint_envelope_bytes = 0

    def __init__(self, service):
        self.service = service

    def mutate(self, fn):
        return fn()

    def close(self, force=True):
        return None


class SynchronousCoordinator:
    """Checkpoint on the mutation that reaches the declared interval."""

    def __init__(self, service, store, interval):
        self.service = service
        self.store = store
        self.interval = int(interval)
        self.lock = threading.RLock()
        self.records = []
        self.wait_records_ms = []
        self.checkpoint_count_total = 0
        self.checkpoint_envelope_bytes_total = 0
        self.initial_checkpoint_envelope_bytes = 0
        initial = self.store.commit(service.dumps())
        self.durable_seq = int(service.ack_seq)
        self.maximum_gap = 0
        self.records.append({**initial, "snapshot_ack_seq": self.durable_seq,
                             "total_ms": 0.0, "initial": True})
        self.checkpoint_count_total += 1
        self.checkpoint_envelope_bytes_total += int(initial["envelope_bytes"])
        self.initial_checkpoint_envelope_bytes = int(initial["envelope_bytes"])

    def mutate(self, fn):
        with self.lock:
            result = fn()
            gap = int(self.service.ack_seq) - self.durable_seq
            if gap >= self.interval:
                started = time.perf_counter_ns()
                payload = self.service.dumps()
                record = self.store.commit(payload)
                elapsed = (time.perf_counter_ns() - started) / 1e6
                self.durable_seq = int(self.service.ack_seq)
                self.records.append({**record, "snapshot_ack_seq": self.durable_seq,
                                     "total_ms": elapsed, "initial": False})
                self.checkpoint_count_total += 1
                self.checkpoint_envelope_bytes_total += int(record["envelope_bytes"])
                gap = int(self.service.ack_seq) - self.durable_seq
                self.wait_records_ms.append(elapsed)
            self.maximum_gap = max(self.maximum_gap, gap)
            return result

    def close(self, force=True):
        if force and int(self.service.ack_seq) != self.durable_seq:
            with self.lock:
                started = time.perf_counter_ns()
                payload = self.service.dumps()
                record = self.store.commit(payload)
                elapsed = (time.perf_counter_ns() - started) / 1e6
                self.durable_seq = int(self.service.ack_seq)
                self.records.append({**record, "snapshot_ack_seq": self.durable_seq,
                                     "total_ms": elapsed, "initial": False, "forced": True})
                self.checkpoint_count_total += 1
                self.checkpoint_envelope_bytes_total += int(record["envelope_bytes"])


def make_operations(seed, count):
    rng = np.random.default_rng(seed)
    operations = []
    for index in range(count):
        u = rng.random()
        if u < .55:
            operations.append(("observe", index, 0))
        elif u < .82:
            phase = index * 3 // count
            delays = ([7, 71, 135], [1031, 1543, 2055], [39, 263, 775, 1543])[phase]
            operations.append(("query", int(rng.choice(delays)),
                               int(rng.choice([32, 64, 128, 256]))))
        elif u < .94:
            operations.append(("put", int(rng.integers(0, 256)), index))
        elif u < .97:
            operations.append(("delete", int(rng.integers(0, 256)), index))
        elif u < .99:
            operations.append(("get", int(rng.integers(0, 256)), 0))
        else:
            operations.append(("control", 0, 0))
    return operations


def coordinator_for(policy, service, store, interval):
    if policy == "none":
        return NullCoordinator(service)
    if policy == "async":
        return CheckpointCoordinator(service, store, interval, strict=False)
    if policy == "strict":
        return CheckpointCoordinator(service, store, interval, strict=True)
    if policy == "sync":
        return SynchronousCoordinator(service, store, interval)
    raise ValueError(policy)


def close_coordinator(coordinator, force=True, timeout=180):
    """Close a coordinator without changing its checkpoint policy.

    The artifact core uses a 30 second administrative timeout.  Formal async
    saturation can leave the background writer catching up for longer than
    that even though it remains live.  The supplemental harness therefore uses
    a longer *shutdown-only* timeout and records no observations after the load
    has ended.
    """
    if not isinstance(coordinator, CheckpointCoordinator):
        coordinator.close(force=force)
        return
    if coordinator.interval <= 0:
        return
    if force:
        with coordinator._cv:
            target = int(coordinator.service.ack_seq)
            coordinator._force = True
            coordinator._cv.notify_all()
            coordinator._cv.wait_for(lambda: coordinator.durable_seq >= target, timeout=timeout)
            if coordinator.durable_seq < target:
                raise TimeoutError(f"supplemental shutdown did not reach {target}; durable={coordinator.durable_seq}")
    with coordinator._cv:
        coordinator._stop = True
        coordinator._cv.notify_all()
    coordinator.thread.join(timeout=timeout)
    if coordinator.thread.is_alive():
        raise TimeoutError("supplemental checkpoint thread did not stop")


def run_checkpoint_case(root, policy, interval, seed, clients, operations):
    case = root / f"{policy}-i{interval}-s{seed}-c{clients}"
    case.mkdir(parents=True, exist_ok=False)
    service = IntegratedService()
    service.initialize_facts(128)
    for index in range(2432):
        service.observe(row_for(index - 2432), count_ack=False)
    store = None if policy == "none" else TwoSlotStore(case / "checkpoint")
    coordinator = coordinator_for(policy, service, store, interval)
    trace = make_operations(seed, operations)
    shards = [trace[index::clients] for index in range(clients)]
    barrier = threading.Barrier(clients)
    errors = []
    latency = []
    latency_lock = threading.Lock()
    cpu_start = time.process_time()

    def execute(shard, worker):
        local = []
        try:
            barrier.wait(timeout=30)
            for local_index, (kind, a, b) in enumerate(shard):
                started = time.perf_counter_ns()
                if kind == "observe":
                    coordinator.mutate(lambda a=a, worker=worker, local_index=local_index:
                                       service.observe(row_for(a + worker * 100003 + local_index)))
                elif kind == "put":
                    value = np.asarray([a, b, -b, a+b], np.float32) / 10000
                    coordinator.mutate(lambda a=a, value=value: service.put_fact(a, value))
                elif kind == "delete":
                    coordinator.mutate(lambda a=a: service.put_fact(a, np.zeros(4, np.float32), delete=True))
                elif kind == "get":
                    service.get_fact(a)
                elif kind == "control":
                    service.controller_tick()
                else:
                    answer = service.query(worker % 256, a, b)["history"]
                    if answer["value"] is not None and not np.isfinite(answer["value"]).all():
                        raise FloatingPointError("non-finite history answer")
                local.append((time.perf_counter_ns() - started) / 1e6)
        except Exception as exc:  # retained in result rather than hiding worker failures
            errors.append(repr(exc))
        with latency_lock:
            latency.extend(local)

    wall_start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=clients) as pool:
        futures = [pool.submit(execute, shard, worker) for worker, shard in enumerate(shards)]
        for future in futures:
            future.result()
    close_coordinator(coordinator, force=True)
    wall_seconds = time.perf_counter() - wall_start
    cpu_seconds = time.process_time() - cpu_start
    snapshot = service.dumps()
    account = service.account(len(snapshot))
    checkpoint_records = [r for r in coordinator.records if not r.get("initial")]
    checkpoint_times = [float(r["total_ms"]) for r in checkpoint_records if "total_ms" in r]
    initial_bytes = int(coordinator.initial_checkpoint_envelope_bytes)
    envelope_bytes = int(coordinator.checkpoint_envelope_bytes_total) - initial_bytes
    checkpoint_count = int(coordinator.checkpoint_count_total) - (1 if policy != "none" else 0)
    acknowledged = int(service.ack_seq)
    if policy == "none":
        maximum_gap = None
        final_gap = None
        recovered_ack = None
    else:
        maximum_gap = int(coordinator.maximum_gap)
        final_gap = acknowledged - int(coordinator.durable_seq)
        _, payload, _ = store.recover()
        recovered_ack = int(IntegratedService.loads(payload).ack_seq)
    result = {
        "policy": policy, "interval": interval, "seed": seed, "clients": clients,
        "operations": operations, "completed": len(latency), "errors": errors,
        "wall_seconds": wall_seconds, "cpu_seconds": cpu_seconds,
        "throughput_ops_s": len(latency) / wall_seconds,
        "latency_ms": distribution(latency),
        "acknowledged_mutations": acknowledged,
        "maximum_ack_minus_durable": maximum_gap,
        "final_ack_minus_durable": final_gap,
        "recovered_ack_seq": recovered_ack,
        "strict_bound_observed": None if policy == "none" else maximum_gap <= interval,
        "checkpoint_count": checkpoint_count,
        "checkpoint_telemetry_samples_retained": len(checkpoint_records),
        "checkpoint_ms": distribution(checkpoint_times),
        "admission_wait_ms": distribution(list(coordinator.wait_records_ms)),
        "checkpoint_envelope_bytes_total": envelope_bytes,
        "checkpoint_fsync_calls": 2 * checkpoint_count,
        "checkpoint_bytes_per_acknowledged_mutation": envelope_bytes / max(1, acknowledged),
        "account": account,
        "rss_bytes": int(psutil.Process().memory_info().rss),
    }
    (case / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def summarize_checkpoint(rows):
    groups = defaultdict(list)
    for row in rows:
        groups[(row["policy"], row["interval"], row["clients"])].append(row)
    summary = []
    for (policy, interval, clients), values in sorted(groups.items()):
        throughput = [v["throughput_ops_s"] for v in values]
        p99 = [v["latency_ms"]["p99"] for v in values]
        p99_9 = [v["latency_ms"]["p99_9"] for v in values]
        max_gap = [v["maximum_ack_minus_durable"] for v in values
                   if v["maximum_ack_minus_durable"] is not None]
        summary.append({
            "policy": policy, "interval": interval, "clients": clients,
            "runs": len(values), "all_completed": all(v["completed"] == v["operations"] for v in values),
            "all_error_free": all(not v["errors"] for v in values),
            "throughput_median_ops_s": float(np.median(throughput)),
            "throughput_bootstrap95": bootstrap_ci(throughput),
            "p99_median_ms": float(np.median(p99)),
            "p99_bootstrap95": bootstrap_ci(p99),
            "p99_9_median_ms": float(np.median(p99_9)),
            "p99_9_bootstrap95": bootstrap_ci(p99_9),
            "maximum_gap_observed": max(max_gap) if max_gap else None,
            "checkpoint_p50_median_ms": float(np.median([v["checkpoint_ms"]["p50"] for v in values
                                                          if v["checkpoint_ms"]["p50"] is not None]))
                                        if any(v["checkpoint_ms"]["p50"] is not None for v in values) else None,
            "write_bytes_per_mutation_median": float(np.median([
                v["checkpoint_bytes_per_acknowledged_mutation"] for v in values])),
            "complete_transient_bound_max": max(v["account"]["complete_transient_bound_bytes"]
                                                 for v in values),
            "all_within_budget": all(v["account"]["within_budget"] for v in values),
        })
    return summary


def nonstationary_schedule(seed, length, warmup=2432, every=16):
    rng = np.random.default_rng(seed)
    queries = []
    candidates = list(range(warmup, length + 1, every))
    for index, t in enumerate(candidates):
        fraction = index / max(1, len(candidates) - 1)
        if fraction < 1/3:
            phase = "near"
            delays = [71, 135, 263]
        elif fraction < 2/3:
            phase = "far"
            delays = [1031, 1543, 2055]
        else:
            phase = "alternating"
            delays = [71, 135, 263] if (index // 8) % 2 == 0 else [1031, 1543, 2055]
        delay = int(rng.choice(delays)); window = int(rng.choice([32, 64, 128, 256]))
        if t - delay - window >= 0:
            queries.append({"t": t, "delay": delay, "window": window, "phase": phase})
    return queries


def oracle_buckets(queries, base_width=64):
    rows = []
    for query in queries:
        lo = query["t"] - query["delay"] - query["window"]
        hi = query["t"] - query["delay"]
        for bucket in range(lo // base_width, (hi - 1) // base_width + 1):
            rows.append((bucket, query["t"]))
    return rows


def history_methods(queries):
    return {
        "exact_tail": ExactTail(budget=65536, channels=4, max_reach=2314),
        "eh_sum": EHSum(budget=65536, channels=4, max_reach=2314, max_buckets=32),
        "coarse_only": TieredOverlayStore(Config(budget=65536, base_width=64, fine_width=8,
                                                   overlay_capacity=0, policy="none")),
        "fixed_recent": TieredOverlayStore(Config(budget=65536, base_width=64, fine_width=8,
                                                   overlay_capacity=16, policy="recent")),
        "online_overlay": TieredOverlayStore(Config(budget=65536, base_width=64, fine_width=8,
                                                     overlay_capacity=16, policy="online")),
        "finite_future_oracle": TieredOverlayStore(Config(budget=65536, base_width=64, fine_width=8,
                                                           overlay_capacity=16, policy="oracle"),
                                                        oracle_buckets(queries)),
    }


def normalize_answer(answer):
    if answer.get("status") in ("ANSWERED", "EXACT", "APPROX"):
        return np.asarray(answer["value"], np.float64), answer.get("resolution", answer["status"])
    return None, "UNKNOWN"


def run_trace_unit(name, entity, rows, seed):
    rows = np.asarray(rows, np.float32)
    queries = nonstationary_schedule(seed, len(rows))
    by_time = defaultdict(list)
    for query in queries:
        by_time[query["t"]].append(query)
    methods = history_methods(queries)
    records = []
    timing = defaultdict(list)
    for t, row in enumerate(rows, 1):
        for method, store in methods.items():
            started = time.perf_counter_ns(); store.observe(row)
            timing[(method, "update")].append((time.perf_counter_ns() - started) / 1e3)
        for query in by_time.get(t, ()):
            lo = t - query["delay"] - query["window"]
            hi = t - query["delay"]
            truth = rows[lo:hi].astype(np.float64).mean(0)
            for method, store in methods.items():
                started = time.perf_counter_ns()
                answer = store.query(query["delay"], query["window"])
                timing[(method, "query")].append((time.perf_counter_ns() - started) / 1e3)
                prediction, resolution = normalize_answer(answer)
                squared_error = None if prediction is None else float(np.mean((prediction - truth) ** 2))
                records.append({"dataset": name, "entity": entity, "method": method,
                                **query, "resolution": resolution,
                                "squared_error": squared_error})
    variance = float(np.mean(np.var(rows.astype(np.float64), axis=0)))
    summaries = []
    for method, store in methods.items():
        selected = [r for r in records if r["method"] == method]
        answered = [r for r in selected if r["squared_error"] is not None]
        mse = float(np.mean([r["squared_error"] for r in answered])) if answered else None
        phase = {}
        for phase_name in ("near", "far", "alternating"):
            phase_rows = [r for r in answered if r["phase"] == phase_name]
            phase[phase_name] = {"queries": len(phase_rows),
                                 "mse": float(np.mean([r["squared_error"] for r in phase_rows]))
                                        if phase_rows else None}
        account = store.account()
        actions = getattr(store, "actions", [])
        summaries.append({"dataset": name, "entity": entity, "method": method,
                          "queries": len(selected), "answered": len(answered),
                          "coverage": len(answered) / max(1, len(selected)), "mse": mse,
                          "nrmse": None if mse is None else float(np.sqrt(mse / max(variance, 1e-12))),
                          "phase": phase, "query_us": distribution(timing[(method, "query")]),
                          "update_us": distribution(timing[(method, "update")]),
                          "actions": len(actions), "account": account})
    return summaries, records


def load_public_units(profile):
    units = []
    bike = np.load(ROOT / "data/real/bike.npz")
    units.append(("bike", 0, np.concatenate([bike["validation_0"], bike["test_0"]])))
    beijing = np.load(ROOT / "data/real/beijing.npz")
    entities = range(2) if profile == "preflight" else range(12)
    for entity in entities:
        units.append(("beijing", entity, np.concatenate([
            beijing[f"validation_{entity}"], beijing[f"test_{entity}"]])))
    return units


def summarize_trace(units):
    by_method = defaultdict(list)
    lookup = {}
    for row in units:
        by_method[row["method"]].append(row)
        lookup[(row["dataset"], row["entity"], row["method"])] = row
    methods = []
    for method, values in sorted(by_method.items()):
        methods.append({"method": method, "units": len(values),
                        "coverage_mean": float(np.mean([v["coverage"] for v in values])),
                        "mse_mean": float(np.mean([v["mse"] for v in values if v["mse"] is not None])),
                        "nrmse_mean": float(np.mean([v["nrmse"] for v in values if v["nrmse"] is not None])),
                        "query_p50_us_median": float(np.median([v["query_us"]["p50"] for v in values])),
                        "query_p95_us_median": float(np.median([v["query_us"]["p95"] for v in values])),
                        "charged_bytes_max": max(v["account"]["charged_bytes"] for v in values)})
    paired = {}
    for comparator in ("coarse_only", "fixed_recent", "finite_future_oracle"):
        differences = []
        relative = []
        for row in by_method["online_overlay"]:
            other = lookup[(row["dataset"], row["entity"], comparator)]
            differences.append(row["mse"] - other["mse"])
            relative.append((row["mse"] - other["mse"]) / max(other["mse"], 1e-12))
        paired[comparator] = {
            "paired_units": len(differences),
            "mean_mse_difference_online_minus_comparator": float(np.mean(differences)),
            "bootstrap95_mean_difference": bootstrap_ci(differences, statistic=np.mean),
            "mean_relative_difference": float(np.mean(relative)),
            "online_wins": sum(value < 0 for value in differences),
        }
        paired[comparator]["by_phase"] = {}
        for phase in ("near", "far", "alternating"):
            phase_differences = []
            for row in by_method["online_overlay"]:
                other = lookup[(row["dataset"], row["entity"], comparator)]
                phase_differences.append(row["phase"][phase]["mse"] -
                                         other["phase"][phase]["mse"])
            paired[comparator]["by_phase"][phase] = {
                "mean_mse_difference": float(np.mean(phase_differences)),
                "bootstrap95": bootstrap_ci(phase_differences, statistic=np.mean),
                "online_wins": sum(value < 0 for value in phase_differences),
            }
    return {"methods": methods, "paired_online_overlay": paired}


def run_soak_case(root, policy, duration, seed, clients=8, interval=500):
    case = root / f"{policy}-{duration}s"
    case.mkdir(parents=True, exist_ok=False)
    service = IntegratedService(); service.initialize_facts(128)
    for index in range(2432): service.observe(row_for(index), count_ack=False)
    store = None if policy == "none" else TwoSlotStore(case / "checkpoint")
    coordinator = coordinator_for(policy, service, store, interval)
    stop = threading.Event(); barrier = threading.Barrier(clients)
    latency_samples = []; latency_lock = threading.Lock(); counts = [0] * clients
    errors = []
    start_wall = time.perf_counter(); deadline = start_wall + duration

    def worker(worker_id):
        rng = np.random.default_rng(seed + worker_id * 1009)
        local = []
        sample_cap = 25000
        try:
            barrier.wait(timeout=30)
            while time.perf_counter() < deadline:
                index = counts[worker_id]; u = rng.random(); started = time.perf_counter_ns()
                if u < .65:
                    coordinator.mutate(lambda index=index, worker_id=worker_id:
                                       service.observe(row_for(index + worker_id * 1000003)))
                elif u < .90:
                    delay = int(rng.choice([71, 263, 775, 1543]))
                    service.query(worker_id, delay, int(rng.choice([32, 64, 128, 256])))
                elif u < .97:
                    key = int(rng.integers(0, 256)); value = row_for(index)
                    coordinator.mutate(lambda key=key, value=value: service.put_fact(key, value))
                elif u < .99:
                    service.get_fact(int(rng.integers(0, 256)))
                else:
                    service.controller_tick()
                elapsed = (time.perf_counter_ns() - started) / 1e6
                # Per-worker reservoir sampling keeps the diagnostic workspace
                # fixed while sampling the full duration rather than only warmup.
                if len(local) < sample_cap:
                    local.append(elapsed)
                else:
                    replacement = int(rng.integers(0, index + 1))
                    if replacement < sample_cap:
                        local[replacement] = elapsed
                counts[worker_id] += 1
        except Exception as exc:
            errors.append(repr(exc))
        with latency_lock:
            latency_samples.extend(local)

    rss_samples = []
    rss_series = []
    with ThreadPoolExecutor(max_workers=clients) as pool:
        futures = [pool.submit(worker, worker_id) for worker_id in range(clients)]
        while not all(f.done() for f in futures):
            rss = int(psutil.Process().memory_info().rss)
            rss_samples.append(rss)
            rss_series.append({"elapsed_seconds": time.perf_counter() - start_wall,
                               "rss_bytes": rss})
            time.sleep(min(1.0, max(0.01, deadline - time.perf_counter())))
        for future in futures: future.result()
    close_coordinator(coordinator, force=True)
    wall = time.perf_counter() - start_wall
    snapshot = service.dumps(); account = service.account(len(snapshot))
    records = [r for r in coordinator.records if not r.get("initial")]
    initial_bytes = int(coordinator.initial_checkpoint_envelope_bytes)
    checkpoint_count = int(coordinator.checkpoint_count_total) - (1 if policy != "none" else 0)
    result = {"policy": policy, "duration_target_seconds": duration, "wall_seconds": wall,
              "clients": clients, "interval": interval, "completed": sum(counts),
              "throughput_ops_s": sum(counts) / wall, "latency_sample_ms": distribution(latency_samples),
              "latency_sample_count": len(latency_samples), "errors": errors,
              "maximum_ack_minus_durable": coordinator.maximum_gap,
              "checkpoint_count": checkpoint_count,
              "checkpoint_telemetry_samples_retained": len(records),
              "checkpoint_ms": distribution([float(r["total_ms"]) for r in records]),
              "checkpoint_envelope_bytes_total": int(coordinator.checkpoint_envelope_bytes_total) - initial_bytes,
              "rss_bytes": distribution(rss_samples), "rss_series": rss_series,
              "telemetry_limits": {"checkpoint_records": getattr(coordinator, "telemetry_limit", None),
                                   "latency_samples": clients * 25000},
              "account": account}
    (case / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def environment_record():
    return {"timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "python": sys.version, "platform": platform.platform(),
            "machine": platform.machine(), "processor": platform.processor(),
            "cpu_count_logical": psutil.cpu_count(), "memory_bytes": psutil.virtual_memory().total,
            "numpy": np.__version__, "psutil": psutil.__version__,
            "max_rss_platform_units": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}


def write_log(output, profile, checkpoint_summary, trace_summary, soak):
    log = output / "experiment-log.md"
    text = f"""---
experiment_id: MTMEM-B-261102-001
system: MT-Memory
type: P0-P1-supplement
date: 2026-11-02
profile: {profile}
status: complete
platform: {platform.platform()!r}
---

# P0/P1 supplemental experiment log

## Protocol

See `source/PROTOCOL.md`. All results are descriptive observations; no
scientific-success threshold was applied.

## Completed units

- Checkpoint comparison groups: {len(checkpoint_summary)}
- Public trace-derived entities: {trace_summary['methods'][0]['units'] if trace_summary['methods'] else 0}
- Sustained cost profiles: {len(soak)}

## Output files

- `checkpoint/raw.json` and `checkpoint/summary.json`
- `trace/unit-summary.json`, `trace/raw-query-records.json`, and `trace/summary.json`
- `soak/summary.json`
- `FINAL_SUMMARY.json`

## Scope note

The public values are real observations, but their query schedule is controlled.
This host is macOS/arm64; these results do not substitute for Linux/x86
confirmation. The explicit soak duration in `soak/summary.json` must be reported
verbatim.
"""
    log.write_text(text)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--profile", choices=("preflight", "formal"), default="preflight")
    parser.add_argument("--soak-seconds", type=int)
    parser.add_argument("--soak-policies", nargs="+", choices=("none", "async", "strict"))
    args = parser.parse_args()
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    (output / "source").mkdir()
    (output / "source" / "PROTOCOL.md").write_text((Path(__file__).with_name("PROTOCOL.md")).read_text())
    (output / "ENVIRONMENT.json").write_text(json.dumps(environment_record(), indent=2) + "\n")

    checkpoint_dir = output / "checkpoint"; checkpoint_dir.mkdir()
    if args.profile == "preflight":
        policies = ("none", "async", "strict", "sync")
        intervals = (100,); seeds = (9101,); clients_set = (2,); operations = 1200
    else:
        policies = ("none", "async", "strict", "sync")
        intervals = (100, 500, 2000); seeds = (9101, 9113, 9127, 9133, 9151)
        clients_set = (1, 8); operations = 12000
    checkpoint_rows = []
    for clients in clients_set:
        for policy in policies:
            policy_intervals = (0,) if policy == "none" else intervals
            for interval in policy_intervals:
                for seed in seeds:
                    checkpoint_rows.append(run_checkpoint_case(checkpoint_dir, policy, interval,
                                                               seed, clients, operations))
    checkpoint_summary = summarize_checkpoint(checkpoint_rows)
    (checkpoint_dir / "raw.json").write_text(json.dumps(checkpoint_rows, indent=2) + "\n")
    (checkpoint_dir / "summary.json").write_text(json.dumps(checkpoint_summary, indent=2) + "\n")

    trace_dir = output / "trace"; trace_dir.mkdir()
    unit_summaries = []; query_records = []
    for index, (name, entity, rows) in enumerate(load_public_units(args.profile)):
        summary, records = run_trace_unit(name, entity, rows, 12001 + index * 17)
        unit_summaries.extend(summary); query_records.extend(records)
    trace_summary = summarize_trace(unit_summaries)
    (trace_dir / "unit-summary.json").write_text(json.dumps(unit_summaries, indent=2) + "\n")
    (trace_dir / "raw-query-records.json").write_text(json.dumps(query_records, separators=(",", ":")) + "\n")
    (trace_dir / "summary.json").write_text(json.dumps(trace_summary, indent=2) + "\n")

    soak_dir = output / "soak"; soak_dir.mkdir()
    duration = args.soak_seconds if args.soak_seconds is not None else (3 if args.profile == "preflight" else 60)
    soak_policies = tuple(args.soak_policies) if args.soak_policies else (
        ("strict",) if args.profile == "preflight" else ("none", "async", "strict"))
    soak = [run_soak_case(soak_dir, policy, duration, 13001) for policy in soak_policies]
    (soak_dir / "summary.json").write_text(json.dumps(soak, indent=2) + "\n")

    final = {"profile": args.profile, "environment": environment_record(),
             "checkpoint_policy_summary": checkpoint_summary,
             "trace_summary": trace_summary, "soak_summary": soak,
             "scope": {"query_schedule": "controlled trace over public observations",
                       "rpo_unit": "acknowledged mutations",
                       "fault_model": "single-host process state and local file path",
                       "cross_platform_completed": False}}
    (output / "FINAL_SUMMARY.json").write_text(json.dumps(final, indent=2) + "\n")
    write_log(output, args.profile, checkpoint_summary, trace_summary, soak)
    print(json.dumps({"status": "complete", "output": str(output),
                      "checkpoint_groups": len(checkpoint_summary),
                      "trace_units": trace_summary["methods"][0]["units"],
                      "soak_cases": len(soak)}, indent=2))


if __name__ == "__main__":
    main()

