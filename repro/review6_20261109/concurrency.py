"""Mixed-load diagnostic. Production service/coordinator are unchanged."""
from pathlib import Path
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
import argparse, json, sys, threading, time, types, random
import numpy as np
import psutil
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'src'))
sys.path.insert(0,str(ROOT/'repro/round78_rq_closure'))
import run as legacy
from mtmemory_icde.core.rpo import CheckpointCoordinator
from mtmemory_icde.core.checkpoint import TwoSlotStore
OUT=ROOT/'results/review6_20261109'; TLS=threading.local()
def write(p,x):p.write_text(json.dumps(x,indent=2,allow_nan=False)+'\n')
def dist(a):
 a=np.asarray(a,dtype=float)
 return {'n':len(a),**({k:float(np.quantile(a,v)) for k,v in [('p50',.5),('p95',.95),('p99',.99),('p99_9',.999)]} if len(a) else {}),'mean':float(a.mean()) if len(a) else None,'max':float(a.max()) if len(a) else None}
class TracedLock:
 def __init__(self,base,windows):self.base=base;self.windows=windows;self.local=threading.local()
 def __enter__(self):
  a=time.perf_counter_ns();self.base.acquire();b=time.perf_counter_ns()
  if hasattr(TLS,'service_wait'):TLS.service_wait+=b-a
  depth=getattr(self.local,'depth',0)
  if depth==0:self.local.start=b;self.local.capture=getattr(TLS,'capture',False)
  self.local.depth=depth+1
  return self
 def __exit__(self,*args):
  self.local.depth-=1
  if self.local.depth==0 and self.local.capture:self.windows.append((self.local.start,time.perf_counter_ns()))
  self.base.release()
class TracedCondition(threading.Condition):
 def __enter__(self):
  a=time.perf_counter_ns();r=super().__enter__()
  if hasattr(TLS,'cv_entry'):TLS.cv_entry+=time.perf_counter_ns()-a
  return r
 def wait(self,timeout=None):
  a=time.perf_counter_ns();r=super().wait(timeout)
  if hasattr(TLS,'gate_wait'):TLS.gate_wait+=time.perf_counter_ns()-a
  return r
class DelayedStore(TwoSlotStore):
 def __init__(self,directory,delay_ms=0):super().__init__(directory);self.delay_ms=delay_ms;self.persist_windows=deque(maxlen=4096)
 def commit(self,payload,*args,**kwargs):
  a=time.perf_counter_ns()
  if self.delay_ms:time.sleep(self.delay_ms/1000)
  r=super().commit(payload,*args,**kwargs)
  self.persist_windows.append((a,time.perf_counter_ns()));return r
class NoCheckpoint:
 def __init__(self,service):self.service=service;self.maximum_gap=None;self.records=[];self.durable_seq=0
 def mutate(self,fn):return fn()
 def close(self,*a,**kw):pass

def overlap(start,end,windows):
 result=np.zeros(len(start),bool)
 for lo,hi in windows:result|=(start<hi)&(end>lo)
 return result

def one(job,operations=120000):
 case=OUT/'concurrency'/job['id'];case.mkdir(parents=True,exist_ok=False)
 rows=legacy.all_split_units(5)[-1][-1];service=legacy.build_service(job['policy'],rows[:4160])
 capture_windows=deque(maxlen=4096);capture_durations=deque(maxlen=4096)
 original_dump=service.dumps
 def dumps():
  prior=getattr(TLS,'capture',False);TLS.capture=True;a=time.perf_counter_ns()
  try:return original_dump()
  finally:TLS.capture=prior;capture_durations.append((time.perf_counter_ns()-a)/1e6)
 service.dumps=dumps
 if job['instrument']:service._lock=TracedLock(service._lock,capture_windows)
 store=DelayedStore(case/'checkpoint',job['delay_ms']);mode=job['mode'];K=job['K']
 if mode=='sync':
  coordinator=legacy.SynchronousCoordinator(service,store,K)
  # Bound telemetry in the harness as in the current strict coordinator.
  coordinator.records=deque(coordinator.records,maxlen=4096);coordinator.wait_records_ms=deque(maxlen=4096)
 elif mode=='strict':
  coordinator=CheckpointCoordinator(service,store,K,verify_capture=False)
  if job['instrument']:
   with coordinator._cv:coordinator._stop=True;coordinator._cv.notify_all()
   coordinator.thread.join(30);assert not coordinator.thread.is_alive();coordinator._stop=False
   coordinator._cv=TracedCondition(threading.RLock());coordinator.thread=threading.Thread(target=coordinator._checkpoint_loop,name='checkpoint',daemon=True);coordinator.thread.start()
 else:coordinator=NoCheckpoint(service)
 for i in range(4000):
  if i%4==0:service.query(i%256,1159,64)
  else:coordinator.mutate(lambda i=i:service.observe(rows[i%len(rows)]))
 if mode=='strict':coordinator.force_checkpoint()
 elif mode=='sync':
  with coordinator.lock:store.commit(service.dumps());coordinator.durable_seq=service.ack_seq
 capture_windows.clear();capture_durations.clear();store.persist_windows.clear();coordinator.records.clear()
 if hasattr(coordinator,'wait_records_ms'):coordinator.wait_records_ms.clear()
 if mode!='none':coordinator.maximum_gap=0
 n=operations//job['clients']*job['clients'];per=n//job['clients']
 # start,end and all phase durations are nanoseconds. Harness buffers are excluded from ledger.
 timing=np.zeros((n,5),np.int64);kinds=np.empty(n,np.uint8)
 barrier=threading.Barrier(job['clients']+1);done=threading.Event();rss=[]
 def sample():
  process=psutil.Process()
  while not done.wait(.05):rss.append(process.memory_info().rss)
 def worker(w):
  rng=np.random.default_rng(20261109+job['rep']*1001+w*101)
  u=rng.random(per);sub=rng.random(per);keys=rng.integers(0,256,per);windows=rng.choice([32,64,128,256],per)
  # Same per-client request sequence for all modes in a block. No coordinated omission correction.
  barrier.wait(60)
  for i in range(per):
   ix=w*per+i
   if job['instrument']:TLS.service_wait=0;TLS.cv_entry=0;TLS.gate_wait=0
   a=time.perf_counter_ns()
   if u[i]<job['query_mix']:
    # near/far panels are both in reach, with shifted boundaries.
    d=135 if i%2==0 else 1159
    service.query(int(keys[i]),d,int(windows[i]));kind=1
   elif sub[i]<.82:
    row=rows[(i*job['clients']+w)%len(rows)];coordinator.mutate(lambda row=row:service.observe(row));kind=0
   else:
    key=int(keys[i]);row=rows[(i+w)%len(rows)];delete=sub[i]>.97
    coordinator.mutate(lambda key=key,row=row,delete=delete:service.put_fact(key,row,delete=delete));kind=2
   b=time.perf_counter_ns();timing[ix,:2]=(a,b);kinds[ix]=kind
   if job['instrument']:timing[ix,2:]=(TLS.service_wait,TLS.cv_entry,TLS.gate_wait)
 sampler=threading.Thread(target=sample,daemon=True)
 rss_start=psutil.Process().memory_info().rss
 with ThreadPoolExecutor(max_workers=job['clients']) as pool:
  fs=[pool.submit(worker,w) for w in range(job['clients'])];sampler.start();begin=time.perf_counter_ns();barrier.wait(60)
  for f in fs:f.result()
  finish=time.perf_counter_ns()
 active_end_prefix=service.ack_seq;active_cp=len(capture_durations);active_capture=list(capture_windows);active_persist=list(store.persist_windows);active_rec=list(coordinator.records);active_duration=list(capture_durations)
 a=time.perf_counter();
 if mode!='none':legacy.close_coordinator(coordinator)
 drain=time.perf_counter()-a;done.set();sampler.join()
 prefix_ok=fact_ok=history_ok=None;account=None
 if mode!='none':
  _,blob,_=store.recover();restored=legacy.StudyService.loads(blob)
  prefix_ok=restored.ack_seq==service.ack_seq
  fact_ok=all(np.array_equal(getattr(restored,n),getattr(service,n)) for n in ['fact_values','fact_versions','fact_live'])
  history_ok=all(np.array_equal(a,b) for a,b in zip(restored.history.state_arrays().values(),service.history.state_arrays().values()))
  assert prefix_ok and fact_ok and history_ok and coordinator.maximum_gap<=K
  account=service.account(len(blob));assert account['within_budget']
 latency=(timing[:,1]-timing[:,0])/1e6;query=kinds==1;capture_overlap=overlap(timing[:,0],timing[:,1],active_capture);persist_overlap=overlap(timing[:,0],timing[:,1],active_persist)
 groups={'all':np.ones(n,bool),'query':query,'mutation':~query,'query_capture_overlap':query&capture_overlap,'query_no_capture_overlap':query&~capture_overlap,'query_persist_overlap_without_capture':query&persist_overlap&~capture_overlap}
 metrics={}
 for name,mask in groups.items():
  metrics[name]={'latency_ms':dist(latency[mask])}
  if job['instrument']:
   metrics[name].update({label:dist(timing[mask,j]/1e6) for j,label in [(2,'service_lock_wait_ms'),(3,'coordinator_entry_ms'),(4,'gate_condition_wait_ms')]})
 # All phase wait metrics may include scheduler descheduling, not just CPU execution.
 cp_phases={key:dist([r[key] for r in active_rec if key in r]) for key in ['capture_ms','persist_ms','total_ms']}
 result=dict(**job,operations=n,queries=int(query.sum()),mutations=int((~query).sum()),measured_query_fraction=float(query.mean()),active_seconds=(finish-begin)/1e9,throughput_ops_s=n/((finish-begin)/1e9),metrics=metrics,checkpoint_captures=active_cp,capture_wall_ms=dist(active_duration),checkpoint_phases_ms=cp_phases,query_capture_overlap_fraction=float(capture_overlap[query].mean()),capture_lock_time_fraction=sum(b-a for a,b in active_capture)/(finish-begin),maximum_gap=coordinator.maximum_gap,active_end_prefix=active_end_prefix,restored_prefix_equal=prefix_ok,facts_equal=fact_ok,history_arrays_equal=history_ok,ledger=account,drain_seconds=drain,rss_start=rss_start,rss_peak=max([rss_start]+rss),harness_measurement_array_bytes=timing.nbytes+kinds.nbytes,uncontrolled='OS scheduling, Python GIL, local fsync, client interleaving; closed-loop clients')
 np.savez_compressed(case/'requests.npz',timing_ns=timing,kind=kinds,capture_windows_ns=np.asarray(active_capture,dtype=np.int64),persist_windows_ns=np.asarray(active_persist,dtype=np.int64))
 write(case/'result.json',result);return result

def jobs():
 blocks=[]
 for rep in range(3):
  for q in [.28,.70,.95]:
   for c in [1,8,16]:blocks.append(('main',rep,q,c,0,500,'fixed',True,['none','sync','strict']))
  for q in [.28,.95]:blocks.append(('storage',rep,q,8,5,500,'fixed',True,['sync','strict']))
  for k in [125,2000]:blocks.append(('K',rep,.70,8,0,k,'fixed',True,['sync','strict']))
  blocks.append(('policy',rep,.70,8,0,500,'dynamic',True,['none','sync','strict']))
  blocks.append(('instrumentation',rep,.70,8,0,500,'fixed',False,['sync','strict']))
 rng=random.Random(20261109);rng.shuffle(blocks);out=[]
 for group,rep,q,c,delay,k,p,ins,modes in blocks:
  rng.shuffle(modes)
  for mode in modes:
   name=f'{group}-r{rep}-q{int(q*100)}-c{c}-d{delay}-K{k}-{p}-{mode}-i{int(ins)}'
   out.append(dict(id=name,group=group,rep=rep,query_mix=q,clients=c,delay_ms=delay,K=k,policy=p,instrument=ins,mode=mode))
 return out

def main():
 a=argparse.ArgumentParser();a.add_argument('--operations',type=int,default=120000);a.add_argument('--pilot',action='store_true');args=a.parse_args()
 OUT.mkdir(exist_ok=True);(OUT/'concurrency').mkdir(exist_ok=True)
 js=jobs()
 if args.pilot:js=[dict(js[0],id='pilot',clients=8,query_mix=.70,mode='strict',group='pilot')]
 freeze=OUT/('CONCURRENCY_PILOT.json' if args.pilot else 'CONCURRENCY_FREEZE.json')
 import hashlib
 packet={'operations':args.operations,'order':js,'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'time':legacy.environment()}
 if not freeze.exists():write(freeze,packet)
 else:assert json.loads(freeze.read_text())['source_sha256']==packet['source_sha256']
 for i,job in enumerate(js):
  dest=OUT/'concurrency'/job['id']/'result.json'
  if dest.exists():r=json.loads(dest.read_text())
  else:r=one(job,args.operations)
  print(f"{i+1}/{len(js)} {job['id']} {r['throughput_ops_s']:.0f} ops/s query p99={r['metrics']['query']['latency_ms']['p99']:.3f}ms capture={r['checkpoint_captures']}",flush=True)
if __name__=='__main__':main()
