from pathlib import Path
import sys,json,time
from collections import defaultdict
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'src'));sys.path.insert(0,str(ROOT/'repro/round78_rq_closure'))
import run as old
from mtmemory_icde.core.history import Config
from mtmemory_icde.core.service import ControlledOverlayStore
OUT=ROOT/'results/review_revision_20261104';OUT.mkdir(exist_ok=True)
BUDGET=44780

def candidates():
 out={}
 for b in (32,64,128):
  for f in (4,8,16):
   for k in (0,8,16):
    if k==0 and f!=8:continue
    name=f'b{b}-f{f}-k{k}'
    try:out[name]=ControlledOverlayStore(Config(budget=BUDGET,channels=4,base_width=b,fine_width=f,max_reach=4096,overlay_capacity=k,policy='recent',query_history=128),active_capacity=k)
    except MemoryError:pass
 return out

def main():
 frozen=json.loads((ROOT/'results/frozen/rq_closure/rq3_boundary/RQ3_FREEZE.json').read_text())
 specs={k:v['spec'] for k,v in frozen['workloads'].items()}
 specs.update(held12={'shift_buckets':12,'dwell_queries':32,'width_buckets':2},held24={'shift_buckets':24,'dwell_queries':64,'width_buckets':2},held28={'shift_buckets':28,'dwell_queries':8,'width_buckets':2})
 rows_out=[];selections=[];packets=[]
 # Complete every validation selection, then write the immutable selection file,
 # before executing any test query in this confirmation pass.
 for ui,(dataset,entity,train,val,test) in enumerate(old.all_split_units()):
  stores=candidates();static_names=list(stores)
  for label in specs:
   for pol in ('recent','online'):
    stores[label+'-'+pol]=ControlledOverlayStore(Config(budget=BUDGET,channels=4,base_width=64,fine_width=8,max_reach=4096,overlay_capacity=16,policy=pol,query_history=128),16)
  warm=train[-4096:];prefix=np.concatenate([warm,val]);stats=defaultdict(list);queries=defaultdict(list)
  for label,spec in specs.items():
   for q in old.workload_queries(len(val),spec,old.SEED+ui*31,warmup=2432,offset=len(warm)):queries[q['t']].append((label,q))
  for t,row in enumerate(prefix,1):
   for store in stores.values():store.observe(row);store._trim_actions()
   for label,q in queries.get(t,[]):
    truth=prefix[t-q['delay']-q['window']:t-q['delay']].astype(np.float64).mean(0)
    for name in static_names+[label+'-recent',label+'-online']:
     a=stores[name].query(q['delay'],q['window'])
     if a['value'] is not None:stats[label,name].append(float(np.mean((a['value']-truth)**2)))
  chosen={}
  for label in specs:
   selected=min(static_names,key=lambda n:(np.mean(stats[label,n]),stores[n].account()['charged_bytes'],n));chosen[label]=selected
   selections.append(dict(dataset=dataset,entity=entity,workload=label,selected=selected,selection_split='validation',validation_mse=float(np.mean(stats[label,selected]))))
  keep=set(chosen.values())|{label+'-'+pol for label in specs for pol in ('recent','online')}
  packets.append((ui,dataset,entity,train,prefix,test,{n:stores[n] for n in keep},chosen))
  print('validation frozen',dataset,entity,flush=True)
 old.write_json(OUT/'fixed_selection.json',selections)
 import hashlib,datetime
 selection_hash=hashlib.sha256((OUT/'fixed_selection.json').read_bytes()).hexdigest()
 old.write_json(OUT/'FIXED_SELECTION_FREEZE.json',dict(timestamp_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),selection_sha256=selection_hash,test_queries_executed=0,selection_split='validation'))
 for ui,dataset,entity,train,prefix,test,stores,chosen in packets:
  allrows=np.concatenate([prefix,test]);offset=len(prefix);queries=defaultdict(list);nq=defaultdict(int);stats=defaultdict(list)
  for label,spec in specs.items():
   for q in old.workload_queries(len(test),spec,old.SEED+ui*31,warmup=2432,offset=offset):queries[q['t']].append((label,q));nq[label]+=1
  for t,row in enumerate(test,offset+1):
   for store in stores.values():store.observe(row);store._trim_actions()
   for label,q in queries.get(t,[]):
    truth=allrows[t-q['delay']-q['window']:t-q['delay']].astype(np.float64).mean(0)
    for method,name in [('selected_fixed',chosen[label]),('original_fixed',label+'-recent'),('dynamic',label+'-online')]:
     a=stores[name].query(q['delay'],q['window'])
     if a['value'] is not None:stats[label,method].append(float(np.mean((a['value']-truth)**2)))
  variance=float(np.var(train.astype(np.float64),axis=0).mean())
  for label in specs:
   for method,name in [('selected_fixed',chosen[label]),('original_fixed',label+'-recent'),('dynamic',label+'-online')]:
    errs=stats[label,method];mse=float(np.mean(errs));rows_out.append(dict(dataset=dataset,entity=entity,workload=label,method=method,layout=name,mse=mse,nrmse=float(np.sqrt(mse/variance)),queries=nq[label],answered=len(errs),coverage=len(errs)/nq[label],charged_bytes=stores[name].account()['charged_bytes']))
  print('test entity complete',dataset,entity,flush=True);old.write_json(OUT/'strong_fixed_raw.json',rows_out)
 summary=[]
 for label in specs:
  rr=[r for r in rows_out if r['workload']==label];idx={(r['dataset'],r['entity'],r['method']):r for r in rr}
  pairs=[(idx[d,e,'dynamic'],idx[d,e,'selected_fixed']) for d,e in sorted({(r['dataset'],r['entity']) for r in rr})]
  delta=[a['mse']-b['mse'] for a,b in pairs];rel=[1-a['mse']/max(b['mse'],1e-12) for a,b in pairs]
  summary.append(dict(workload=label,entities=len(pairs),dynamic_mse=float(np.mean([a['mse'] for a,b in pairs])),selected_fixed_mse=float(np.mean([b['mse'] for a,b in pairs])),dynamic_minus_selected=float(np.mean(delta)),bootstrap95_delta=old.bootstrap_ci(delta),mean_relative_reduction=float(np.mean(rel)),dynamic_wins=sum(x<0 for x in delta),coverage_min=min(r['coverage'] for r in rr),max_charge=max(r['charged_bytes'] for r in rr)))
 assert hashlib.sha256((OUT/'fixed_selection.json').read_bytes()).hexdigest()==selection_hash
 old.write_json(OUT/'strong_fixed_summary.json',summary);print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
