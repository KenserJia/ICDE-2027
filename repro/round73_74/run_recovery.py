from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import multiprocessing as mp
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time

import numpy as np

from durable_store import HEADER, TRAILER_BYTES, CorruptCheckpoint, TwoSlotStore, decode


ROOT = Path(__file__).resolve().parent
ENGINE_ROOT = Path(os.environ.get("MTMEM_ICDE_ROOT", Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(ENGINE_ROOT / "src"))
from mtmemory.round6x.engine import Config, Engine  # noqa: E402


def engine_payload(generation: int, destination: Path) -> tuple[bytes, dict]:
    cfg = Config(channels=4, segment_length=64, budget=262144,
                 cache_capacity=8, width=8, max_segments=12, keyspace=32,
                 workspace=2048)
    engine = Engine(cfg, destination)
    rng = np.random.default_rng(7100 + generation)
    rows = rng.normal(size=(256 + generation * 8, 4)).astype(np.float32)
    engine.observe(rows)
    engine.put(3, generation % 4, 16, 0, 2)
    answer = engine.query(3)
    payload = engine.dumps()
    expected = {"generation": generation, "nobs": int(engine.control[0]),
                "fact_version": int(engine.fact(3)[0]), "query_status": answer["status"],
                "query_mean": answer.get("mean")}
    engine.close()
    return payload, expected


def validate_engine(payload: bytes, expected: dict, path: Path) -> dict:
    engine = Engine.loads(payload, path)
    answer = engine.query(3, record=False)
    actual = {"nobs": int(engine.control[0]), "fact_version": int(engine.fact(3)[0]),
              "query_status": answer["status"], "query_mean": answer.get("mean")}
    engine.close()
    ok = (actual["nobs"] == expected["nobs"] and
          actual["fact_version"] == expected["fact_version"] and
          actual["query_status"] == expected["query_status"] and
          (actual["query_mean"] == expected["query_mean"] or
           np.isclose(actual["query_mean"], expected["query_mean"], rtol=0, atol=1e-12)))
    return {"ok": bool(ok), "actual": actual}


def reset_dir(path: Path):
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True)


def crash_matrix(base: Path, payloads: list[bytes], expected: list[dict], repetitions=20):
    failpoints = ["after_partial_write", "before_file_fsync", "after_file_fsync",
                  "after_replace_before_dir_fsync", "after_dir_fsync"]
    rows = []
    payload_file = base / "payload-new.bin"
    payload_file.write_bytes(payloads[1])
    for failpoint in failpoints:
        for rep in range(repetitions):
            work = base / f"crash-{failpoint}-{rep:02d}"
            reset_dir(work)
            store = TwoSlotStore(work)
            store.commit(payloads[0], 0)
            started = time.perf_counter_ns()
            proc = subprocess.run([sys.executable, str(ROOT / "crash_child.py"), str(work),
                                   str(payload_file), "1", failpoint],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            elapsed = (time.perf_counter_ns() - started) / 1e6
            generation, payload, meta = store.recover()
            valid = validate_engine(payload, expected[generation], work / "restored.dat")
            pending = [p.name for p in work.glob("*.pending")]
            # A recovered service must be able to checkpoint again.  Reusing
            # the target pending filename also reclaims any abandoned partial
            # write without an unbounded cleanup scan.
            resume_meta = store.commit(payloads[1], generation + 1)
            resumed_generation, resumed_payload, _ = store.recover()
            resumed_valid = validate_engine(resumed_payload, expected[1], work / "resumed.dat")
            rows.append({"failpoint": failpoint, "rep": rep, "returncode": proc.returncode,
                         "signal_sigkill": proc.returncode == -9, "recovered_generation": generation,
                         "valid_engine": valid["ok"], "elapsed_ms": elapsed,
                         "pending_files_before_resume": pending,
                         "pending_files_after_resume": [p.name for p in work.glob("*.pending")],
                         "resume_generation": resumed_generation,
                         "resume_valid_engine": resumed_valid["ok"],
                         "resume_commit": resume_meta, "scan": meta,
                         "stderr": proc.stderr.decode(errors="replace")})
    return rows


def mutate(blob: bytes, mode: str) -> bytes:
    data = bytearray(blob)
    if mode == "truncate_header": return bytes(data[:max(1, HEADER.size // 2)])
    if mode == "truncate_payload": return bytes(data[:HEADER.size + max(1, (len(data)-HEADER.size-TRAILER_BYTES)//2)])
    if mode == "truncate_trailer": return bytes(data[:-7])
    positions = {"flip_magic": 0, "flip_header": 12,
                 "flip_payload": HEADER.size + 11,
                 "flip_trailer": len(data) - 1}
    data[positions[mode]] ^= 0x5A
    return bytes(data)


def corruption_matrix(base: Path, payloads: list[bytes], expected: list[dict]):
    modes = ["truncate_header", "truncate_payload", "truncate_trailer",
             "flip_magic", "flip_header", "flip_payload", "flip_trailer"]
    rows = []
    for mode in modes:
        work = base / f"corrupt-{mode}"
        reset_dir(work)
        store = TwoSlotStore(work)
        store.commit(payloads[0], 0); store.commit(payloads[1], 1)
        valid, _ = store.scan(); newest_slot = valid[-1][1]
        path = store.paths[newest_slot]
        path.write_bytes(mutate(path.read_bytes(), mode))
        generation, payload, meta = store.recover()
        valid_engine = validate_engine(payload, expected[generation], work / "restored.dat")
        rows.append({"mode": mode, "recovered_generation": generation,
                     "rollback_distance": 1-generation, "valid_engine": valid_engine["ok"],
                     "corruption_detected": bool(meta["invalid"]), "scan": meta})
    both = base / "corrupt-both"
    reset_dir(both); store = TwoSlotStore(both)
    store.commit(payloads[0], 0); store.commit(payloads[1], 1)
    for path in store.paths:
        path.write_bytes(mutate(path.read_bytes(), "flip_payload"))
    try:
        store.recover(); rejected = False; message = ""
    except FileNotFoundError as exc:
        rejected = True; message = str(exc)
    rows.append({"mode": "both_slots_corrupt", "all_corrupt_rejected": rejected, "error": message})
    return rows


def fast_payload(generation: int) -> bytes:
    body = json.dumps({"generation": generation, "value": generation * 17,
                       "padding": "x" * 2048}, sort_keys=True).encode()
    return body


def concurrent_test(base: Path, commits=1000, readers=4):
    work = base / "concurrent"; reset_dir(work); store = TwoSlotStore(work)
    store.commit(fast_payload(0), 0)
    stop = threading.Event(); errors = []; observations = [[] for _ in range(readers)]
    def writer():
        for generation in range(1, commits + 1):
            store.commit(fast_payload(generation), generation)
        stop.set()
    def reader(index):
        previous = -1
        while not stop.is_set() or previous < commits:
            try:
                generation, payload, _ = store.recover()
                parsed = json.loads(payload)
                if parsed["generation"] != generation or parsed["value"] != generation * 17:
                    errors.append({"reader": index, "kind": "mixed", "generation": generation})
                if generation < previous:
                    errors.append({"reader": index, "kind": "regression", "before": previous, "after": generation})
                previous = generation; observations[index].append(generation)
            except Exception as exc:
                errors.append({"reader": index, "kind": "exception", "error": repr(exc)})
            if previous >= commits:
                break
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=readers+1) as pool:
        futures = [pool.submit(reader, i) for i in range(readers)]
        futures.append(pool.submit(writer))
        for future in futures: future.result()
    return {"commits": commits, "readers": readers,
            "read_counts": [len(v) for v in observations],
            "last_generations": [v[-1] if v else None for v in observations],
            "errors": errors, "elapsed_s": time.perf_counter()-started}


def _process_writer(directory: str, commits: int):
    store = TwoSlotStore(directory)
    for generation in range(1, commits + 1):
        store.commit(fast_payload(generation), generation)
    (Path(directory) / "writer.done").write_text(str(commits), encoding="ascii")


def _process_reader(directory: str, commits: int, index: int, queue):
    store = TwoSlotStore(directory); previous = -1; reads = 0; errors = []
    done = Path(directory) / "writer.done"
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            generation, payload, _ = store.recover(); parsed = json.loads(payload)
            if parsed["generation"] != generation or parsed["value"] != generation * 17:
                errors.append({"kind": "mixed", "generation": generation})
            if generation < previous:
                errors.append({"kind": "regression", "before": previous, "after": generation})
            previous = generation; reads += 1
        except Exception as exc:
            errors.append({"kind": "exception", "error": repr(exc)})
        if done.exists() and previous >= commits:
            break
    queue.put({"reader": index, "reads": reads, "last_generation": previous,
               "errors": errors, "timed_out": previous < commits})


def multiprocess_test(base: Path, commits=500, readers=4):
    work = base / "multiprocess"; reset_dir(work); TwoSlotStore(work).commit(fast_payload(0), 0)
    context = mp.get_context("spawn"); queue = context.Queue(); started = time.perf_counter()
    reader_processes = [context.Process(target=_process_reader,
                                        args=(str(work), commits, i, queue))
                        for i in range(readers)]
    writer = context.Process(target=_process_writer, args=(str(work), commits))
    for process in reader_processes: process.start()
    writer.start(); writer.join(30)
    for process in reader_processes: process.join(30)
    rows = [queue.get(timeout=2) for _ in reader_processes]
    return {"commits": commits, "readers": readers, "writer_exitcode": writer.exitcode,
            "reader_exitcodes": [p.exitcode for p in reader_processes], "reader_results": rows,
            "errors": [error for row in rows for error in row["errors"]],
            "elapsed_s": time.perf_counter()-started}


def latency_test(base: Path, payload: bytes, commits=100):
    work = base / "latency"; reset_dir(work); store = TwoSlotStore(work)
    commit_ms=[]; recover_ms=[]
    for generation in range(commits):
        t=time.perf_counter_ns();meta=store.commit(payload,generation);commit_ms.append((time.perf_counter_ns()-t)/1e6)
        t=time.perf_counter_ns();store.recover();recover_ms.append((time.perf_counter_ns()-t)/1e6)
    sizes={p.name:p.stat().st_size for p in work.iterdir() if p.is_file()}
    def stats(values):
        return {"mean":float(np.mean(values)),"p50":float(np.percentile(values,50)),
                "p95":float(np.percentile(values,95)),"p99":float(np.percentile(values,99)),
                "max":float(np.max(values))}
    return {"payload_bytes":len(payload),"last_commit":meta,"commit_ms":stats(commit_ms),
            "recover_ms":stats(recover_ms),"files":sizes,"disk_bytes":sum(sizes.values())}


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--out",default=str(ROOT/"results"/"recovery.json"))
    parser.add_argument("--repetitions",type=int,default=20);args=parser.parse_args()
    out=Path(args.out);out.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="round74-") as tmp:
        tmp=Path(tmp);payloads=[];expected=[]
        for generation in range(2):
            payload, exp=engine_payload(generation,tmp/f"source-{generation}.dat")
            payloads.append(payload);expected.append(exp)
        base=ROOT/"checkpoints";base.mkdir(exist_ok=True)
        result={"protocol":"Round 7.4 strong recovery", "platform":sys.platform,
                "payload_sha256":[hashlib.sha256(p).hexdigest() for p in payloads],
                "payload_bytes":[len(p) for p in payloads], "expected":expected,
                "crash_matrix":crash_matrix(base,payloads,expected,args.repetitions),
                "corruption_matrix":corruption_matrix(base,payloads,expected),
                "concurrency":concurrent_test(base),
                "multiprocess_concurrency":multiprocess_test(base),
                "latency":latency_test(base,payloads[1])}
    out.write_text(json.dumps(result,indent=2,sort_keys=True),encoding="utf-8")
    print(json.dumps({"output":str(out),"crashes":len(result["crash_matrix"]),
                      "corruptions":len(result["corruption_matrix"]),
                      "concurrency_errors":len(result["concurrency"]["errors"])},sort_keys=True))


if __name__=="__main__":main()
