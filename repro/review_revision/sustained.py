from pathlib import Path
import sys,time,json,threading
from collections import deque
from concurrent.futures import ThreadPoolExecutor
import numpy as np,psutil
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'repro/review_revision'));import performance as perf
old=perf.old
OUT=ROOT/'results/review_revision_20261104/sustained';OUT.mkdir(exist_ok=True)
rows=old.all_split_units(5)[-1][-1];raw=[]
for allocation,durability in [('fixed','sync'),('dynamic','strict')]:
 case=OUT/f'{allocation}-{durability}';case.mkdir(exist_ok=True)
 if (case/'result.json').exists():raw.append(json.loads((case/'result.json').read_text()));continue
 service=old.build_service(allocation,rows[:4160]);store=old.TwoSlotStore(case/'checkpoint')
 coordinator=old.SynchronousCoordinator(service,store,500) if durability=='sync' else perf.CheckpointCoordinator(service,store,500)
 coordinator.records=deque(coordinator.records,maxlen=4096);coordinator.wait_records_ms=deque(maxlen=4096)
 barrier=threading.Barrier(9);stop=threading.Event();counts=[0]*8;samples=[None]*8;errors=[]
 rss=deque(maxlen=1024);process=psutil.Process();baseline=process.memory_info().rss
 def worker(w):
  rng=np.random.default_rng(20261104+w*101);reservoir=np.empty(25000,np.float64);seen=0
  try:
   barrier.wait(30)
   while not stop.is_set():
    # A separate deterministic generator governs sample selection, so sampling
    # does not change the workload sequence.
    for i in range(256):
     u=rng.random();a=time.perf_counter_ns()
     if u<.58:
      row=rows[(seen*8+w)%len(rows)];coordinator.mutate(lambda row=row:service.observe(row))
     elif u<.86:service.query(w,1159+int(rng.integers(-32,33)),int(rng.choice([32,64,128,256])))
     elif u<.96:
      k=int(rng.integers(0,256));row=rows[seen%len(rows)];coordinator.mutate(lambda k=k,row=row:service.put_fact(k,row))
     elif u<.98:
      k=int(rng.integers(0,256));coordinator.mutate(lambda k=k:service.put_fact(k,np.zeros(4),delete=True))
     else:service.get_fact(int(rng.integers(0,256)))
     dt=(time.perf_counter_ns()-a)/1e6;seen+=1
     if seen<=len(reservoir):reservoir[seen-1]=dt
     else:
      j=int(sample_rng[w].integers(0,seen))
      if j<len(reservoir):reservoir[j]=dt
   counts[w]=seen;samples[w]=reservoir[:min(seen,len(reservoir))]
  except Exception as exc:errors.append(repr(exc));stop.set();raise
 sample_rng=[np.random.default_rng(411+w) for w in range(8)]
 with ThreadPoolExecutor(max_workers=8) as pool:
  fs=[pool.submit(worker,w) for w in range(8)];started=time.perf_counter();barrier.wait(30)
  while time.perf_counter()-started<120 and not stop.is_set():
   time.sleep(.2);rss.append([time.perf_counter()-started,process.memory_info().rss])
  stop.set()
  for f in fs:f.result()
 elapsed=time.perf_counter()-started;old.close_coordinator(coordinator)
 _,blob,_=store.recover();restored=old.StudyService.loads(blob)
 assert coordinator.maximum_gap<=500 and restored.ack_seq==service.ack_seq
 assert np.array_equal(restored.fact_values,service.fact_values) and np.array_equal(restored.fact_versions,service.fact_versions)
 assert np.allclose(restored.query(0,1159,64)['history']['value'],service.query(0,1159,64)['history']['value'])
 sample=np.concatenate(samples)
 weights=np.concatenate([np.full(len(samples[w]),counts[w]/len(samples[w])) for w in range(8)])
 order=np.argsort(sample);cdf=np.cumsum(weights[order]);cdf/=cdf[-1]
 dist={'count':len(sample),'estimated_requests':sum(counts),'maximum_sample':float(sample.max())}
 for key,q in [('p50',.5),('p95',.95),('p99',.99),('p99_9',.999)]:dist[key]=float(sample[order[min(len(order)-1,np.searchsorted(cdf,q))]])
 r=dict(allocation=allocation,durability=durability,seconds=elapsed,completed=sum(counts),throughput_ops_s=sum(counts)/elapsed,latency_sample_ms=dist,sampling='uniform reservoir of 25000 per worker; CDF weighted by worker_count / sample_count',worker_counts=counts,maximum_gap=coordinator.maximum_gap,restored_prefix=restored.ack_seq,final_prefix=service.ack_seq,rss_start_bytes=baseline,rss_sample_max_bytes=max(x[1] for x in rss),rss_last_20s_min_bytes=min(x[1] for x in rss if x[0]>100),rss_last_20s_max_bytes=max(x[1] for x in rss if x[0]>100),rss_samples=list(rss),account=service.account(len(blob)),telemetry_limit=4096,measurement_reservoir_bytes=8*25000*8,errors=errors)
 old.write_json(case/'result.json',r);raw.append(r);old.write_json(OUT/'raw.json',raw);print(allocation,durability,sum(counts),elapsed,flush=True)
