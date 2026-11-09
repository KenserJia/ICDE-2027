from pathlib import Path
import sys,json,time,threading,random,subprocess,importlib.util,platform,hashlib,os
from collections import deque
from concurrent.futures import ThreadPoolExecutor
import numpy as np
import psutil
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'src'))
from mtmemory_icde.core.joint import JointService
from mtmemory_icde.core.rpo import CheckpointCoordinator
from mtmemory_icde.core.checkpoint import TwoSlotStore
from quality import OUT,write,sha
from exact import ExactPrefix
from fault_child import value
METHODS={'fused':{},'cache32':dict(cache_capacity=32),'histogram':dict(engine='histogram'),'reference':dict(fused=False),'native':dict(engine='native')}
def loadsync():
 spec=importlib.util.spec_from_file_location('legacy_run',ROOT/'repro/round78_rq_closure/run.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m.SynchronousCoordinator

def child(job,case):
 s=JointService(**METHODS[job['method']]);s.initialize_facts(128);WARM=8192
 initial=np.asarray([value(i) for i in range(WARM)],np.float32)
 for row in initial:s.observe(row,count_ack=False)
 raw=np.empty((WARM+104000,4),np.float32);raw[:WARM]=initial;raw_n=WARM;factlog=[];audits=[]
 store=TwoSlotStore(case/'checkpoint');co=loadsync()(s,store,500) if job['mode']=='sync' else CheckpointCoordinator(s,store,500,verify_capture=False)
 co.records=deque(co.records,maxlen=4096);co.wait_records_ms=deque(co.wait_records_ms,maxlen=4096)
 proc=psutil.Process();baseline=proc.memory_info().rss;rss=[baseline];stop=threading.Event()
 def sample():
  while not stop.wait(.005):rss.append(proc.memory_info().rss)
 sampler=threading.Thread(target=sample,daemon=True);sampler.start()
 def work(worker,n,measured):
  nonlocal raw_n
  rng=np.random.default_rng(91000+job['rep']*100+worker+(0 if measured else 10000));kinds=[];lat=[];local_audit=[]
  for i in range(n):
   r=float(rng.random());key=int(rng.integers(256));delay=int(rng.choice([0,7,135,511,1023,2047,3071,3800])) if job['locality']=='hot8' else int(rng.integers(3801));width=int(rng.choice([255,511,1023]));delay=int(rng.integers(256));row=value(100000+worker*104000+i)
   kind=0 if r<job['mix']/100 else 1 if r<job['mix']/100+(1-job['mix']/100)*.8 else 2
   tick=time.perf_counter_ns()
   if kind==0:
    answer=s.query(key,delay,width,certificate=job['method']!='native')
   else:
    def mutate():
     nonlocal raw_n
     if kind==1:
      z=s.observe(row);raw[raw_n]=row;raw_n+=1
     else:
      delete=i%7==0;z=s.put_fact(key,row,delete=delete);factlog.append((s.ack_seq,key,s.version,delete,row.copy()))
     return z
    co.mutate(mutate)
   elapsed=(time.perf_counter_ns()-tick)/1e6
   if measured:
    kinds.append(kind);lat.append(elapsed)
    if kind==0 and i%97==0:local_audit.append(answer)
  return np.asarray(kinds,np.int8),np.asarray(lat),local_audit
 # Warmup is outside timing, but its writes and fact changes remain in the coherent prefix.
 work(0,4000,False);startack=s.ack_seq;cp0=co.checkpoint_count_total;bytes0=co.checkpoint_envelope_bytes_total
 bar=threading.Barrier(job['clients']+1)
 def launch(w):bar.wait();return work(w,100000//job['clients'],True)
 with ThreadPoolExecutor(max_workers=job['clients']) as pool:
  pending=[pool.submit(launch,w) for w in range(job['clients'])];tick=time.perf_counter();bar.wait();results=[p.result() for p in pending];seconds=time.perf_counter()-tick
 co.close();stop.set();sampler.join();_,image,_=store.recover();restored=JointService.loads(image)
 assert s.ack_seq==restored.ack_seq==co.durable_seq and all(np.array_equal(x,y) for x,y in zip(s._arrays().values(),restored._arrays().values())) and co.maximum_gap<=500
 oracle=ExactPrefix(raw[:raw_n]);checks=0
 for _,_,aa in results:
  for z in aa:
   h=z['history'];assert h['status']=='ANSWERED'
   if job['method']!='native':assert oracle.contains(z['lo'],z['hi'],h['value'],h['total_bound']);checks+=1
   f=z['fact'];prior=[v for v in factlog if v[0]<=z['prefix'] and v[1]==f['key']]
   if prior:
    _,key,ver,deleted,row=prior[-1];assert f['version']==ver and f['live']==(not deleted) and (deleted or np.array_equal(f['value'],row))
   else:assert f['version']==(f['key']+1 if f['key']<128 else 0)
 kinds=np.concatenate([x[0] for x in results]);lat=np.concatenate([x[1] for x in results]);stats={}
 for i,name in enumerate(['query','observe','fact']):
  x=lat[kinds==i];stats[name]={'n':len(x),'p50_ms':float(np.percentile(x,50)),'p95_ms':float(np.percentile(x,95)),'p99_ms':float(np.percentile(x,99)),'p999_ms':float(np.percentile(x,99.9)),'max_ms':float(x.max())}
 np.savez_compressed(case/'latencies.npz',kind=kinds,latency_ms=lat)
 ledger=s.account(len(image));assert ledger['within_budget'] and ledger['snapshot_fits']
 result=dict(**job,requests=len(lat),seconds=seconds,throughput_rps=len(lat)/seconds,latencies=stats,max_gap=co.maximum_gap,final_gap=s.ack_seq-co.durable_seq,mutations=s.ack_seq-startack,checkpoints=co.checkpoint_count_total-cp0,checkpoint_bytes=co.checkpoint_envelope_bytes_total-bytes0,query_certificate_checks=checks,restored_all_arrays=True,ledger=ledger,rss_start_bytes=baseline,rss_peak_bytes=max(rss),harness_raw_buffer_bytes=raw.nbytes,rss_scope='whole Python process including instrumentation, raw oracle log, executor, allocator and bounded service; sampled every5ms; not a hard bound')
 write(case/'result.json',result)

def main():
 jobs=[]
 for method in ['fused','cache32','histogram']:
  for mix in [28,95]:
   for clients in [1,8]:
    for mode in ['sync','strict']:
     for rep in range(3):jobs.append(dict(method=method,mix=mix,clients=clients,mode=mode,rep=rep,locality='random'))
 for method in ['native','reference']:
  for mode in ['sync','strict']:
   for rep in range(3):jobs.append(dict(method=method,mix=70,clients=8,mode=mode,rep=rep,locality='random'))
 for method in ['fused','cache32','histogram']:
  for mode in ['sync','strict']:
   for rep in range(3):jobs.append(dict(method=method,mix=95,clients=8,mode=mode,rep=rep,locality='hot8'))
 random.Random(71111).shuffle(jobs)
 freeze=dict(jobs=jobs,N=100000,warmup=4000,K=500,B=131072,source_hashes={str(p.relative_to(ROOT)):sha(p) for p in [Path(__file__),*list((ROOT/'src/mtmemory_icde/core').glob('*.py'))]},environment=dict(platform=platform.platform(),machine=platform.machine(),python=sys.version,numpy=np.__version__))
 p=OUT/'PERFORMANCE_FREEZE.json'
 if not p.exists():write(p,freeze)
 else:assert json.loads(p.read_text())==freeze
 records=[]
 for i,j in enumerate(jobs):
  name='-'.join(str(j[k]) for k in ['method','mix','clients','mode','rep','locality']);case=OUT/'performance'/name;case.mkdir(parents=True,exist_ok=True)
  if not (case/'result.json').exists():
   c=subprocess.run([sys.executable,str(Path(__file__)),json.dumps(j),str(case)],capture_output=True,text=True,timeout=240);(case/'stderr.txt').write_text(c.stderr);assert c.returncode==0,(name,c.stderr)
  r=json.loads((case/'result.json').read_text());records.append(r);write(OUT/'performance_records.json',records);print(i+1,len(jobs),name,round(r['throughput_rps']),flush=True)
if __name__=='__main__':
 if len(sys.argv)>1:child(json.loads(sys.argv[1]),Path(sys.argv[2]))
 else:main()
