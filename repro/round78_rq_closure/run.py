from __future__ import annotations

import argparse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
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
from mtmemory_icde.core.service import ControlledOverlayStore, IntegratedService  # noqa: E402


SEED = 20261103
HISTORY_BUDGET = 65536
SERVICE_BUDGET = 131072
MAX_REACH = 4096


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def pct(values, q):
    return None if not values else float(np.percentile(np.asarray(values, np.float64), q))


def distribution(values):
    return {"count": len(values), "p50": pct(values, 50), "p95": pct(values, 95),
            "p99": pct(values, 99), "p99_9": pct(values, 99.9),
            "maximum": None if not values else float(max(values))}


def bootstrap_ci(values, seed=SEED, repetitions=5000):
    x = np.asarray(values, np.float64)
    if not len(x):
        return None
    if len(x) == 1:
        return [float(x[0]), float(x[0])]
    rng = np.random.default_rng(seed)
    samples = rng.choice(x, size=(repetitions, len(x)), replace=True).mean(axis=1)
    return [float(np.percentile(samples, 2.5)), float(np.percentile(samples, 97.5))]


def environment():
    return {"timestamp_utc": datetime.now(timezone.utc).isoformat(), "python": sys.version,
            "platform": platform.platform(), "machine": platform.machine(),
            "numpy": np.__version__, "psutil": psutil.__version__,
            "logical_cpus": psutil.cpu_count(), "memory_bytes": psutil.virtual_memory().total}


def load_units(split, limit=None):
    units = []
    bike = np.load(ROOT / "data/real/bike.npz")
    units.append(("bike", 0, np.asarray(bike[f"{split}_0"], np.float32)))
    beijing = np.load(ROOT / "data/real/beijing.npz")
    count = 12 if limit is None else max(0, limit - 1)
    for entity in range(min(12, count)):
        units.append(("beijing", entity, np.asarray(beijing[f"{split}_{entity}"], np.float32)))
    return units


def all_split_units(limit=None):
    out = []
    bike = np.load(ROOT / "data/real/bike.npz")
    out.append(("bike", 0, np.asarray(bike["train_0"], np.float32),
                np.asarray(bike["validation_0"], np.float32), np.asarray(bike["test_0"], np.float32)))
    beijing = np.load(ROOT / "data/real/beijing.npz")
    count = 12 if limit is None else max(0, limit - 1)
    for entity in range(min(12, count)):
        out.append(("beijing", entity, np.asarray(beijing[f"train_{entity}"], np.float32),
                    np.asarray(beijing[f"validation_{entity}"], np.float32),
                    np.asarray(beijing[f"test_{entity}"], np.float32)))
    return out


def workload_id(spec):
    dwell = "steady" if spec["dwell_queries"] == 0 else str(spec["dwell_queries"])
    return f"shift{spec['shift_buckets']}-dwell{dwell}-width{spec['width_buckets']}"


def workload_queries(length, spec, seed, warmup=2432, every=32, offset=0):
    rng = np.random.default_rng(seed)
    result = []
    near = 128
    shift = int(spec["shift_buckets"]) * 64
    dwell = int(spec["dwell_queries"])
    width = int(spec["width_buckets"])
    for qi, t in enumerate(range(warmup, length + 1, every)):
        if shift == 0:
            center = near
            phase = "near"
        elif dwell == 0:
            center = near + shift
            phase = "far"
        elif (qi // dwell) % 2 == 0:
            center = near + shift
            phase = "far"
        else:
            center = near
            phase = "near"
        jitter = int(rng.integers(-width * 32, width * 32 + 1)) if width else 0
        window = int(rng.choice([32, 64, 128, 256]))
        delay = max(7, min(MAX_REACH - window - 1, center + jitter + 7))
        absolute_t = offset + t
        if t - delay - window >= 0:
            result.append({"t": absolute_t, "delay": delay, "window": window, "phase": phase})
    return result


def history_store(policy, max_reach=MAX_REACH, base_width=64, overlay_capacity=16):
    cfg = Config(budget=HISTORY_BUDGET, channels=4, base_width=base_width, fine_width=8,
                 max_reach=max_reach, overlay_capacity=overlay_capacity, policy=policy,
                 query_history=128)
    return TieredOverlayStore(cfg)


def evaluate_pair(rows, spec, seed):
    rows = np.asarray(rows, np.float32)
    queries = workload_queries(len(rows), spec, seed)
    by_t = defaultdict(list)
    for query in queries:
        by_t[query["t"]].append(query)
    stores = {"fixed": history_store("recent"), "dynamic": history_store("online")}
    errors = defaultdict(list); latencies = defaultdict(list); resolutions = defaultdict(lambda: defaultdict(int))
    for t, row in enumerate(rows, 1):
        for store in stores.values():
            store.observe(row)
        for query in by_t.get(t, ()):
            lo = t - query["delay"] - query["window"]; hi = t - query["delay"]
            truth = rows[lo:hi].astype(np.float64).mean(axis=0)
            for method, store in stores.items():
                started = time.perf_counter_ns(); answer = store.query(query["delay"], query["window"])
                latencies[method].append((time.perf_counter_ns() - started) / 1e3)
                if answer["value"] is not None:
                    errors[method].append(float(np.mean((np.asarray(answer["value"]) - truth) ** 2)))
                resolutions[method][answer["resolution"]] += 1
    variance = float(np.mean(np.var(rows.astype(np.float64), axis=0)))
    result = {}
    for method, store in stores.items():
        mse = float(np.mean(errors[method])) if errors[method] else None
        result[method] = {"queries": len(queries), "answered": len(errors[method]),
                          "coverage": len(errors[method]) / max(1, len(queries)), "mse": mse,
                          "nrmse": None if mse is None else float(np.sqrt(mse / max(variance, 1e-12))),
                          "query_us": distribution(latencies[method]),
                          "resolutions": dict(resolutions[method]), "actions": len(store.actions),
                          "charged_bytes": store.account()["charged_bytes"]}
    result["delta_dynamic_minus_fixed"] = result["dynamic"]["mse"] - result["fixed"]["mse"]
    return result


def rq3_specs(profile):
    if profile == "preflight":
        return [{"shift_buckets": s, "dwell_queries": d, "width_buckets": 2}
                for s in (0, 16, 30) for d in ((0,) if s == 0 else (0, 16))]
    specs = [{"shift_buckets": 0, "dwell_queries": 0, "width_buckets": 2}]
    for shift in (8, 16, 24, 30):
        for dwell in (0, 4, 16, 64, 256):
            for width in (1, 4):
                specs.append({"shift_buckets": shift, "dwell_queries": dwell,
                              "width_buckets": width})
    return specs


def summarize_rq3(records):
    grouped = defaultdict(list)
    for row in records:
        grouped[row["workload_id"]].append(row)
    summary = []
    for wid, values in grouped.items():
        deltas = [row["result"]["delta_dynamic_minus_fixed"] for row in values]
        spec = values[0]["spec"]
        summary.append({"workload_id": wid, "spec": spec, "units": len(values),
                        "mean_mse_dynamic_minus_fixed": float(np.mean(deltas)),
                        "bootstrap95_mean_difference": bootstrap_ci(deltas),
                        "dynamic_wins": sum(value < 0 for value in deltas),
                        "fixed_mse_mean": float(np.mean([v["result"]["fixed"]["mse"] for v in values])),
                        "dynamic_mse_mean": float(np.mean([v["result"]["dynamic"]["mse"] for v in values])),
                        "coverage_min": float(min(min(v["result"]["fixed"]["coverage"],
                                                       v["result"]["dynamic"]["coverage"]) for v in values)),
                        "charged_bytes": values[0]["result"]["fixed"]["charged_bytes"]})
    return sorted(summary, key=lambda row: (row["spec"]["shift_buckets"],
                                             row["spec"]["dwell_queries"],
                                             row["spec"]["width_buckets"]))


def freeze_rq3(summary):
    stable = next(row for row in summary if row["spec"]["shift_buckets"] == 0)
    nontrivial = [row for row in summary if row["spec"]["shift_buckets"] > 0 and
                  row["spec"]["dwell_queries"] > 0]
    crossing = [row for row in nontrivial if row["bootstrap95_mean_difference"][0] <= 0 <=
                row["bootstrap95_mean_difference"][1]]
    critical = min(crossing or nontrivial, key=lambda row: abs(row["mean_mse_dynamic_minus_fixed"]))
    candidates = [row for row in summary if row["spec"]["shift_buckets"] > 0]
    significant = [row for row in candidates if row["bootstrap95_mean_difference"][1] < 0]
    dominant = min(significant or candidates, key=lambda row: row["mean_mse_dynamic_minus_fixed"])
    return {"selection_split": "train", "selection_rule": "PROTOCOL.md",
            "workloads": {"stable": {"workload_id": stable["workload_id"], "spec": stable["spec"]},
                          "critical": {"workload_id": critical["workload_id"], "spec": critical["spec"]},
                          "dynamic_dominant": {"workload_id": dominant["workload_id"],
                                               "spec": dominant["spec"]}}}


def run_rq3(output, profile):
    root = output / "rq3_boundary"; root.mkdir()
    specs = rq3_specs(profile); units = load_units("train", 2 if profile == "preflight" else None)
    calibration = []
    for spec in specs:
        for ui, (dataset, entity, rows) in enumerate(units):
            # Common random numbers across the grid isolate distance/dwell/width.
            result = evaluate_pair(rows, spec, SEED + ui * 17)
            calibration.append({"dataset": dataset, "entity": entity, "workload_id": workload_id(spec),
                                "spec": spec, "result": result})
    summary = summarize_rq3(calibration); frozen = freeze_rq3(summary)
    write_json(root / "calibration_raw.json", calibration)
    write_json(root / "calibration_summary.json", summary)
    write_json(root / "RQ3_FREEZE.json", frozen)
    confirmation = []
    validation = load_units("validation", 2 if profile == "preflight" else None)
    for label, choice in frozen["workloads"].items():
        for ui, (dataset, entity, rows) in enumerate(validation):
            result = evaluate_pair(rows, choice["spec"], SEED + 50000 + ui * 17)
            confirmation.append({"label": label, "dataset": dataset, "entity": entity,
                                 "workload_id": choice["workload_id"], "spec": choice["spec"],
                                 "result": result})
    confirmation_summary = summarize_rq3(confirmation)
    for row in confirmation_summary:
        row["label"] = next(r["label"] for r in confirmation if r["workload_id"] == row["workload_id"])
    write_json(root / "confirmation_raw.json", confirmation)
    write_json(root / "confirmation_summary.json", confirmation_summary)
    return frozen, {"calibration": summary, "confirmation": confirmation_summary}


class StudyService(IntegratedService):
    def __init__(self, history_policy="online"):
        super().__init__()
        cfg = Config(budget=HISTORY_BUDGET, channels=4, base_width=64, fine_width=8,
                     max_reach=MAX_REACH, overlay_capacity=16, policy=history_policy,
                     query_history=128)
        self.history = ControlledOverlayStore(cfg, active_capacity=16)


class SynchronousCoordinator:
    def __init__(self, service, store, interval):
        self.service = service; self.store = store; self.interval = int(interval)
        self.lock = threading.RLock(); self.records = []; self.wait_records_ms = []
        self.checkpoint_count_total = 0; self.checkpoint_envelope_bytes_total = 0
        initial = store.commit(service.dumps()); self.durable_seq = int(service.ack_seq)
        self.maximum_gap = 0; self.initial_checkpoint_envelope_bytes = int(initial["envelope_bytes"])
        self.records.append({**initial, "snapshot_ack_seq": self.durable_seq, "initial": True,
                             "total_ms": 0.0})
        self.checkpoint_count_total = 1; self.checkpoint_envelope_bytes_total = int(initial["envelope_bytes"])

    def mutate(self, fn):
        with self.lock:
            result = fn(); gap = int(self.service.ack_seq) - self.durable_seq
            if gap >= self.interval:
                started = time.perf_counter_ns(); record = self.store.commit(self.service.dumps())
                elapsed = (time.perf_counter_ns() - started) / 1e6
                self.durable_seq = int(self.service.ack_seq); gap = 0
                self.records.append({**record, "snapshot_ack_seq": self.durable_seq,
                                     "initial": False, "total_ms": elapsed})
                self.wait_records_ms.append(elapsed); self.checkpoint_count_total += 1
                self.checkpoint_envelope_bytes_total += int(record["envelope_bytes"])
            self.maximum_gap = max(self.maximum_gap, gap); return result

    def close(self, force=True):
        if force and int(self.service.ack_seq) != self.durable_seq:
            with self.lock:
                started = time.perf_counter_ns(); record = self.store.commit(self.service.dumps())
                elapsed = (time.perf_counter_ns() - started) / 1e6
                self.durable_seq = int(self.service.ack_seq)
                self.records.append({**record, "snapshot_ack_seq": self.durable_seq,
                                     "initial": False, "forced": True, "total_ms": elapsed})
                self.wait_records_ms.append(elapsed); self.checkpoint_count_total += 1
                self.checkpoint_envelope_bytes_total += int(record["envelope_bytes"])


def close_coordinator(coordinator):
    if isinstance(coordinator, SynchronousCoordinator):
        coordinator.close(True); return
    coordinator.force_checkpoint()
    with coordinator._cv:
        coordinator._stop = True; coordinator._cv.notify_all()
    coordinator.thread.join(timeout=180)
    if coordinator.thread.is_alive():
        raise TimeoutError("checkpoint thread did not stop")


def build_service(policy, warm_rows):
    service = StudyService("recent" if policy == "fixed" else "online")
    service.initialize_facts(128)
    for row in warm_rows:
        service.observe(row, count_ack=False)
    return service


def make_coordinator(kind, service, path, interval):
    store = TwoSlotStore(path)
    if kind == "sync":
        return SynchronousCoordinator(service, store, interval), store
    return CheckpointCoordinator(service, store, interval, strict=True), store


def checkpoint_metrics(coordinator, store, service):
    records = [row for row in coordinator.records if not row.get("initial")]
    initial = int(coordinator.initial_checkpoint_envelope_bytes)
    payload_bytes = int(coordinator.checkpoint_envelope_bytes_total) - initial
    _, payload, _ = store.recover(); recovered = StudyService.loads(payload)
    snapshot = service.dumps(); account = service.account(len(snapshot))
    return {"maximum_ack_minus_durable": int(coordinator.maximum_gap),
            "final_ack_minus_durable": int(service.ack_seq) - int(coordinator.durable_seq),
            "recovered_ack_seq": int(recovered.ack_seq), "acknowledged_mutations": int(service.ack_seq),
            "checkpoint_count": len(records),
            "checkpoint_ms": distribution([float(row["total_ms"]) for row in records]),
            "checkpoint_bytes_total": payload_bytes,
            "checkpoint_bytes_per_mutation": payload_bytes / max(1, int(service.ack_seq)),
            "strict_rpo_observed": int(coordinator.maximum_gap) <= int(coordinator.interval),
            "account": account}


def rq5_quality_case(case, dataset, entity, warm_rows, test_rows, spec, allocation, durability,
                     interval, seed):
    case.mkdir(parents=True, exist_ok=False)
    service = build_service(allocation, warm_rows); coordinator, store = make_coordinator(
        durability, service, case / "checkpoint", interval)
    combined = np.concatenate([warm_rows, test_rows]); offset = len(warm_rows)
    queries = workload_queries(len(test_rows), spec, seed, warmup=2432, offset=offset)
    by_t = defaultdict(list)
    for query in queries: by_t[query["t"]].append(query)
    mse = []; op_latency = []; query_latency = []; fact_checks = 0; fact_correct = 0
    wall_start = time.perf_counter()
    for local, row in enumerate(test_rows, 1):
        started = time.perf_counter_ns(); coordinator.mutate(lambda row=row: service.observe(row))
        op_latency.append((time.perf_counter_ns() - started) / 1e6)
        if local % 128 == 0:
            key = (local // 128) % 256; delete = (local // 128) % 7 == 0
            value = np.asarray([local, -local, local / 2, 1], np.float32) / 10000
            started = time.perf_counter_ns()
            coordinator.mutate(lambda key=key, value=value, delete=delete:
                               service.put_fact(key, value, delete=delete))
            op_latency.append((time.perf_counter_ns() - started) / 1e6)
        absolute_t = offset + local
        for query in by_t.get(absolute_t, ()):
            lo = absolute_t - query["delay"] - query["window"]; hi = absolute_t - query["delay"]
            truth = combined[lo:hi].astype(np.float64).mean(axis=0)
            key = (local // 32) % 256; started = time.perf_counter_ns()
            answer = service.query(key, query["delay"], query["window"])
            elapsed = (time.perf_counter_ns() - started) / 1e6
            op_latency.append(elapsed); query_latency.append(elapsed)
            if answer["history"]["value"] is not None:
                mse.append(float(np.mean((np.asarray(answer["history"]["value"]) - truth) ** 2)))
            expected = service.get_fact(key); fact_checks += 1
            fact_correct += int(expected["live"] == answer["fact"]["live"] and
                                expected["version"] == answer["fact"]["version"])
    close_coordinator(coordinator); wall = time.perf_counter() - wall_start
    variance = float(np.mean(np.var(combined.astype(np.float64), axis=0)))
    result = {"kind": "quality", "dataset": dataset, "entity": entity,
              "allocation": allocation, "durability": durability, "interval": interval,
              "workload_id": workload_id(spec), "queries": len(queries), "answered": len(mse),
              "coverage": len(mse) / max(1, len(queries)),
              "mse": float(np.mean(mse)) if mse else None,
              "nrmse": float(np.sqrt(np.mean(mse) / max(variance, 1e-12))) if mse else None,
              "fact_correct_fraction": fact_correct / max(1, fact_checks),
              "wall_seconds": wall, "throughput_ops_s": len(op_latency) / wall,
              "latency_ms": distribution(op_latency), "query_latency_ms": distribution(query_latency)}
    result.update(checkpoint_metrics(coordinator, store, service)); write_json(case / "result.json", result)
    return result


def rq5_cost_case(case, rows, spec, allocation, durability, interval, seed, clients, operations):
    case.mkdir(parents=True, exist_ok=False)
    warm = rows[:MAX_REACH + 64]; service = build_service(allocation, warm)
    coordinator, store = make_coordinator(durability, service, case / "checkpoint", interval)
    barrier = threading.Barrier(clients); errors = []; latencies = []; lock = threading.Lock()
    per_client = operations // clients

    def worker(worker_id):
        rng = np.random.default_rng(seed + worker_id * 101); local = []
        try:
            barrier.wait(timeout=30)
            for i in range(per_client):
                u = rng.random(); started = time.perf_counter_ns()
                if u < .58:
                    row = rows[(i * clients + worker_id) % len(rows)]
                    coordinator.mutate(lambda row=row: service.observe(row))
                elif u < .86:
                    qi = i + worker_id * per_client
                    shift = spec["shift_buckets"] * 64
                    dwell = spec["dwell_queries"]
                    far = shift > 0 and (dwell == 0 or (qi // max(1, dwell)) % 2 == 0)
                    center = 128 + (shift if far else 0)
                    window = int(rng.choice([32, 64, 128, 256]))
                    delay = max(7, min(MAX_REACH-window-1,
                                       center + int(rng.integers(-spec["width_buckets"]*32,
                                                                 spec["width_buckets"]*32+1)) + 7))
                    service.query(worker_id, delay, window)
                elif u < .96:
                    key = int(rng.integers(0, 256)); value = rows[(i + worker_id) % len(rows)]
                    coordinator.mutate(lambda key=key, value=value: service.put_fact(key, value))
                elif u < .98:
                    key = int(rng.integers(0, 256))
                    coordinator.mutate(lambda key=key: service.put_fact(key, np.zeros(4), delete=True))
                else:
                    service.get_fact(int(rng.integers(0, 256)))
                local.append((time.perf_counter_ns() - started) / 1e6)
        except Exception as exc:
            errors.append(repr(exc))
        with lock: latencies.extend(local)

    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=clients) as pool:
        futures = [pool.submit(worker, worker_id) for worker_id in range(clients)]
        for future in futures: future.result()
    close_coordinator(coordinator); wall = time.perf_counter() - started
    result = {"kind": "cost", "allocation": allocation, "durability": durability,
              "interval": interval, "workload_id": workload_id(spec), "clients": clients,
              "seed": seed,
              "requested_operations": per_client * clients, "completed": len(latencies),
              "errors": errors, "wall_seconds": wall, "throughput_ops_s": len(latencies) / wall,
              "latency_ms": distribution(latencies)}
    result.update(checkpoint_metrics(coordinator, store, service)); write_json(case / "result.json", result)
    return result


def summarize_rq5(rows):
    groups = defaultdict(list)
    for row in rows:
        groups[(row["kind"], row["workload_id"], row["allocation"], row["durability"])].append(row)
    summary = []
    for (kind, workload, allocation, durability), values in sorted(groups.items()):
        out = {"kind": kind, "workload_id": workload, "allocation": allocation,
               "durability": durability, "runs": len(values),
               "throughput_median_ops_s": float(np.median([v["throughput_ops_s"] for v in values])),
               "p99_median_ms": float(np.median([v["latency_ms"]["p99"] for v in values])),
               "p99_9_median_ms": float(np.median([v["latency_ms"]["p99_9"] for v in values])),
               "write_bytes_per_mutation_median": float(np.median([
                   v["checkpoint_bytes_per_mutation"] for v in values])),
               "maximum_gap": max(v["maximum_ack_minus_durable"] for v in values),
               "all_rpo_observed": all(v["strict_rpo_observed"] for v in values),
               "all_recovery_current": all(v["recovered_ack_seq"] == v["acknowledged_mutations"]
                                           for v in values),
               "all_within_budget": all(v["account"]["within_budget"] for v in values)}
        if kind == "quality":
            out.update({"mse_mean": float(np.mean([v["mse"] for v in values])),
                        "nrmse_mean": float(np.mean([v["nrmse"] for v in values])),
                        "coverage_min": min(v["coverage"] for v in values),
                        "fact_correct_min": min(v["fact_correct_fraction"] for v in values)})
        else:
            out.update({"all_completed": all(v["completed"] == v["requested_operations"] for v in values),
                        "all_error_free": all(not v["errors"] for v in values)})
        summary.append(out)
    return summary


def rq5_contrasts(rows):
    """Paired full-system versus simple-reference effects on identical traces."""
    result = []
    for workload in sorted(set(row["workload_id"] for row in rows)):
        quality = [row for row in rows if row["kind"] == "quality" and
                   row["workload_id"] == workload]
        index = {(row["dataset"], row["entity"], row["allocation"], row["durability"]): row
                 for row in quality}
        pairs = []
        for dataset, entity in sorted(set((row["dataset"], row["entity"]) for row in quality)):
            simple = index[(dataset, entity, "fixed", "sync")]
            full = index[(dataset, entity, "dynamic", "strict")]
            pairs.append({"dataset": dataset, "entity": entity,
                          "mse_delta_full_minus_simple": full["mse"] - simple["mse"],
                          "relative_mse_change": (full["mse"] - simple["mse"]) /
                                                 max(simple["mse"], 1e-12),
                          "throughput_ratio_full_over_simple": full["throughput_ops_s"] /
                                                               simple["throughput_ops_s"],
                          "p99_ratio_full_over_simple": full["latency_ms"]["p99"] /
                                                        max(simple["latency_ms"]["p99"], 1e-12)})
        deltas = [row["mse_delta_full_minus_simple"] for row in pairs]
        relative = [row["relative_mse_change"] for row in pairs]
        cost = [row for row in rows if row["kind"] == "cost" and row["workload_id"] == workload]
        cost_index = {(row["seed"], row["allocation"], row["durability"]): row for row in cost}
        cost_pairs = []
        for seed in sorted(set(row["seed"] for row in cost)):
            simple = cost_index[(seed, "fixed", "sync")]
            full = cost_index[(seed, "dynamic", "strict")]
            cost_pairs.append({"seed": seed,
                               "throughput_ratio_full_over_simple": full["throughput_ops_s"] /
                                                                    simple["throughput_ops_s"],
                               "p99_ratio_full_over_simple": full["latency_ms"]["p99"] /
                                                             max(simple["latency_ms"]["p99"], 1e-12),
                               "p99_9_ratio_full_over_simple": full["latency_ms"]["p99_9"] /
                                                               max(simple["latency_ms"]["p99_9"], 1e-12),
                               "write_ratio_full_over_simple": full["checkpoint_bytes_per_mutation"] /
                                                               max(simple["checkpoint_bytes_per_mutation"], 1e-12)})
        result.append({"workload_id": workload, "quality_pairs": len(pairs),
                       "mean_mse_delta_full_minus_simple": float(np.mean(deltas)),
                       "bootstrap95_mse_delta": bootstrap_ci(deltas),
                       "mean_relative_mse_change": float(np.mean(relative)),
                       "bootstrap95_relative_mse_change": bootstrap_ci(relative),
                       "full_quality_wins": sum(value < 0 for value in deltas),
                       "quality_throughput_ratio_median": float(np.median([
                           row["throughput_ratio_full_over_simple"] for row in pairs])),
                       "quality_p99_ratio_median": float(np.median([
                           row["p99_ratio_full_over_simple"] for row in pairs])),
                       "cost_pairs": len(cost_pairs),
                       "cost_throughput_ratio_median": float(np.median([
                           row["throughput_ratio_full_over_simple"] for row in cost_pairs])),
                       "cost_p99_ratio_median": float(np.median([
                           row["p99_ratio_full_over_simple"] for row in cost_pairs])),
                       "cost_p99_9_ratio_median": float(np.median([
                           row["p99_9_ratio_full_over_simple"] for row in cost_pairs])),
                       "cost_write_ratio_median": float(np.median([
                           row["write_ratio_full_over_simple"] for row in cost_pairs])),
                       "pairs": pairs, "cost_replica_pairs": cost_pairs})
    return result


def run_rq5(output, profile, frozen):
    root = output / "rq5_2x2"; root.mkdir(); raw = []
    interval = 500; units = all_split_units(2 if profile == "preflight" else 5)
    for label, choice in frozen["workloads"].items():
        spec = choice["spec"]
        for allocation in ("fixed", "dynamic"):
            for durability in ("sync", "strict"):
                for ui, (dataset, entity, train, validation, test) in enumerate(units):
                    warm = np.concatenate([train[-MAX_REACH:], validation])
                    case = root / f"quality-{label}-{allocation}-{durability}-{dataset}-{entity}"
                    raw.append(rq5_quality_case(case, dataset, entity, warm, test, spec, allocation,
                                                durability, interval, SEED + ui * 31))
                cost_seeds = (0,) if profile == "preflight" else (0, 1, 2, 3, 4)
                cost_rows = units[-1][4]
                for replica in cost_seeds:
                    case = root / f"cost-{label}-{allocation}-{durability}-r{replica}"
                    raw.append(rq5_cost_case(case, cost_rows, spec, allocation, durability, interval,
                                             SEED + replica * 211, 2 if profile == "preflight" else 8,
                                             1200 if profile == "preflight" else 6000))
    summary = summarize_rq5(raw); contrasts = rq5_contrasts(raw)
    write_json(root / "raw.json", raw); write_json(root / "summary.json", summary)
    write_json(root / "contrasts.json", contrasts)
    return {"cells": summary, "full_vs_simple": contrasts}


def candidate_stores(reach):
    candidates = {"exact_tail": ExactTail(HISTORY_BUDGET, 4, reach),
                  "eh_sum": EHSum(HISTORY_BUDGET, 4, reach, 32)}
    for base in (32, 64, 128, 256, 512):
        for capacity in (0, 8, 16):
            name = f"tiered-b{base}-k{capacity}"
            try:
                candidates[name] = TieredOverlayStore(Config(
                    budget=HISTORY_BUDGET, channels=4, base_width=base, fine_width=8,
                    max_reach=reach, overlay_capacity=capacity,
                    policy="none" if capacity == 0 else "recent", query_history=128))
            except MemoryError:
                pass
    return candidates


def range_queries(stage_start, stage_end, reach, seed, every):
    rng = np.random.default_rng(seed); result = []
    fractions = (.10, .25, .40, .55, .70, .85)
    for qi, t in enumerate(range(stage_start + max(512, reach // 8), stage_end + 1, every)):
        window = int(rng.choice([32, 64, 128, 256])); center = int(reach * fractions[qi % len(fractions)])
        delay = max(7, min(reach - window - 1, center + int(rng.integers(-15, 16))))
        if t - delay - window >= 0: result.append({"t": t, "delay": delay, "window": window})
    return result


def rq2_unit(dataset, entity, train, validation, test, reach, seed, profile):
    rows = np.concatenate([train, validation, test]); train_end = len(train)
    validation_end = train_end + len(validation); stores = candidate_stores(reach)
    every = 512 if profile == "preflight" else 128
    queries = [("validation", q) for q in range_queries(train_end, validation_end, reach, seed, every)]
    queries += [("test", q) for q in range_queries(validation_end, len(rows), reach, seed + 19, every)]
    by_t = defaultdict(list)
    for stage, query in queries: by_t[query["t"]].append((stage, query))
    stats = defaultdict(lambda: defaultdict(lambda: {"errors": [], "answered": 0, "queries": 0,
                                                     "latency_us": []}))
    for t, row in enumerate(rows, 1):
        for store in stores.values(): store.observe(row)
        for stage, query in by_t.get(t, ()):
            lo = t - query["delay"] - query["window"]; hi = t - query["delay"]
            truth = rows[lo:hi].astype(np.float64).mean(axis=0)
            for method, store in stores.items():
                started = time.perf_counter_ns(); answer = store.query(query["delay"], query["window"])
                elapsed = (time.perf_counter_ns() - started) / 1e3
                slot = stats[method][stage]; slot["queries"] += 1; slot["latency_us"].append(elapsed)
                value = answer.get("value")
                if value is not None:
                    slot["answered"] += 1
                    slot["errors"].append(float(np.mean((np.asarray(value) - truth) ** 2)))
    variance = float(np.mean(np.var(rows.astype(np.float64), axis=0))); result = []
    for method, store in stores.items():
        for stage in ("validation", "test"):
            slot = stats[method][stage]; mse = float(np.mean(slot["errors"])) if slot["errors"] else None
            result.append({"dataset": dataset, "entity": entity, "reach": reach, "method": method,
                           "stage": stage, "queries": slot["queries"], "answered": slot["answered"],
                           "coverage": slot["answered"] / max(1, slot["queries"]), "mse": mse,
                           "nrmse": None if mse is None else float(np.sqrt(mse / max(variance, 1e-12))),
                           "query_us": distribution(slot["latency_us"]),
                           "charged_bytes": store.account()["charged_bytes"]})
    return result


def summarize_rq2(rows):
    groups = defaultdict(list)
    for row in rows: groups[(row["reach"], row["method"], row["stage"])].append(row)
    aggregate = []
    for (reach, method, stage), values in sorted(groups.items()):
        valid = [v for v in values if v["nrmse"] is not None]
        aggregate.append({"reach": reach, "method": method, "stage": stage, "units": len(values),
                          "coverage_mean": float(np.mean([v["coverage"] for v in values])),
                          "coverage_min": float(min(v["coverage"] for v in values)),
                          "nrmse_mean": None if not valid else float(np.mean([v["nrmse"] for v in valid])),
                          "nrmse_bootstrap95": None if not valid else bootstrap_ci([v["nrmse"] for v in valid]),
                          "charged_bytes_max": max(v["charged_bytes"] for v in values),
                          "query_p95_us_median": float(np.median([v["query_us"]["p95"] for v in values]))})
    selected = []
    for reach in sorted(set(row["reach"] for row in aggregate)):
        choices = [row for row in aggregate if row["reach"] == reach and row["stage"] == "validation"
                   and row["method"].startswith("tiered-") and row["nrmse_mean"] is not None]
        full = [row for row in choices if row["coverage_min"] >= .999]
        chosen = min(full or choices, key=lambda row: (row["nrmse_mean"], -row["coverage_mean"]))
        test = next(row for row in aggregate if row["reach"] == reach and
                    row["method"] == chosen["method"] and row["stage"] == "test")
        selected.append({"reach": reach, "selected_on_validation": chosen["method"],
                         "validation": chosen, "test": test})
    return aggregate, selected


def judge_rq2(selected, raw):
    reaches = np.asarray([row["reach"] for row in selected], np.float64)
    errors = np.asarray([row["test"]["nrmse_mean"] for row in selected], np.float64)
    coverages = np.asarray([row["test"]["coverage_mean"] for row in selected], np.float64)
    slope = float(np.polyfit(np.log2(reaches), errors, 1)[0]) if len(reaches) > 1 else 0.0
    first, last = float(errors[0]), float(errors[-1]); ratio = last / max(first, 1e-12)
    shortest, longest = int(reaches[0]), int(reaches[-1])
    methods = {row["reach"]: row["selected_on_validation"] for row in selected}
    per_unit = defaultdict(dict)
    for row in raw:
        if row["stage"] == "test" and row["method"] == methods.get(row["reach"]):
            per_unit[(row["dataset"], row["entity"])][row["reach"]] = row["nrmse"]
    paired = [values[longest] - values[shortest] for values in per_unit.values()
              if values.get(shortest) is not None and values.get(longest) is not None]
    exact = [row for row in raw if row["stage"] == "test" and row["method"] == "exact_tail"]
    exact_coverage = {reach: float(np.mean([row["coverage"] for row in exact
                                            if row["reach"] == reach]))
                      for reach in (shortest, longest)}
    supported = bool(((slope > 0 and ratio >= 1.05) and
                      (not paired or bootstrap_ci(paired)[0] > 0)) or coverages.min() < .999)
    wording = ("Under fixed memory, how do historical coverage and query precision trade off?" if supported else
               "Within a declared historical reach and fixed memory budget, which bounded layout gives the best query precision?")
    return {"current_wording_supported": supported, "observed_log2_reach_nrmse_slope": slope,
            "longest_over_shortest_nrmse_ratio": ratio, "minimum_test_coverage": float(coverages.min()),
            "paired_longest_minus_shortest_nrmse_mean": float(np.mean(paired)),
            "paired_longest_minus_shortest_bootstrap95": bootstrap_ci(paired),
            "exact_tail_coverage_shortest": exact_coverage[shortest],
            "exact_tail_coverage_longest": exact_coverage[longest],
            "recommended_wording": wording,
            "interpretation": ("The frozen range scan exposes an empirical coverage/precision frontier."
                               if supported else
                               "The scan does not establish a reproducible range penalty; retain only the declared-reach claim.")}


def run_rq2(output, profile):
    root = output / "rq2_range"; root.mkdir(); raw = []
    reaches = (512, 2048, 8192) if profile == "preflight" else (512, 1024, 2048, 4096, 8192, 16384)
    units = all_split_units(2 if profile == "preflight" else None)
    for reach in reaches:
        for ui, (dataset, entity, train, validation, test) in enumerate(units):
            # Common random numbers across reaches isolate the declared range.
            raw.extend(rq2_unit(dataset, entity, train, validation, test, reach,
                                SEED + ui * 17, profile))
    aggregate, selected = summarize_rq2(raw); judgment = judge_rq2(selected, raw)
    write_json(root / "raw.json", raw); write_json(root / "aggregate.json", aggregate)
    write_json(root / "selected_frontier.json", selected); write_json(root / "RQ2_JUDGMENT.json", judgment)
    return {"selected_frontier": selected, "judgment": judgment}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--profile", choices=("preflight", "formal"), default="preflight")
    args = parser.parse_args(); output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    (output / "source").mkdir(); (output / "source" / "PROTOCOL.md").write_text(
        Path(__file__).with_name("PROTOCOL.md").read_text())
    write_json(output / "ENVIRONMENT.json", environment())
    started = time.perf_counter(); frozen, rq3 = run_rq3(output, args.profile)
    rq5 = run_rq5(output, args.profile, frozen); rq2 = run_rq2(output, args.profile)
    final = {"profile": args.profile, "elapsed_seconds": time.perf_counter() - started,
             "rq3": rq3, "rq3_frozen": frozen, "rq5_2x2": rq5, "rq2": rq2,
             "scope": {"observations": "public real data", "queries": "controlled",
                       "history_budget_bytes": HISTORY_BUDGET,
                       "complete_service_budget_bytes": SERVICE_BUDGET,
                       "fault_model": "single-host process and local filesystem"}}
    write_json(output / "FINAL_SUMMARY.json", final)
    print(json.dumps({"status": "complete", "output": str(output),
                      "elapsed_seconds": final["elapsed_seconds"],
                      "rq2_wording_supported": rq2["judgment"]["current_wording_supported"],
                      "rq3_frozen": frozen["workloads"]}, indent=2))


if __name__ == "__main__":
    main()
