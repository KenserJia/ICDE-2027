"""Bounded exact facts + controlled coarse/fine history + serializable service."""
from __future__ import annotations

from collections import deque
from io import BytesIO
import json
import threading

import numpy as np


from .history import Config as HistoryConfig, TieredOverlayStore


class ControlledOverlayStore(TieredOverlayStore):
    """Tiered store with a fixed physical ceiling and variable active slots."""
    def __init__(self, cfg: HistoryConfig, active_capacity: int = 4):
        super().__init__(cfg)
        self.active_capacity = int(active_capacity)

    def _active_indices(self):
        return range(min(self.active_capacity, len(self.overlay_ids)))

    def _overlay_slot(self, bid):
        indices = np.fromiter(self._active_indices(), dtype=np.int64)
        if not len(indices):
            return None
        hits = indices[self.overlay_ids[indices] == bid]
        return None if len(hits) == 0 else int(hits[0])

    def _install_overlay(self, bid, sums, counts, score, reason):
        indices = list(self._active_indices())
        if not indices:
            return False
        for j in indices:
            if self.overlay_ids[j] >= 0:
                self.overlay_scores[j] = self._score(int(self.overlay_ids[j]))
        old = self._overlay_slot(bid)
        if old is not None:
            idx = old
        else:
            empty = [j for j in indices if self.overlay_ids[j] < 0]
            idx = empty[0] if empty else min(indices, key=lambda j: self.overlay_scores[j])
            if self.overlay_ids[idx] >= 0 and score <= self.overlay_scores[idx]:
                return False
            if self.overlay_ids[idx] >= 0:
                self.actions.append({"event": self.event_count, "action": "drop",
                                     "bucket": int(self.overlay_ids[idx]), "reason": reason})
        self.overlay_ids[idx] = bid; self.overlay_sums[idx] = sums
        self.overlay_counts[idx] = counts; self.overlay_scores[idx] = score
        self.actions.append({"event": self.event_count, "action": "promote",
                             "bucket": int(bid), "reason": reason})
        self._trim_actions()
        return True

    def _trim_actions(self):
        if len(self.actions) > 256:
            self.actions[:] = self.actions[-256:]

    def set_active_capacity(self, capacity: int):
        capacity = int(capacity)
        if capacity not in (4, 8, 16) or capacity > len(self.overlay_ids):
            raise ValueError("active overlay capacity")
        before = self.active_capacity
        if before == capacity:
            return False
        resident = []
        for index, bid in enumerate(self.overlay_ids):
            if bid >= 0:
                resident.append((float(self._score(int(bid))), int(bid),
                                 self.overlay_sums[index].copy(), self.overlay_counts[index].copy()))
        resident.sort(reverse=True, key=lambda row: (row[0], row[1]))
        self.overlay_ids.fill(-1); self.overlay_sums.fill(0); self.overlay_counts.fill(0); self.overlay_scores.fill(0)
        self.active_capacity = capacity
        for index, (score, bid, sums, counts) in enumerate(resident[:capacity]):
            self.overlay_ids[index] = bid; self.overlay_sums[index] = sums
            self.overlay_counts[index] = counts; self.overlay_scores[index] = score
        self.actions.append({"event": self.event_count, "action": "reconfigure",
                             "before": before, "after": capacity})
        self._trim_actions()
        return True

    @classmethod
    def from_blob(cls, blob: bytes, active_capacity: int):
        base = TieredOverlayStore.loads(blob)
        base.__class__ = cls
        base.active_capacity = int(active_capacity)
        base._trim_actions()
        return base


class IntegratedService:
    KEYSPACE = 256
    CHANNELS = 4

    def __init__(self):
        cfg = HistoryConfig(budget=65536, channels=self.CHANNELS, base_width=64,
                            fine_width=8, max_reach=2314, overlay_capacity=16,
                            policy="online", query_history=128)
        self.history = ControlledOverlayStore(cfg, active_capacity=4)
        self.fact_values = np.zeros((self.KEYSPACE, self.CHANNELS), np.float32)
        self.fact_versions = np.zeros(self.KEYSPACE, np.int64)
        self.fact_live = np.zeros(self.KEYSPACE, np.bool_)
        self.version = 0
        self.ack_seq = 0
        self.request_seq = 0
        self.query_shapes = deque(maxlen=128)
        self.controller_actions = deque(maxlen=128)
        self._lock = threading.RLock()

    @property
    def event_count(self):
        return self.history.event_count

    def initialize_facts(self, count=128):
        for key in range(count):
            value = np.array([key, key*.5, -key, key*.25], np.float32) / max(1, count)
            self.put_fact(key, value, count_ack=False)
        self.ack_seq = 0

    def observe(self, row, count_ack=True):
        with self._lock:
            self.history.observe(row); self.history._trim_actions(); self.request_seq += 1
            if count_ack: self.ack_seq += 1
            return self.ack_seq

    def put_fact(self, key, value, delete=False, count_ack=True):
        key = int(key)
        if not 0 <= key < self.KEYSPACE:
            raise ValueError("bounded fact catalog")
        with self._lock:
            self.version += 1; self.fact_versions[key] = self.version
            self.fact_live[key] = not delete
            self.fact_values[key] = 0 if delete else np.asarray(value, np.float32)
            self.request_seq += 1
            if count_ack: self.ack_seq += 1
            return {"key": key, "version": self.version, "live": not delete, "ack_seq": self.ack_seq}

    def get_fact(self, key):
        key = int(key)
        with self._lock:
            self.request_seq += 1
            return {"key": key, "version": int(self.fact_versions[key]),
                    "live": bool(self.fact_live[key]),
                    "value": self.fact_values[key].copy() if self.fact_live[key] else None}

    def query(self, key, delay, window, record=True):
        key = int(key); delay = int(delay); window = int(window)
        with self._lock:
            history = self.history.query(delay, window, record=record)
            fact = {"key": key, "version": int(self.fact_versions[key]),
                    "live": bool(self.fact_live[key]),
                    "value": self.fact_values[key].copy() if self.fact_live[key] else None}
            end = self.event_count-delay; start = end-window
            self.query_shapes.append((start % 64 != 0 or end % 64 != 0, delay+window))
            self.request_seq += 1
            return {"history": history, "fact": fact, "lo": start, "hi": end}

    def controller_tick(self):
        with self._lock:
            if not self.query_shapes:
                return None
            shifted = float(np.mean([row[0] for row in self.query_shapes]))
            far = float(np.mean([row[1] > 768 for row in self.query_shapes]))
            target = 16 if shifted >= .55 or far >= .65 else (4 if shifted <= .15 and far <= .25 else 8)
            before = self.history.active_capacity
            changed = self.history.set_active_capacity(target)
            action = {"request_seq": self.request_seq, "event_count": self.event_count,
                      "before": before, "after": target, "shifted_fraction": shifted,
                      "far_fraction": far, "changed": bool(changed)}
            self.controller_actions.append(action)
            return action

    def dumps(self):
        with self._lock:
            meta = {"version": self.version, "ack_seq": self.ack_seq,
                    "request_seq": self.request_seq,
                    "active_capacity": self.history.active_capacity,
                    "query_shapes": list(self.query_shapes),
                    "controller_actions": list(self.controller_actions)}
            history_blob = self.history.dumps(); buffer = BytesIO()
            # The history blob is itself a portable NPZ image. Compressing the
            # outer service image removes container/zero-array redundancy and
            # keeps resident state + two durable slots + one pending slot under
            # the declared 128 KiB complete transient budget.
            np.savez_compressed(buffer, meta=np.array(json.dumps(meta, separators=(",", ":"))),
                                history=np.frombuffer(history_blob, np.uint8),
                                fact_values=self.fact_values, fact_versions=self.fact_versions,
                                fact_live=self.fact_live)
            return buffer.getvalue()

    @classmethod
    def loads(cls, blob: bytes):
        archive = np.load(BytesIO(blob), allow_pickle=False)
        meta = json.loads(str(archive["meta"])); service = cls()
        service.history = ControlledOverlayStore.from_blob(archive["history"].tobytes(), meta["active_capacity"])
        service.fact_values[:] = archive["fact_values"]
        service.fact_versions[:] = archive["fact_versions"]
        service.fact_live[:] = archive["fact_live"]
        service.version = int(meta["version"]); service.ack_seq = int(meta["ack_seq"])
        service.request_seq = int(meta["request_seq"])
        service.query_shapes = deque((tuple(row) for row in meta["query_shapes"]), maxlen=128)
        service.controller_actions = deque(meta["controller_actions"], maxlen=128)
        return service

    def account(self, snapshot_bytes=None):
        history = self.history.account()
        facts = self.fact_values.nbytes + self.fact_versions.nbytes + self.fact_live.nbytes
        resident = history["resident_array_bytes"] + history["metadata_bytes"] + facts + 4096
        out = {"history_physical_array_bytes": history["resident_array_bytes"],
               "history_metadata_bytes": history["metadata_bytes"],
               "fact_catalog_bytes": facts, "service_control_reserved_bytes": 4096,
               "resident_reserved_bytes": resident, "workspace_bytes": 4096,
               "budget_bytes": 131072, "active_overlay_capacity": self.history.active_capacity,
               "physical_overlay_capacity": len(self.history.overlay_ids)}
        if snapshot_bytes is not None:
            envelope = int(snapshot_bytes) + 88
            out.update({"snapshot_payload_bytes": int(snapshot_bytes), "snapshot_envelope_bytes": envelope,
                        "two_slot_steady_bytes": 2*envelope,
                        "transient_three_envelope_bytes": 3*envelope,
                        "disk_two_slot_bytes": 2*envelope,
                        "pending_envelope_reservation_bytes": envelope,
                        "resident_plus_pending_workspace_bytes": resident + envelope + 4096,
                        "ledger_is_physical_ram_bound": False,
                        "complete_transient_bound_bytes": resident + 3*envelope + 4096,
                        "within_budget": resident + 3*envelope + 4096 <= 131072})
        return out
