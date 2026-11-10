"""Serial sustained real-data arrivals; all layouts selected before timing."""
from pathlib import Path
import sys,json,time,threading,hashlib,random,subprocess
from collections import deque
from concurrent.futures import ThreadPoolExecutor
import numpy as np,psutil
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'src'));sys.path.insert(0,str(Path(__file__).parent));sys.path.insert(0,str(ROOT/'repro/review7_20261109'))
from mtmemory_icde.core.strong_baselines import ComparisonService
from mtmemory_icde.core.rpo import CheckpointCoordinator
from mtmemory_icde.core.checkpoint import TwoSlotStore
from application import service_at
from exact import ExactPrefix
OUT=ROOT/'results/w1w4_20261110'
def write(p,x):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,indent=2,allow_nan=False)+'\n')
def data():
 with np.load(ROOT/'data/real/household.npz') as z:
  tr,va,te=[z[f'{n}_0'] for n in ['train','validation','test']]
 return np.concatenate([tr,va,te]),len(tr)+len(va),len(tr),float(np.var(tr.astype(float),axis=0).mean())
def make_due(duration,base,burst):
 cuts=[0,120,130,420,430,duration] if duration==600 else [0,600,610,1200,1210,duration]
 return np.concatenate([a+np.arange(int((b-a)*(burst if i in [1,3] else base)))/(burst if i in [1,3] else base) for i,(a,b) in enumerate(zip(cuts,cuts[1:]))])
def child(job,choices):
 import os
 c=choices[job['method']];rows,t0,train_n,var=data();s=ComparisonService.loads((OUT/'long_initial'/f'{job["method"]}.bin').read_bytes());case=OUT/'longrun'/job['name'];case.mkdir(parents=True,exist_ok=True);write(case/'PROCESS.json',dict(pid=os.getpid()))
 co=CheckpointCoordinator(s,TwoSlotStore(case/'checkpoint'),500,verify_capture=False);due=make_due(job['duration'],job['base'],job['burst']);N=len(due);rng=np.random.default_rng(11000+job['rep']);kinds=np.where((r:=rng.random(N))<.95,0,np.where(r<.99,1,2)).astype(np.int8);delays=rng.integers(0,1,N,dtype=np.int32);widths=rng.integers(16,129,N,dtype=np.int16);panels=rng.integers(0,3,N,dtype=np.int8)
 for j,(a,z) in enumerate([(384,512),(1536,2048),(6144,8192)]):
  ix=np.flatnonzero(panels==j);delays[ix]=rng.integers(a,z+1,len(ix))-widths[ix]
 del panels
 assert (kinds==1).sum()<=len(rows)-t0,'real observations cannot cycle'
 latency=np.empty(N,np.float32);latency.fill(0);execute=latency.copy();cert=np.zeros(N,np.bool_);served=np.zeros(N,np.bool_)
 # Prefix-specific audits and controlled fact trace are measurement state outside ledger.
 fact_capacity=int((kinds==2).sum());fp=np.zeros(fact_capacity,np.int64);fk=np.zeros(fact_capacity,np.int16);fv=np.zeros(fact_capacity,np.int64);fd=np.zeros(fact_capacity,bool)
 audits=[];raw_n=t0;fact_n=0;index=0;ticket=threading.Lock();bar=threading.Barrier(9);start=[0.];counts=[0]*8;stop=threading.Event();telemetry=[];proc=psutil.Process();errors=[]
 def worker(wid):
  nonlocal index,raw_n,fact_n
  local=[];bar.wait()
  while True:
   with ticket:i=index;index+=1
   if i>=N:break
   wait=start[0]+due[i]-time.perf_counter()
   if wait>0:time.sleep(wait)
   tick=time.perf_counter()
   if kinds[i]==0:
    answer=s.query(i%256,int(delays[i]),int(widths[i]));h=answer['history'];assert h['status']=='ANSWERED';isgood=np.sqrt(np.mean(h['total_bound']**2)/var)<=.1
    if i%10007==0:local.append(answer)
   else:
    def mutate():
     nonlocal raw_n,fact_n
     if kinds[i]==1:
      out=s.observe(rows[raw_n]);raw_n+=1;return out
     deleted=i%7==0;out=s.put_fact(i%256,rows[i%train_n],delete=deleted);fp[fact_n]=s.ack_seq;fk[fact_n]=i%256;fv[fact_n]=s.version;fd[fact_n]=deleted;fact_n+=1;return out
    co.mutate(mutate);isgood=False
   done=time.perf_counter();latency[i]=(done-start[0]-due[i])*1000;execute[i]=(done-tick)*1000;cert[i]=isgood;served[i]=True;counts[wid]+=1
  return local
 def monitor():
  last=0;minute=0
  while not stop.wait(1):
   elapsed=time.perf_counter()-start[0];finished=sum(counts);arrived=int(np.searchsorted(due,elapsed,side='right'));gap=int(s.ack_seq)-int(co.durable_seq)
   telemetry.append(dict(seconds=elapsed,completed=finished,arrived=arrived,backlog=max(0,arrived-finished),gap=gap,rss=proc.memory_info().rss,checkpoints=co.checkpoint_count_total))
   if elapsed//60>minute:
    minute=int(elapsed//60);ix=np.flatnonzero(served&(np.arange(N)>=last));q=ix[kinds[ix]==0]
    msg=dict(minute=minute,elapsed=round(elapsed,1),completed=finished,backlog=max(0,arrived-finished),query_p99_ms=float(np.percentile(latency[q],99)) if len(q) else None,certified_20ms=int(np.count_nonzero(cert[ix]&(latency[ix]<=20))),rss_mib=proc.memory_info().rss/2**20,max_gap=co.maximum_gap)
    with (case/'progress.jsonl').open('a') as f:f.write(json.dumps(msg)+'\n')
    print('PROGRESS',job['name'],json.dumps(msg),flush=True);last=index
 with ThreadPoolExecutor(max_workers=8) as pool:
  tasks=[pool.submit(worker,w) for w in range(8)];start[0]=time.perf_counter();monitor_thread=threading.Thread(target=monitor,daemon=True);monitor_thread.start();bar.wait();audits=[a for f in tasks for a in f.result()];elapsed=time.perf_counter()-start[0]
 stop.set();monitor_thread.join();cp_start=time.perf_counter();co.close();drain=time.perf_counter()-cp_start;_,blob,_=co.store.recover();restored=ComparisonService.loads(blob)
 assert served.all() and co.maximum_gap<=500 and s.ack_seq==restored.ack_seq==co.durable_seq
 assert all(np.array_equal(x,y) for x,y in zip(s._arrays().values(),restored._arrays().values()))
 checks=0
 for a in audits:
  lo,hi=a['lo'],a['hi'];oracle=ExactPrefix(rows[lo:hi]);h=a['history'];assert oracle.contains(0,hi-lo,h['value'],h['total_bound']);f=a['fact'];ids=np.flatnonzero((fp[:fact_n]<=a['prefix'])&(fk[:fact_n]==f['key']))
  if len(ids):j=ids[-1];assert f['version']==fv[j] and f['live']==(not fd[j])
  else:assert f['version']==(f['key']+1 if f['key']<128 else 0)
  checks+=1
 q=kinds==0;good=cert&q;account=s.account(len(blob));assert account['within_budget'] and account['snapshot_fits']
 result=dict(**job,requests=N,seconds=elapsed,queries=int(q.sum()),observations=raw_n-t0,source_cycles=0,throughput=N/elapsed,G01=float(good[q].mean()),certified_goodput=int(good.sum())/elapsed,timely_goodput_20ms=int(np.count_nonzero(good&(latency<=20)))/elapsed,scheduled_query_p99_ms=float(np.percentile(latency[q],99)),scheduled_query_p999_ms=float(np.percentile(latency[q],99.9)),execute_query_p99_ms=float(np.percentile(execute[q],99)),max_gap=co.maximum_gap,max_backlog=max(x['backlog'] for x in telemetry),final_image_restored=True,exact_oracle_checks=checks,account=account,checkpoint_drain_seconds=drain,initial_rss_mib=telemetry[0]['rss']/2**20,last_rss_mib=telemetry[-1]['rss']/2**20,max_rss_mib=max(x['rss'] for x in telemetry)/2**20,telemetry_scope='whole process including preallocated bounded-duration measurement arrays; logical ledger is not RAM cap')
 write(case/'result.json',result);write(case/'telemetry.json',telemetry);np.savez_compressed(case/'requests.npz',kind=kinds,scheduled_latency_ms=latency,execution_latency_ms=execute,certified=cert)
 print('COMPLETE',job['name'],json.dumps(result),flush=True)
def main():
 assert (OUT/'EXACT_AUDIT.json').exists(),'finish quality and live/oracle audit before timing'
 sel=json.loads((OUT/'SELECTIONS.json').read_text());pool=[r for r in sel if r['dataset']=='household' and r['B']==262144 and r['objective']=='g01'];native=next(r for r in pool if r['variant']=='recent');baseline=max([r for r in pool if r['variant']!='recent'],key=lambda r:(r['metrics']['G']['0.1'],-r['config']['ledger']['charged_bytes']))
 choices={'recent':native['config'],'strong':baseline['config']};rows,t,_,_=data();initial=OUT/'long_initial';initial.mkdir(exist_ok=True)
 for name,c in choices.items():
  p=initial/f'{name}.bin'
  if not p.exists():p.write_bytes(service_at(c,rows,t).dumps())
 if (OUT/'PILOT.json').exists():
  pp=json.loads((OUT/'PILOT.json').read_text());base=pp['base'];burst=pp['burst']
 else:
  pilot=[]
  for name,c in choices.items():
   dest=OUT/'pilot'/name;dest.mkdir(parents=True,exist_ok=True);service=service_at(c,rows,t-2048);co=CheckpointCoordinator(service,TwoSlotStore(dest/'checkpoint'),500,verify_capture=False);rng=np.random.default_rng(9911);observed=0;tick=time.perf_counter()
   for i in range(10000):
    r=float(rng.random())
    if r<.95:service.query(i%256,int(rng.integers(256,3801)),int(rng.integers(16,129)))
    elif r<.99:
     co.mutate(lambda:service.observe(rows[t-2048+observed]));observed+=1
    else:co.mutate(lambda:service.put_fact(i%256,rows[i]))
   seconds=time.perf_counter()-tick;co.close();pilot.append(dict(method=name,requests=10000,seconds=seconds,rps=10000/seconds,validation_observations=observed))
  base=min(8000,max(100,int(.3*min(x['rps'] for x in pilot))))
  burst=min(40000,max(base*2,int(1.2*max(x['rps'] for x in pilot))))
  write(OUT/'PILOT.json',dict(records=pilot,base=base,burst=burst,selection='pilot validation data; capped to avoid cycling test data; not a capacity guarantee'))
 jobs=[dict(method=m,rep=r,duration=600,base=base,burst=burst,name=f'{m}-r{r}-10min') for m in choices for r in range(3)]
 random.Random(20261110).shuffle(jobs);jobs.append(dict(method='recent',rep=3,duration=1800,base=min(4000,base),burst=min(20000,burst),name='recent-30min'))
 protocol=dict(choices=choices,baseline_selection='highest household validation G(.1) among SSE/bound/fixed',K=500,budget=262144,R=16384,clients=8,query_fraction=.95,observation_fraction=.04,fact_fraction=.01,jobs=jobs,scope='six10min matched runs and one30min descriptive run, fixed load and two10s bursts, no capacity optimum or productionSLO claim',source={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__),ROOT/'src/mtmemory_icde/core/strong_baselines.py']})
 p=OUT/'LONG_PROTOCOL.json'
 if p.exists():assert json.loads(p.read_text())==protocol
 else:write(p,protocol)
 for i,j in enumerate(jobs):
  case=OUT/'longrun'/j['name'];case.mkdir(parents=True,exist_ok=True)
  if not (case/'result.json').exists():
   if (case/'checkpoint').exists():
    import shutil
    shutil.move(str(case),str(case)+'-failed-'+str(time.time_ns()));case.mkdir(parents=True)
   print('START',i+1,len(jobs),j['name'],flush=True)
   with (case/'stdout.txt').open('w') as out,(case/'stderr.txt').open('w') as err:
    result=subprocess.run([sys.executable,str(Path(__file__)),json.dumps(j)],stdout=out,stderr=err,timeout=j['duration']+600);assert result.returncode==0,(j,(case/'stderr.txt').read_text())
  print('CASE',i+1,len(jobs),j['name'],flush=True)
 write(OUT/'long_records.json',[json.loads((OUT/'longrun'/j['name']/'result.json').read_text()) for j in jobs]);print('ALL LONG RUNS COMPLETE',flush=True)
if __name__=='__main__':
 if len(sys.argv)>1:child(json.loads(sys.argv[1]),json.loads((OUT/'LONG_PROTOCOL.json').read_text())['choices'])
 else:main()
