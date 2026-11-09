"""Paced arrivals with bounded dispatch queue; includes dispatcher/scheduler delay."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from collections import deque
import sys,threading,time,queue,random,json,hashlib
import numpy as np
from concurrency import ROOT,OUT,TLS,TracedLock,TracedCondition,DelayedStore,NoCheckpoint,dist,write,legacy,CheckpointCoordinator

def one(job):
 case=OUT/'paced_confirmation'/job['id'];case.mkdir(parents=True,exist_ok=False)
 rows=legacy.all_split_units(5)[-1][-1];s=legacy.build_service('fixed',rows[:4160]);cap=deque(maxlen=4096);s._lock=TracedLock(s._lock,cap);orig=s.dumps
 def dumps():
  prior=getattr(TLS,'capture',False);TLS.capture=True
  try:return orig()
  finally:TLS.capture=prior
 s.dumps=dumps;store=DelayedStore(case/'checkpoint');mode=job['mode']
 if mode=='strict':co=CheckpointCoordinator(s,store,500,verify_capture=False)
 elif mode=='sync':co=legacy.SynchronousCoordinator(s,store,500);co.records=deque(co.records,maxlen=4096);co.wait_records_ms=deque(maxlen=4096)
 else:co=NoCheckpoint(s)
 for i in range(2000):
  if i%4==0:s.query(0,135,63)
  else:co.mutate(lambda i=i:s.observe(rows[i%len(rows)]))
 if mode=='strict':co.force_checkpoint()
 elif mode=='sync':store.commit(s.dumps());co.durable_seq=s.ack_seq
 cap.clear();co.records.clear()
 n=job['rate']*10;rng=np.random.default_rng(9100+job['rep']);isq=rng.random(n)<job['q'];timing=np.zeros((n,5),np.int64)
 inbox=queue.Queue(maxsize=1024);barrier=threading.Barrier(job['clients']+1);start=[0]
 def worker():
  barrier.wait(30)
  while True:
   task=inbox.get()
   if task is None:inbox.task_done();return
   i,planned,enqueued=task;TLS.service_wait=0;a=time.perf_counter_ns()
   if isq[i]:s.query(i%256,135 if i%2 else 1159,[32,64,128,256][i%4])
   else:
    row=rows[i%len(rows)];co.mutate(lambda row=row:s.observe(row))
   timing[i]=[planned,enqueued,a,time.perf_counter_ns(),TLS.service_wait];inbox.task_done()
 with ThreadPoolExecutor(max_workers=job['clients']) as pool:
  fs=[pool.submit(worker) for _ in range(job['clients'])];start[0]=time.perf_counter_ns()+20_000_000;barrier.wait(30)
  # One 1ms batch. All arrivals in a batch share the scheduled arrival instant.
  batch=job['rate']//1000
  for tick in range(10000):
   planned=start[0]+tick*1_000_000;delay=(planned-time.perf_counter_ns())/1e9
   if delay>0:time.sleep(delay)
   for i in range(tick*batch,(tick+1)*batch):inbox.put((i,planned,time.perf_counter_ns()))
  inbox.join();finish=time.perf_counter_ns()
  for _ in fs:inbox.put(None)
  for f in fs:f.result()
 capture_count=len(cap)
 if mode!='none':legacy.close_coordinator(co);_,blob,_=store.recover();z=legacy.StudyService.loads(blob);assert z.ack_seq==s.ack_seq and co.maximum_gap<=500
 a=(timing[:,3]-timing[:,0])/1e6;enqueue_delay=(timing[:,1]-timing[:,0])/1e6;queue_delay=(timing[:,2]-timing[:,1])/1e6;service=(timing[:,3]-timing[:,2])/1e6
 r=dict(**job,operations=n,queries=int(isq.sum()),completed_ops_s=n/((finish-start[0])/1e9),elapsed_from_first_arrival_seconds=(finish-start[0])/1e9,query_latency_from_scheduled_ms=dist(a[isq]),query_service_ms=dist(service[isq]),query_dispatch_lateness_ms=dist(enqueue_delay[isq]),query_queue_wait_ms=dist(queue_delay[isq]),query_service_lock_wait_ms=dist(timing[isq,4]/1e6),maximum_gap=co.maximum_gap,captures=capture_count,queue_capacity=1024,arrival_batch_ms=1,restored_prefix_equal=mode!='none',scope='single-process Python bounded-queue paced diagnostic; planned-to-completion includes producer scheduling/backpressure, not network; no requests dropped')
 np.savez_compressed(case/'requests.npz',timing_ns=timing,is_query=isq,capture_windows_ns=np.asarray(cap));write(case/'result.json',r);return r

def main():
 (OUT/'paced_confirmation').mkdir(exist_ok=True);rng=random.Random(9110910);blocks=[(rep,q) for rep in range(3) for q in [.70,.95]];rng.shuffle(blocks);jobs=[]
 for rep,q in blocks:
  modes=['none','sync','strict'];rng.shuffle(modes)
  for mode in modes:jobs.append(dict(id=f'confirm10-r{rep}-q{int(q*100)}-{mode}',rep=rep,q=q,rate=60000,clients=8,mode=mode,arrival_seconds=10))
 freeze={'order':jobs,'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'purpose':'duration confirmation of two critical cells; all modes and reps retained; selected before confirmation, based on short-run scheduling variability; not a prespecified independent initial study'}
 p=OUT/'PACED_CONFIRMATION_FREEZE.json'
 if not p.exists():write(p,freeze)
 else:assert json.loads(p.read_text())==freeze
 for i,job in enumerate(jobs):
  p=OUT/'paced_confirmation'/job['id']/'result.json'
  r=json.loads(p.read_text()) if p.exists() else one(job)
  print(i+1,len(jobs),job['id'],round(r['completed_ops_s']),round(r['query_latency_from_scheduled_ms']['p99'],3),flush=True)
if __name__=='__main__':main()
