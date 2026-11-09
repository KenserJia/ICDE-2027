from pathlib import Path
import sys,json,time,threading,argparse,hashlib
from concurrent.futures import ThreadPoolExecutor
from collections import defaultdict
import numpy as np,psutil
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'src'));sys.path.insert(0,str(ROOT/'repro/round78_rq_closure'))
import run as old
from mtmemory_icde.core.rpo import CheckpointCoordinator
OUT=ROOT/'results/review_revision_20261104'
TLS=threading.local()
class TimedLock:
 def __init__(self,base):self.base=base
 def __enter__(self):
  a=time.perf_counter_ns();self.base.acquire();b=time.perf_counter_ns()
  if hasattr(TLS,'wait_ns'):TLS.wait_ns+=b-a
  return self
 def __exit__(self,*args):self.base.release()
class TimedCondition(threading.Condition):
 def __enter__(self):
  a=time.perf_counter_ns();r=super().__enter__()
  if hasattr(TLS,'entry_ns'):TLS.entry_ns+=time.perf_counter_ns()-a
  return r
 def wait(self,timeout=None):
  a=time.perf_counter_ns();r=super().wait(timeout)
  if hasattr(TLS,'admission_ns'):TLS.admission_ns+=time.perf_counter_ns()-a
  return r

def one(case,rows,spec,allocation,durability,seed,clients,operations,diagnostic=False,verify=True):
 case.mkdir(parents=True,exist_ok=False)
 service=old.build_service(allocation,rows[:4160]);store=old.TwoSlotStore(case/'checkpoint')
 if diagnostic:service._lock=TimedLock(service._lock)
 if durability=='sync':coordinator=old.SynchronousCoordinator(service,store,500)
 else:
  coordinator=CheckpointCoordinator(service,store,500,verify_capture=verify)
  if diagnostic:
   # Replace before requests. Worker is parked on the original condition; wake
   # and stop it, then start the identical loop on a timed condition.
   with coordinator._cv:coordinator._stop=True;coordinator._cv.notify_all()
   coordinator.thread.join(30);coordinator._stop=False
   coordinator._cv=TimedCondition(threading.RLock())
   coordinator.thread=threading.Thread(target=coordinator._checkpoint_loop,daemon=True);coordinator.thread.start()
 # Fixed warmup uses the same allocation but is excluded from reported requests.
 for i in range(20000):
  if i%4==0:service.query(i%256,128 if i%8==0 else 1159,64)
  else:coordinator.mutate(lambda i=i:service.observe(rows[i%len(rows)]))
 if durability=='sync':
  # Bring warmup prefix to disk without stopping the coordinator.
  with coordinator.lock:
   rec=store.commit(service.dumps());coordinator.durable_seq=int(service.ack_seq)
 else:coordinator.force_checkpoint()
 start_ack=int(service.ack_seq);base_bytes=int(coordinator.checkpoint_envelope_bytes_total)
 coordinator.maximum_gap=0
 if hasattr(coordinator.records,'clear'):coordinator.records.clear()
 coordinator.wait_records_ms.clear()
 n=(operations//clients)*clients;per=n//clients
 latency=np.empty(n,np.float64);kinds=np.empty(n,np.uint8)
 detail=np.zeros((n,3),np.float64) if diagnostic else None
 errors=[];barrier=threading.Barrier(clients+1);done=threading.Event();rss=[]
 def sample():
  process=psutil.Process()
  while not done.wait(.2):rss.append([time.perf_counter(),process.memory_info().rss])
 sampler=threading.Thread(target=sample,daemon=True)
 rss_start=psutil.Process().memory_info().rss
 def worker(w):
  rng=np.random.default_rng(seed+w*101);u=rng.random(per);keys=rng.integers(0,256,per)
  windows=rng.choice([32,64,128,256],per);jitter=rng.integers(-spec['width_buckets']*32,spec['width_buckets']*32+1,per)
  # Request generation precedes the timed barrier and is charged to harness RSS.
  barrier.wait(timeout=60)
  try:
   for i in range(per):
    ix=w*per+i;v=u[i]
    if diagnostic:TLS.wait_ns=0;TLS.entry_ns=0;TLS.admission_ns=0
    a=time.perf_counter_ns()
    if v<.58:
     row=rows[(i*clients+w)%len(rows)];coordinator.mutate(lambda row=row:service.observe(row));kind=0
    elif v<.86:
     qi=i+w*per;dwell=spec['dwell_queries'];shift=spec['shift_buckets']*64
     far=shift>0 and (dwell==0 or (qi//max(1,dwell))%2==0)
     delay=max(7,min(4096-int(windows[i])-1,128+(shift if far else 0)+int(jitter[i])+7))
     service.query(w%256,delay,int(windows[i]));kind=1
    elif v<.96:
     key=int(keys[i]);row=rows[(i+w)%len(rows)];coordinator.mutate(lambda key=key,row=row:service.put_fact(key,row));kind=2
    elif v<.98:
     key=int(keys[i]);coordinator.mutate(lambda key=key:service.put_fact(key,np.zeros(4),delete=True));kind=3
    else:service.get_fact(int(keys[i]));kind=4
    latency[ix]=(time.perf_counter_ns()-a)/1e6;kinds[ix]=kind
    if diagnostic:detail[ix]=[TLS.entry_ns/1e6,TLS.admission_ns/1e6,TLS.wait_ns/1e6]
  except Exception as exc:errors.append(repr(exc));raise
 with ThreadPoolExecutor(max_workers=clients) as pool:
  futures=[pool.submit(worker,w) for w in range(clients)]
  sampler.start();started=time.perf_counter();barrier.wait(timeout=60)
  for f in futures:f.result()
  active=time.perf_counter()-started
 drain_start=time.perf_counter();old.close_coordinator(coordinator);drain=time.perf_counter()-drain_start
 done.set();sampler.join();_,blob,_=store.recover();restored=old.StudyService.loads(blob)
 after=service.query(0,1159,64,record=False);again=restored.query(0,1159,64,record=False)
 assert np.allclose(after['history']['value'],again['history']['value'])
 assert restored.ack_seq==service.ack_seq and coordinator.maximum_gap<=500
 fact_equal=bool(np.array_equal(service.fact_versions,restored.fact_versions) and np.array_equal(service.fact_live,restored.fact_live) and np.array_equal(service.fact_values,restored.fact_values))
 assert fact_equal
 def dist(x):return old.distribution(np.asarray(x).tolist())
 account=service.account(len(blob));assert account['within_budget']
 recs=list(coordinator.records)
 result=dict(allocation=allocation,durability=durability,verify_capture=verify,diagnostic=diagnostic,seed=seed,clients=clients,operations=n,active_seconds=active,drain_seconds=drain,throughput_ops_s=n/active,latency_ms=dist(latency),by_operation={},maximum_gap=coordinator.maximum_gap,restored_prefix=restored.ack_seq,final_prefix=service.ack_seq,fact_roundtrip=fact_equal,history_roundtrip=True,account=account,rss_start_bytes=rss_start,rss_peak_bytes=max([rss_start]+[r[1] for r in rss]),rss_end_bytes=psutil.Process().memory_info().rss,request_generation_array_bytes=32*n,measurement_array_bytes=int(latency.nbytes+kinds.nbytes+(0 if detail is None else detail.nbytes)),checkpoint_records_retained=len(recs),errors=errors)
 for k,name in enumerate(['observe','history_query','put','delete','fact_read']):result['by_operation'][name]=dist(latency[kinds==k])
 result['checkpoint_phases_ms']={key:dist([r[key] for r in recs if key in r]) for key in ['capture_ms','validation_ms','persist_ms','total_ms']}
 if diagnostic:
  slow=latency>=np.percentile(latency,99.9)
  result['request_wait_ms']={name:dist(detail[:,j]) for j,name in enumerate(['coordinator_entry','condition_wait','service_lock_wait'])}
  result['slowest_0_1pct_mean_ms']={name:float(np.mean(detail[slow,j])) for j,name in enumerate(['coordinator_entry','condition_wait','service_lock_wait'])}
  result['slowest_0_1pct_mean_ms']['latency']=float(np.mean(latency[slow]))
 # Measurement vectors and telemetry are bounded by this protocol, outside ledger.
 result['checkpoint_bytes_per_measured_mutation']=(coordinator.checkpoint_envelope_bytes_total-base_bytes)/max(1,service.ack_seq-start_ack)
 old.write_json(case/'result.json',result);return result

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--mode',choices=['long','diagnostic','scaling'],required=True);parser.add_argument('--operations',type=int);args=parser.parse_args()
 OUT.mkdir(exist_ok=True);old.write_json(OUT/'environment.json',old.environment())
 frozen=json.loads((ROOT/'results/frozen/rq_closure/rq3_boundary/RQ3_FREEZE.json').read_text())['workloads'];rows=old.all_split_units(5)[-1][-1];raw=[]
 if args.mode=='long':jobs=[(label,choice['spec'],a,d,seed,8,False,True) for seed in (0,1,2) for label,choice in frozen.items() for a in ('fixed','dynamic') for d in ('sync','strict')]
 elif args.mode=='diagnostic':jobs=[('dynamic_dominant',frozen['dynamic_dominant']['spec'],a,d,seed,8,True,verify) for seed in (0,1,2) for a,d,verify in [('fixed','sync',True),('dynamic','sync',True),('dynamic','strict',True),('dynamic','strict',False)]]
 else:jobs=[('dynamic_dominant',frozen['dynamic_dominant']['spec'],a,'sync',seed,c,False,True) for seed in (0,1,2) for c in (1,16) for a in ('fixed','dynamic')]
 # Randomize cells within a recorded, deterministic execution order.
 rng=np.random.default_rng(20261104);rng.shuffle(jobs)
 root=OUT/args.mode;root.mkdir(exist_ok=True)
 for ji,(label,spec,a,d,seed,clients,diagnostic,verify) in enumerate(jobs):
  name=f'{label}-{a}-{d}-s{seed}-c{clients}-verify{int(verify)}';case=root/name
  if (case/'result.json').exists():r=json.loads((case/'result.json').read_text())
  else:r=one(case,rows,spec,a,d,20261104+seed*211,clients,args.operations or (1000000 if args.mode=='long' else 250000),diagnostic,verify)
  r['workload']=label;raw.append(r);old.write_json(root/'raw.json',raw)
  print(ji+1,len(jobs),name,round(r['throughput_ops_s']),round(r['latency_ms']['p99_9'],3),flush=True)
 print('COMPLETE',args.mode,flush=True)
if __name__=='__main__':main()
