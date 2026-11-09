"""Bounded coarse-base + replaceable fine-overlay reference implementation."""
from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
import json
import os
import threading
import time
from collections import Counter
from collections import OrderedDict

import numpy as np


@dataclass(frozen=True)
class Config:
    budget: int = 65536
    channels: int = 4
    base_width: int = 64
    fine_width: int = 8
    max_reach: int = 2314
    overlay_capacity: int = 8
    replay_capacity: int = 0
    policy: str = "recent"
    query_history: int = 128
    catalog_delays: tuple[int, ...] = (64, 256, 1024, 2048)


class BoundedFactCache:
    """Exact latest-value cache with explicit LRU eviction and tombstones."""
    def __init__(self, capacity=64, channels=4):
        self.capacity=int(capacity);self.channels=int(channels);self.data=OrderedDict();self.version=0;self.evictions=0
    def put(self,key,value):
        self.version+=1;key=int(key)
        if key in self.data:del self.data[key]
        evicted=None
        if len(self.data)>=self.capacity:
            evicted=self.data.popitem(last=False);self.evictions+=1
        self.data[key]=(np.asarray(value,np.float32).copy(),self.version)
        return None if evicted is None else int(evicted[0])
    def get(self,key):
        key=int(key)
        if key not in self.data:return None
        value,version=self.data.pop(key);self.data[key]=(value,version);return value.copy(),version
    def delete(self,key):
        self.version+=1;return self.data.pop(int(key),None) is not None
    def account(self):
        # Reserved slots, not current occupancy: key/version/value plus 24 B slot metadata.
        resident=self.capacity*(8+8+self.channels*4+24)
        return {"capacity":self.capacity,"resident_reserved_bytes":resident,"entries":len(self.data),"evictions":self.evictions}


class TieredOverlayStore:
    """A bounded summary ring whose overlays never determine answerability."""

    def __init__(self, cfg: Config, oracle_buckets=()):
        if cfg.base_width % cfg.fine_width:
            raise ValueError("fine_width must divide base_width")
        self.cfg = cfg
        self.base_slots = int(np.ceil(cfg.max_reach / cfg.base_width)) + 3
        self.sub = cfg.base_width // cfg.fine_width
        self.base_ids = np.full(self.base_slots, -1, np.int64)
        self.base_sums = np.zeros((self.base_slots, cfg.channels), np.float64)
        self.base_counts = np.zeros(self.base_slots, np.int32)
        k = cfg.overlay_capacity
        self.overlay_ids = np.full(k, -1, np.int64)
        self.overlay_sums = np.zeros((k, self.sub, cfg.channels), np.float64)
        self.overlay_counts = np.zeros((k, self.sub), np.int32)
        self.overlay_scores = np.zeros(k, np.float64)
        self.active_id = -1
        self.active_sums = np.zeros((self.sub, cfg.channels), np.float64)
        self.active_counts = np.zeros(self.sub, np.int32)
        self.q_delays = np.full(cfg.query_history, -1, np.int64)
        self.q_windows = np.zeros(cfg.query_history, np.int64)
        self.q_pos = 0
        self.event_count = 0
        self.oracle = Counter()
        self.oracle_future = {}
        for v in oracle_buckets:
            if isinstance(v, (tuple, list)):
                bid, qt = int(v[0]), int(v[1]); self.oracle[bid] += 1
                self.oracle_future.setdefault(bid, []).append(qt)
            else:
                self.oracle[int(v)] += 1
        self.actions: list[dict] = []
        self.replay_ids = np.full(cfg.replay_capacity, -1, np.int64)
        self.replay_rows = np.zeros((cfg.replay_capacity, cfg.channels), np.float32)
        self.replay_live = np.zeros(cfg.replay_capacity, np.bool_)
        self.replay_pos = 0
        self._lock = threading.RLock()
        if self.account()["charged_bytes"] > cfg.budget:
            raise MemoryError(f"charged {self.account()['charged_bytes']} > budget {cfg.budget}")

    def account(self):
        arrays = [self.base_ids, self.base_sums, self.base_counts, self.overlay_ids,
                  self.overlay_sums, self.overlay_counts, self.overlay_scores,
                  self.active_sums, self.active_counts, self.q_delays, self.q_windows,
                  self.replay_ids, self.replay_rows, self.replay_live]
        array_bytes = int(sum(a.nbytes for a in arrays))
        metadata = 4096
        snapshot_slot = array_bytes + metadata
        workspace = max(2048, self.cfg.base_width * self.cfg.channels * 8)
        return {"resident_array_bytes": array_bytes, "metadata_bytes": metadata,
                "snapshot_slots": 2, "snapshot_slot_bytes": snapshot_slot,
                "workspace_bytes": workspace,
                "charged_bytes": array_bytes + metadata + 2 * snapshot_slot + workspace,
                "budget_bytes": self.cfg.budget}

    def _base_slot(self, bid):
        return int(bid % self.base_slots)

    def _overlay_slot(self, bid):
        hits = np.flatnonzero(self.overlay_ids == bid)
        return None if len(hits) == 0 else int(hits[0])

    def _seal_active(self):
        bid = self.active_id
        if bid < 0:
            return
        slot = self._base_slot(bid)
        self.base_ids[slot] = bid
        self.base_sums[slot] = self.active_sums.sum(0)
        self.base_counts[slot] = self.active_counts.sum()
        if self.cfg.overlay_capacity and self._want_overlay(bid):
            self._install_overlay(bid, self.active_sums, self.active_counts,
                                  self._score(bid), "seal")
        self.active_sums.fill(0); self.active_counts.fill(0)

    def _score(self, bid):
        age = max(0, self.event_count // self.cfg.base_width - bid)
        if self.cfg.policy == "oracle":
            # Full query trace: rank by remaining future uses; recency breaks ties.
            future = self.oracle_future.get(bid)
            uses = self.oracle.get(bid, 0) if future is None else sum(t >= self.event_count for t in future)
            return float(uses) + bid * 1e-9
        if self.cfg.policy == "recent":
            return -float(age)
        hist = self.q_delays[self.q_delays >= 0]
        if self.cfg.policy == "online" and len(hist):
            target = hist / self.cfg.base_width
        else:
            target = np.asarray(self.cfg.catalog_delays, np.float64) / self.cfg.base_width
        return float(np.exp(-np.abs(target - age) / 2.0).sum())

    def _want_overlay(self, bid):
        if self.cfg.policy == "none":
            return False
        if self.cfg.policy == "oracle":
            return self.oracle.get(bid, 0) > 0
        return True

    def _install_overlay(self, bid, sums, counts, score, reason):
        # Scores are functions of current time/query history. Re-evaluate the
        # resident set before every admission instead of leaving stale scores.
        for j, old_bid in enumerate(self.overlay_ids):
            if old_bid >= 0:
                self.overlay_scores[j] = self._score(int(old_bid))
        old = self._overlay_slot(bid)
        if old is not None:
            idx = old
        else:
            empty = np.flatnonzero(self.overlay_ids < 0)
            idx = int(empty[0]) if len(empty) else int(np.argmin(self.overlay_scores))
            if self.overlay_ids[idx] >= 0 and score <= self.overlay_scores[idx]:
                return False
            if self.overlay_ids[idx] >= 0:
                self.actions.append({"event": self.event_count, "action": "drop",
                                     "bucket": int(self.overlay_ids[idx]), "reason": reason})
        self.overlay_ids[idx] = bid
        self.overlay_sums[idx] = sums
        self.overlay_counts[idx] = counts
        self.overlay_scores[idx] = score
        self.actions.append({"event": self.event_count, "action": "promote",
                             "bucket": int(bid), "reason": reason})
        return True

    def observe(self, row):
        with self._lock:
            row = np.asarray(row, np.float32)
            eid = self.event_count
            bid = eid // self.cfg.base_width
            if bid != self.active_id:
                self._seal_active(); self.active_id = bid
            sid = (eid % self.cfg.base_width) // self.cfg.fine_width
            self.active_sums[sid] += row
            self.active_counts[sid] += 1
            if self.cfg.replay_capacity:
                p = self.replay_pos % self.cfg.replay_capacity
                self.replay_ids[p] = eid; self.replay_rows[p] = row; self.replay_live[p] = True
                self.replay_pos += 1
            self.event_count += 1

    def observe_many(self, rows):
        for row in np.asarray(rows): self.observe(row)

    def _part(self, bid, lo, hi):
        """Return sum, count, resolution for [lo,hi) inside a base bucket."""
        b0 = bid * self.cfg.base_width
        left, right = max(lo, b0), min(hi, b0 + self.cfg.base_width)
        if right <= left: return np.zeros(self.cfg.channels), 0.0, "NONE"
        slot = self._base_slot(bid)
        if self.base_ids[slot] != bid:
            if bid == self.active_id:
                bs, bc = self.active_sums, self.active_counts
            else:
                return np.zeros(self.cfg.channels), 0.0, "UNKNOWN"
        else:
            oi = self._overlay_slot(bid)
            if oi is not None:
                bs, bc = self.overlay_sums[oi], self.overlay_counts[oi]
            elif left == b0 and right == b0 + self.cfg.base_width:
                return self.base_sums[slot].copy(), float(self.base_counts[slot]), "EXACT"
            else:
                frac = (right-left) / self.cfg.base_width
                return self.base_sums[slot] * frac, float(self.base_counts[slot]) * frac, "BASE_APPROX"
        total = np.zeros(self.cfg.channels); count = 0.0; approx = False
        for sid in range(self.sub):
            s0 = b0 + sid*self.cfg.fine_width; s1 = s0+self.cfg.fine_width
            ov = max(0, min(right,s1)-max(left,s0))
            if ov:
                frac = ov / self.cfg.fine_width
                total += bs[sid]*frac; count += float(bc[sid])*frac
                approx |= ov != self.cfg.fine_width
        return total, count, "FINE_APPROX" if approx else "EXACT"

    def query(self, delay, window, record=True):
        with self._lock:
            end = self.event_count - int(delay); start = end - int(window)
            if record:
                p = self.q_pos % self.cfg.query_history
                self.q_delays[p] = delay; self.q_windows[p] = window; self.q_pos += 1
            if start < max(0, self.event_count-self.base_slots*self.cfg.base_width) or end > self.event_count or start < 0:
                return {"status":"UNKNOWN", "value":None, "resolution":"UNKNOWN"}
            total=np.zeros(self.cfg.channels); count=0.; modes=[]
            for bid in range(start//self.cfg.base_width, (end-1)//self.cfg.base_width+1):
                s,c,m=self._part(bid,start,end)
                if m=="UNKNOWN": return {"status":"UNKNOWN","value":None,"resolution":"UNKNOWN"}
                total+=s;count+=c;modes.append(m)
            mode="EXACT" if all(m=="EXACT" for m in modes) else ("FINE_APPROX" if "FINE_APPROX" in modes else "BASE_APPROX")
            return {"status":"ANSWERED", "value":total/max(count,1e-12), "resolution":mode}

    def drop_overlay(self, bid):
        with self._lock:
            i=self._overlay_slot(bid)
            if i is None:return {"ok":False,"reason":"not_present"}
            self.overlay_ids[i]=-1;self.overlay_sums[i].fill(0);self.overlay_counts[i].fill(0);self.overlay_scores[i]=0
            self.actions.append({"event":self.event_count,"action":"drop","bucket":int(bid),"reason":"explicit"})
            return {"ok":True}

    def _replay_bucket(self,bid):
        lo=bid*self.cfg.base_width;hi=lo+self.cfg.base_width
        mask=self.replay_live&(self.replay_ids>=lo)&(self.replay_ids<hi)
        ids=self.replay_ids[mask];rows=self.replay_rows[mask]
        if len(ids)!=self.cfg.base_width or len(np.unique(ids))!=self.cfg.base_width:return None
        sums=np.zeros_like(self.active_sums);counts=np.zeros_like(self.active_counts)
        for eid,row in zip(ids,rows):
            s=(int(eid)-lo)//self.cfg.fine_width;sums[s]+=row;counts[s]+=1
        return sums,counts

    def promote_from_replay(self,bid):
        with self._lock:
            got=self._replay_bucket(bid)
            if got is None:return {"ok":False,"reason":"incomplete_replay"}
            ok=self._install_overlay(bid,*got,1e12,"replay")
            return {"ok":bool(ok),"reason":"installed" if ok else "capacity_policy"}

    def delete_event(self,eid):
        with self._lock:
            hits=np.flatnonzero(self.replay_live&(self.replay_ids==eid))
            if not len(hits):return {"ok":False,"reason":"event_not_in_replay"}
            bid=eid//self.cfg.base_width
            got=self._replay_bucket(bid)
            if got is None:return {"ok":False,"reason":"bucket_not_fully_reconstructable"}
            self.replay_live[hits[0]]=False
            rows=np.flatnonzero(self.replay_live&(self.replay_ids//self.cfg.base_width==bid))
            sums=np.zeros_like(self.active_sums);counts=np.zeros_like(self.active_counts)
            lo=bid*self.cfg.base_width
            for p in rows:
                s=(int(self.replay_ids[p])-lo)//self.cfg.fine_width;sums[s]+=self.replay_rows[p];counts[s]+=1
            slot=self._base_slot(bid);self.base_sums[slot]=sums.sum(0);self.base_counts[slot]=counts.sum()
            oi=self._overlay_slot(bid)
            if oi is not None:self.overlay_sums[oi]=sums;self.overlay_counts[oi]=counts
            self.actions.append({"event":self.event_count,"action":"delete","event_id":int(eid),"bucket":int(bid)})
            return {"ok":True}

    def state_arrays(self):
        return {k:getattr(self,k).copy() for k in ("base_ids","base_sums","base_counts","overlay_ids","overlay_sums",
                 "overlay_counts","overlay_scores","active_sums","active_counts","q_delays","q_windows",
                 "replay_ids","replay_rows","replay_live")}

    def dumps(self):
        with self._lock:
            b=BytesIO();meta={"cfg":self.cfg.__dict__,"active_id":self.active_id,"q_pos":self.q_pos,
                "event_count":self.event_count,"replay_pos":self.replay_pos,"actions":self.actions}
            np.savez(b,meta=np.array(json.dumps(meta)),**self.state_arrays());return b.getvalue()

    @classmethod
    def loads(cls,data):
        z=np.load(BytesIO(data),allow_pickle=False);meta=json.loads(str(z["meta"]))
        raw=meta["cfg"];raw["catalog_delays"]=tuple(raw["catalog_delays"]);obj=cls(Config(**raw))
        for k in z.files:
            if k!="meta":getattr(obj,k)[:]=z[k]
        for k in ("active_id","q_pos","event_count","replay_pos"):setattr(obj,k,meta[k])
        obj.actions=meta["actions"];return obj

    def save_atomic(self,path,failpoint=None):
        path=Path(path);pending=path.with_suffix(path.suffix+".pending")
        data=self.dumps();pending.write_bytes(data)
        with pending.open("rb") as f:os.fsync(f.fileno())
        if failpoint=="before_replace":raise RuntimeError("injected before_replace")
        os.replace(pending,path)
        if failpoint=="after_replace":raise RuntimeError("injected after_replace")
        return len(data)


def stream(seed,length=8192,channels=4):
    r=np.random.default_rng(seed);x=np.zeros((length,channels),np.float32);level=r.normal(0,.4,channels)
    for i in range(length):
        if i%int(r.integers(48,193))==0:level=r.normal(0,.7,channels)
        prev=x[i-1] if i else np.zeros(channels)
        x[i]=.86*prev+.14*level+r.normal(0,.12,channels)
    return x


def query_schedule(seed,length,profile,shifted=True,every=64,warmup=2432):
    r=np.random.default_rng(seed+991);out=[]
    for t in range(warmup,length+1,every):
        frac=t/length
        if profile=="stable_near": delays=[64,128,256]
        elif profile=="stable_far": delays=[1536,1792,2048]
        elif profile=="near_far_near":delays=[64,128,256] if frac<.33 or frac>.67 else [1536,1792,2048]
        elif profile=="burst":delays=[64,128] if not (.42<frac<.58) else [1024,1536,2048]
        else:delays=[64,512,1024,2048] if int(frac*8)%2==0 else [128,768,1536]
        delay=int(r.choice(delays));window=int(r.choice([32,64,128,256]))
        if shifted:delay+=7
        if t-delay-window>=0:out.append({"t":t,"delay":delay,"window":window})
    return out


def evaluate(rows,queries,cfg,oracle=()):
    store=TieredOverlayStore(cfg,oracle);details=[];qby={}
    for q in queries:qby.setdefault(q["t"],[]).append(q)
    update_ns=[];query_ns=[]
    for i,row in enumerate(rows,1):
        s=time.perf_counter_ns();store.observe(row);update_ns.append(time.perf_counter_ns()-s)
        for q in qby.get(i,[]):
            s=time.perf_counter_ns();ans=store.query(q["delay"],q["window"]);query_ns.append(time.perf_counter_ns()-s)
            lo=i-q["delay"]-q["window"];hi=i-q["delay"];truth=rows[lo:hi].mean(0)
            pred=None if ans["value"] is None else ans["value"]
            details.append({**q,"status":ans["status"],"resolution":ans["resolution"],
                "truth":truth.tolist(),"prediction":None if pred is None else pred.tolist(),
                "squared_error":None if pred is None else float(np.mean((pred-truth)**2))})
    answered=[d for d in details if d["status"]=="ANSWERED"]
    return {"coverage":len(answered)/max(1,len(details)),"mse":float(np.mean([d["squared_error"] for d in answered])) if answered else None,
            "queries":len(details),"exact_fraction":sum(d["resolution"]=="EXACT" for d in answered)/max(1,len(answered)),
            "fine_fraction":sum(d["resolution"]=="FINE_APPROX" for d in answered)/max(1,len(answered)),
            "update_p50_us":float(np.percentile(update_ns,50)/1e3),"query_p50_us":float(np.percentile(query_ns,50)/1e3) if query_ns else 0.,
            "query_p95_us":float(np.percentile(query_ns,95)/1e3) if query_ns else 0.,"ledger":store.account(),"details":details,"actions":store.actions}
