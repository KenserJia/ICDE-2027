"""Run the MT-Memory history layer on Scotty's registered-window subset.

This is an end-to-end cross-runtime number, not a Java microbenchmark.  The
same 256-event window, 64-event slide, tumbling duplicate, deterministic value
function, event count, and output count are used by ScottyAdapter.java.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time

import numpy as np


REPO_ROOT = Path(os.environ.get("MTMEM_ICDE_ROOT", Path(__file__).resolve().parents[2]))
OVERLAY_DIR = REPO_ROOT / "repro/round71_service"
sys.path.insert(0, str(OVERLAY_DIR))
from overlay import Config, TieredOverlayStore  # noqa: E402


def values(events: int) -> np.ndarray:
    timestamp = np.arange(events, dtype=np.float64)
    scalar = np.sin(timestamp * .013) + .2*np.cos(timestamp*.003) + ((timestamp % 29)-14)*.001
    return np.stack((scalar, scalar*.5, -scalar, scalar*.25), axis=1).astype(np.float32)


def run(method: str, rows: np.ndarray, check: bool) -> dict:
    if method == "fixed_coarse64":
        cfg = Config(budget=65536, base_width=64, overlay_capacity=0, policy="none")
    elif method == "online_overlay":
        cfg = Config(budget=65536, base_width=64, overlay_capacity=16, policy="online")
    else:
        raise ValueError(method)
    store = TieredOverlayStore(cfg); prefix = np.concatenate(([0.], np.cumsum(rows[:, 0], dtype=np.float64)))
    wrong=0;max_error=0.;outputs=0;unknown=0
    started=time.perf_counter_ns()
    for end,row in enumerate(rows,1):
        store.observe(row)
        if end >= 256 and end % 64 == 0:
            copies=2 if end % 256 == 0 else 1
            for _ in range(copies):
                answer=store.query(0,256,record=False);outputs+=1
                if answer["status"]!="ANSWERED":unknown+=1;continue
                if check:
                    truth=(prefix[end]-prefix[end-256])/256
                    error=abs(float(answer["value"][0])-truth);max_error=max(max_error,error)
                    wrong += error>1e-6
    elapsed=(time.perf_counter_ns()-started)/1e9
    return {"method":method,"ordered_only":True,"events":len(rows),"elapsed_s":elapsed,
            "events_per_s":len(rows)/elapsed,"outputs":outputs,"wrong":int(wrong),
            "unknown":unknown,"max_abs_error":max_error,"account":store.account()}


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--events",type=int,default=1_000_000)
    parser.add_argument("--repeats",type=int,default=5);parser.add_argument("--out",required=True);args=parser.parse_args()
    rows=values(args.events);correctness_rows=rows[:min(len(rows),100_000)];result=[]
    for method in ("fixed_coarse64","online_overlay"):
        checked=run(method,correctness_rows,True);checked["repeat"]=-1;result.append(checked)
        for repeat in range(args.repeats):
            measured=run(method,rows,False);measured["repeat"]=repeat;result.append(measured)
    out=Path(args.out);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text("".join(json.dumps(row,sort_keys=True)+"\n" for row in result),encoding="utf-8")
    print(json.dumps({"output":str(out),"runs":len(result)},sort_keys=True))


if __name__=="__main__":main()
