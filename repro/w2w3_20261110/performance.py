"""Real-data joint goodput, with configurations frozen by validation in quality.py.

Timing cases run serially in isolated subprocesses. No test result selects a layout.
"""
from pathlib import Path
import sys,json,time,threading,hashlib,random,subprocess,importlib.util,platform
from collections import deque
from concurrent.futures import ThreadPoolExecutor
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'src'));sys.path.insert(0,str(ROOT/'repro/review7_20261109'))
from mtmemory_icde.core.joint import JointService
from mtmemory_icde.core.rpo import CheckpointCoordinator
from mtmemory_icde.core.checkpoint import TwoSlotStore
from exact import ExactPrefix
OUT=ROOT/'results/w2w3_20261110'
def write(path,x):path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(x,indent=2,allow_nan=False)+'\n')
def sync_class():
 spec=importlib.util.spec_from_file_location('synchronous_protocol',ROOT/'repro/round78_rq_closure/run.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m.SynchronousCoordinator
def unit(ui):
 ds,e=('bike',0) if ui==0 else ('beijing',0)
 with np.load(ROOT/f'data/real/{ds}.npz') as z:return ds,e,*[z[f'{name}_{e}'].astype(np.float32) for name in ['train','validation','test']]
def prepare(configs):
 for cid,chosen in configs.items():
  path=OUT/'initial_images'/f'{cid}.bin'
  if path.exists():continue
  ds,e,tr,va,te=unit(chosen['unit']);s=JointService(**chosen['config']['options']);s.initialize_facts(128)
  for row in np.concatenate([tr,va]):s.observe(row,count_ack=False)
  path.parent.mkdir(exist_ok=True);blob=s.dumps();restored=JointService.loads(blob)
  assert all(np.array_equal(x,y) for x,y in zip(s._arrays().values(),restored._arrays().values()))
  path.write_bytes(blob);write(path.with_suffix('.json'),dict(config=chosen,account=s.account(len(blob)),sha256=hashlib.sha256(blob).hexdigest()))
  print('PREPARED',cid,flush=True)
def child(job,configs):
 chosen=configs[job['cid']];ds,e,tr,va,te=unit(chosen['unit']);rows=np.concatenate([tr,va,te]);var=float(np.var(tr.astype(float),axis=0).mean())
 s=JointService.loads((OUT/'initial_images'/f'{job["cid"]}.bin').read_bytes());initial_n=s.event_count
 case=OUT/'performance'/job['name'];case.mkdir(parents=True,exist_ok=True)
 co=sync_class()(s,TwoSlotStore(case/'checkpoint'),500) if job['mode']=='sync' else CheckpointCoordinator(s,TwoSlotStore(case/'checkpoint'),500,verify_capture=False)
 co.records=deque(co.records,maxlen=4096);co.wait_records_ms=deque(co.wait_records_ms,maxlen=4096)
 N=job['N'];rng=np.random.default_rng(20261110+job['rep']);p=rng.random(N)
 kinds=np.where(p<.95,0,np.where(p<.99,1,2)).astype(np.int8)
 widths=rng.integers(16,129,N);panels=rng.integers(0,3,N);ages=np.zeros(N,np.int64)
 for i,(a,z) in enumerate([(384,512),(1536,2048),(3072,4096) if chosen['R']==4096 else (6144,8192)]):
  ix=np.flatnonzero(panels==i);ages[ix]=rng.integers(a,z+1,len(ix))
 delays=ages-widths;keys=rng.integers(0,256,N)
 assert int((kinds==1).sum())<=len(te),'test observations must not cycle'
 served=np.zeros(N,bool);lat=np.zeros(N);scheduled_lat=np.zeros(N);bounds=np.full(N,np.nan);exact=np.zeros(N,bool);audit=[];factlog=[];raw_n=initial_n
 raw=np.empty((len(rows),4),np.float32);raw[:initial_n]=rows[:initial_n]
 index=0;ticket_lock=threading.Lock();bar=threading.Barrier(job['clients']+1);start=[0.]
 cp0=co.checkpoint_count_total;bytes0=co.checkpoint_envelope_bytes_total
 def work():
  nonlocal index,raw_n
  local=[]
  bar.wait()
  while True:
   with ticket_lock:
    i=index;index+=1
   if i>=N:break
   due=start[0]+i/job['rate'] if job['rate'] else None
   if due is not None:
    delay=due-time.perf_counter()
    if delay>0:time.sleep(delay)
   tick=time.perf_counter()
   if kinds[i]==0:
    z=s.query(int(keys[i]),int(delays[i]),int(widths[i]));h=z['history'];assert h['status']=='ANSWERED'
   else:
    def mutate():
     nonlocal raw_n
     if kinds[i]==1:
      row=rows[raw_n];ret=s.observe(row);raw[raw_n]=row;raw_n+=1
     else:
      row=tr[i%len(tr)];deleted=i%7==0;ret=s.put_fact(int(keys[i]),row,delete=deleted)
      factlog.append((s.ack_seq,int(keys[i]),s.version,deleted,row.copy()))
     return ret
    co.mutate(mutate)
   done=time.perf_counter();lat[i]=(done-tick)*1000;scheduled_lat[i]=(done-(tick if due is None else due))*1000;served[i]=True
   if kinds[i]==0:
    bounds[i]=float(np.sqrt(np.mean(h['total_bound']**2)/var));exact[i]=h['resolution']=='EXACT'
    if i%97==0:local.append(z)
  return local
 with ThreadPoolExecutor(max_workers=job['clients']) as pool:
  tasks=[pool.submit(work) for _ in range(job['clients'])];start[0]=time.perf_counter();bar.wait();audit=[z for task in tasks for z in task.result()];seconds=time.perf_counter()-start[0]
 preclose=time.perf_counter();co.close();drain=time.perf_counter()-preclose
 _,blob,_=co.store.recover();restored=JointService.loads(blob)
 assert served.all() and co.maximum_gap<=500 and co.durable_seq==s.ack_seq==restored.ack_seq
 assert all(np.array_equal(x,y) for x,y in zip(s._arrays().values(),restored._arrays().values()))
 ledger=s.account(len(blob));assert ledger['within_budget'] and ledger['snapshot_fits']
 oracle=ExactPrefix(raw[:raw_n]);checks=0
 for z in audit:
  h=z['history'];assert oracle.contains(z['lo'],z['hi'],h['value'],h['total_bound']);checks+=1
  f=z['fact'];prior=[v for v in factlog if v[0]<=z['prefix'] and v[1]==f['key']]
  if prior:
   _,key,ver,deleted,row=prior[-1];assert f['version']==ver and f['live']==(not deleted) and (deleted or np.array_equal(f['value'],row))
  else:assert f['version']==(f['key']+1 if f['key']<128 else 0)
 q=kinds==0;good=q&(bounds<=.1)
 result=dict(**job,config=chosen,seconds=seconds,throughput=N/seconds,query_rps=int(q.sum())/seconds,G01=float(good[q].mean()),certified_goodput=int(good.sum())/seconds,certified_goodput_5ms=int((good&(scheduled_lat<=5)).sum())/seconds,certified_goodput_20ms=int((good&(scheduled_lat<=20)).sum())/seconds,query_p99_ms=float(np.percentile(lat[q],99)),scheduled_query_p99_ms=float(np.percentile(scheduled_lat[q],99)),scheduled_query_p999_ms=float(np.percentile(scheduled_lat[q],99.9)),backlog_drain_seconds=max(0.,seconds-(N/job['rate'])) if job['rate'] else 0.,final_checkpoint_drain_seconds=drain,exact_fraction=float(exact[q].mean()),query_count=int(q.sum()),max_gap=co.maximum_gap,checkpoints=co.checkpoint_count_total-cp0,checkpoint_bytes=co.checkpoint_envelope_bytes_total-bytes0,exact_oracle_checks=checks,restored_all_arrays=True,ledger=ledger,test_observations=int((kinds==1).sum()),source_cycles=0)
 np.savez_compressed(case/'requests.npz',kind=kinds,delay=delays,width=widths,key=keys,latency_ms=lat,scheduled_latency_ms=scheduled_lat,normalized_bound=bounds,exact=exact)
 write(case/'result.json',result)
def main():
 selections=json.loads((OUT/'SELECTIONS.json').read_text());assert (OUT/'quality_records.json').exists(),'quality must complete before timing'
 configs={}
 for x in selections:
  if x['unit'] not in [0,1] or x['protocol']!='random_uniform' or (x['B'],x['R']) not in [(131072,4096),(262144,16384)] or x['objective'] not in ['mse','g01']:continue
  cid=f'u{x["unit"]}-B{x["B"]}-R{x["R"]}-{x["id"]}'
  if cid not in configs:configs[cid]={**x,'objectives':[x['objective']]}
  else:configs[cid]['objectives'].append(x['objective'])
 jobs=[]
 for cid,x in configs.items():
  for mode in ['sync','strict']:
   for rep in range(3):
    for rate in [0,5000,20000] if 'g01' in x['objectives'] else [0]:
     name=f'{cid}-{mode}-r{rep}-rate{rate}'
     jobs.append(dict(cid=cid,mode=mode,rep=rep,rate=rate,clients=8,N=30000 if rate==0 else rate*4,name=name))
 random.Random(20261110).shuffle(jobs)
 packet=dict(configs=configs,jobs=jobs,K=500,query_fraction=.95,observation_fraction=.04,fact_fraction=.01,selection='validation-only mse and G(0.1); all selected configurations retained',query_geometry='random_uniform; widths uniform16..128; equal near/middle/far panels',units='Bike and first Beijing station, fixed before timing; no claim over all13',arrival='8 closed-loop clients or deterministic paced tickets at5k/20k per second for4s; scheduled-to-completion includes backlog',source_hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__),*sorted((ROOT/'src/mtmemory_icde/core').glob('*.py'))]},platform=platform.platform(),python=sys.version,numpy=np.__version__)
 path=OUT/'PERFORMANCE_PROTOCOL.json'
 if path.exists():assert json.loads(path.read_text())==packet
 else:write(path,packet)
 prepare(configs)
 records=[]
 for i,job in enumerate(jobs):
  case=OUT/'performance'/job['name'];path=case/'result.json'
  if not path.exists():
   case.mkdir(parents=True,exist_ok=True);r=subprocess.run([sys.executable,str(Path(__file__)),json.dumps(job)],capture_output=True,text=True,timeout=180)
   (case/'stdout.txt').write_text(r.stdout);(case/'stderr.txt').write_text(r.stderr)
   assert r.returncode==0,(job,r.stderr)
  records.append(json.loads(path.read_text()));write(OUT/'performance_records.json',records)
  print('TIMING',i+1,len(jobs),job['name'],'goodput',round(records[-1]['certified_goodput'],1),flush=True)
 print('PERFORMANCE COMPLETE',len(records),flush=True)
if __name__=='__main__':
 if len(sys.argv)>1:
  packet=json.loads((OUT/'PERFORMANCE_PROTOCOL.json').read_text());child(json.loads(sys.argv[1]),packet['configs'])
 else:main()
