from __future__ import annotations

from collections import deque
import threading
import time


class CheckpointFailure(RuntimeError):
    """Persistence/capture failed; no new durability may be assumed."""


class CheckpointCoordinator:
    """Periodic checkpointing with an optional strict acknowledged-RPO guard."""

    def __init__(self, service, store, interval: int, strict: bool = True,
                 telemetry_limit: int = 4096, verify_capture: bool = True):
        self.service = service
        self.store = store
        self.interval = int(interval)
        self.strict = bool(strict)
        self._cv = threading.Condition(threading.RLock())
        self._stop = False
        self._force = False
        self._failure = None
        self.durable_seq = 0
        # Telemetry is operational metadata, so it must be bounded just like
        # the managed state.  Lifetime counters retain write-amplification
        # information after old per-checkpoint samples leave the ring.
        self.telemetry_limit = int(telemetry_limit)
        self.verify_capture = bool(verify_capture)
        self.records = deque(maxlen=self.telemetry_limit)
        self.wait_records_ms = deque(maxlen=self.telemetry_limit)
        self.checkpoint_count_total = 0
        self.checkpoint_envelope_bytes_total = 0
        self.initial_checkpoint_envelope_bytes = 0
        self.maximum_gap = 0
        self.thread = None
        if self.interval > 0:
            try:
                _, payload, _ = self.store.recover()
                restored = type(service).loads(payload)
                self.durable_seq = int(restored.ack_seq)
            except FileNotFoundError:
                rec = self.store.commit(service.dumps())
                rec["snapshot_ack_seq"] = int(service.ack_seq)
                rec["initial"] = True
                self._record(rec)
                self.initial_checkpoint_envelope_bytes = int(rec.get("envelope_bytes", 0))
                self.durable_seq = int(service.ack_seq)
            self.thread = threading.Thread(target=self._checkpoint_loop, name="checkpoint", daemon=True)
            self.thread.start()

    def _record(self, record):
        self.records.append(record)
        self.checkpoint_count_total += 1
        self.checkpoint_envelope_bytes_total += int(record.get("envelope_bytes", 0))

    def mutate(self, fn):
        if self.interval <= 0:
            return fn()
        started = None
        with self._cv:
            self._raise_failure()
            if self.strict:
                while int(self.service.ack_seq) - self.durable_seq >= self.interval:
                    if started is None:
                        started = time.perf_counter_ns()
                    self._cv.notify_all()
                    self._cv.wait(timeout=0.05)
                    self._raise_failure()
            if started is not None:
                self.wait_records_ms.append((time.perf_counter_ns() - started) / 1e6)
            result = fn()
            gap = int(self.service.ack_seq) - self.durable_seq
            self.maximum_gap = max(self.maximum_gap, gap)
            if gap >= self.interval:
                self._cv.notify_all()
            return result

    def _raise_failure(self):
        if self._failure is not None:
            raise CheckpointFailure('checkpoint failed; durable prefix unchanged') from self._failure

    def _checkpoint_loop(self):
        try:
            self._checkpoint_loop_body()
        except Exception as exc:
            with self._cv:
                self._failure = exc
                self._stop = True
                self._cv.notify_all()

    def _checkpoint_loop_body(self):
        while True:
            with self._cv:
                self._cv.wait_for(lambda: self._stop or self._force or
                                  int(self.service.ack_seq) - self.durable_seq >= self.interval)
                current = int(self.service.ack_seq)
                if self._stop and not self._force and current == self.durable_seq:
                    return
                if current == self.durable_seq:
                    self._force = False
                    if self._stop:
                        return
                    continue
                serialize_start = time.perf_counter_ns()
                payload = self.service.dumps()
                # Admission remains excluded by _cv. Queries cannot change ack_seq.
                snapshot_ack = int(self.service.ack_seq)
                capture_ms = (time.perf_counter_ns() - serialize_start) / 1e6
                validation_start = time.perf_counter_ns()
                if self.verify_capture:
                    decoded_ack = int(type(self.service).loads(payload).ack_seq)
                    if decoded_ack != snapshot_ack:
                        raise RuntimeError("captured prefix does not match snapshot")
                validation_ms = (time.perf_counter_ns() - validation_start) / 1e6
                serialize_ms = capture_ms + validation_ms
            persist_start = time.perf_counter_ns()
            rec = self.store.commit(payload)
            persist_ms = (time.perf_counter_ns() - persist_start) / 1e6
            with self._cv:
                self.durable_seq = max(self.durable_seq, snapshot_ack)
                self._record({**rec, "snapshot_ack_seq": snapshot_ack,
                              "serialize_ms": serialize_ms,
                              "capture_ms": capture_ms, "validation_ms": validation_ms,
                              "persist_ms": persist_ms,
                              "total_ms": serialize_ms + persist_ms,
                              "initial": False})
                self._force = False
                self._cv.notify_all()
                if self._stop and int(self.service.ack_seq) == self.durable_seq:
                    return

    def force_checkpoint(self):
        if self.interval <= 0:
            return
        with self._cv:
            self._raise_failure()
            target = int(self.service.ack_seq)
            self._force = True
            self._cv.notify_all()
            self._cv.wait_for(lambda: self.durable_seq >= target or self._failure is not None, timeout=30)
            self._raise_failure()
            if self.durable_seq < target:
                raise TimeoutError("forced checkpoint did not become durable")

    def close(self, force: bool = True):
        if self.interval <= 0:
            return
        try:
            if force:
                self.force_checkpoint()
        finally:
            with self._cv:
                self._stop = True
                self._cv.notify_all()
            self.thread.join(timeout=30)
        if self.thread.is_alive():
            raise TimeoutError("checkpoint thread did not stop")
