"""Score bandwidth/history sensitivity at fixed native layout; all validation before test."""
from pathlib import Path
from collections import defaultdict
import sys,json,time,hashlib,math
import numpy as np
from concurrency import ROOT,OUT,write,legacy
from mtmemory_icde.core.history import Config
from mtmemory_icde.core.service import ControlledOverlayStore
class KernelHistory(ControlledOverlayStore):
 def __init__(self,cfg,tau=2):
  self.tau=float(tau);super().__init__(cfg,active_capacity=cfg.overlay_capacity)
 def _score(self,bid):
  if self.cfg.policy=='recent':return super()._score(bid)
  age=max(0,self.event_count//self.cfg.base_width-bid);hist=self.q_delays[self.q_delays>=0]
  target=(hist if len(hist) else np.asarray(self.cfg.catalog_delays))/self.cfg.base_width
  return float(np.exp(-np.abs(target-age)/self.tau).sum())
 @classmethod
 def restore(cls,blob,tau):
  s=ControlledOverlayStore.from_blob(blob,16);s.__class__=cls;s.tau=tau;return s

def configs():return [dict(id=f't{tau}-L{L}',policy='online',tau=tau,L=L) for tau in [.5,1,2,4,8] for L in [32,128,512]]+[dict(id='recent',policy='recent',tau=2,L=128)]
def make(c):return KernelHistory(Config(budget=131072,base_width=64,fine_width=8,overlay_capacity=16,max_reach=4096,policy=c['policy'],query_history=c['L']),c['tau'])
def charge(s):return 3*(s.account()['resident_array_bytes']+8192)+8192

def specs():
 d={k:v['spec'] for k,v in json.loads((ROOT/'results/frozen/rq_closure/rq3_boundary/RQ3_FREEZE.json').read_text())['workloads'].items()}
 d.update(held12=dict(shift_buckets=12,dwell_queries=32,width_buckets=2),held24=dict(shift_buckets=24,dwell_queries=64,width_buckets=2),held28=dict(shift_buckets=28,dwell_queries=8,width_buckets=2));return d

def pass_unit(ui,unit,stage,cs,ws,selection_hash=None):
 ds,en,tr,va,te=unit;sub=OUT/'sensitivity'/stage;sub.mkdir(parents=True,exist_ok=True);dest=sub/f'{ui:02d}.json'
 if dest.exists():return json.loads(dest.read_text())
 var=float(np.var(tr.astype(float),axis=0).mean());stores=[];ids=[]
 for label in ws:
  for c in cs:
   ids.append((label,c))
   if stage=='validation':stores.append(make(c))
   else:
    blob=(OUT/'sensitivity/states'/f'{ui:02d}-{label}-{c["id"]}.npz').read_bytes();stores.append(KernelHistory.restore(blob,c['tau']))
 if stage=='validation':rows=np.concatenate([tr[-4096:],va]);offset=0;length=len(va);qoffset=4096
 else:rows=te;offset=4096+len(va);length=len(te);qoffset=offset
 allrows=np.concatenate([tr[-4096:],va,te]);by=defaultdict(list);counts=defaultdict(int)
 for label,sp in ws.items():
  for q in legacy.workload_queries(length,sp,legacy.SEED+ui*31,warmup=2432,offset=qoffset):by[q['t']].append((label,q))
 ix={w:[i for i,(lab,c) in enumerate(ids) if lab==w] for w in ws};sq=[[] for s in stores];exact=[0]*len(stores);scalecheck=0
 for t,row in enumerate(rows,offset+1):
  for s in stores:s.observe(row);s.actions.clear()
  for label,q in by.get(t,[]):
   truth=allrows[t-q['delay']-q['window']:t-q['delay']].astype(float).mean(0);counts[label]+=1
   for i in ix[label]:
    a=stores[i].query(q['delay'],q['window']);assert a['status']=='ANSWERED';sq[i].append(float(np.mean((a['value']-truth)**2)));exact[i]+=int(a['resolution']=='EXACT')
  if stage=='validation' and t%1024==0:
   # Positive score scaling cannot change any non-underflow ranking in this trace.
   s=stores[0];bids=s.overlay_ids[s.overlay_ids>=0];scores=np.array([s._score(int(b)) for b in bids])
   for factor in [.01,100.]:
    assert np.array_equal(np.argsort(scores,kind='stable'),np.argsort(scores*factor,kind='stable'));scalecheck+=1
 result=[]
 for i,(s,(label,c)) in enumerate(zip(stores,ids)):
  mse=float(np.mean(sq[i]));blob=s.dumps();assert charge(s)<=131072 and len(blob)<=s.account()['resident_array_bytes']+8192
  rec=dict(dataset=ds,entity=en,workload=label,**c,stage=stage,mse=mse,nrmse=float(np.sqrt(mse/var)),queries=len(sq[i]),coverage=1.,exact_fraction=exact[i]/len(sq[i]),charged_bytes=charge(s),snapshot_bytes=len(blob),array_bytes=s.account()['resident_array_bytes']);result.append(rec)
  if stage=='validation':(OUT/'sensitivity/states'/f'{ui:02d}-{label}-{c["id"]}.npz').write_bytes(blob)
 packet=dict(unit=ui,dataset=ds,entity=en,rows=result,scale_invariance_checks=scalecheck,selection_sha256=selection_hash)
 write(dest,packet);return packet

def main():
 (OUT/'sensitivity/states').mkdir(parents=True,exist_ok=True);cs=configs();ws=specs();units=legacy.all_split_units();source=Path(__file__)
 freeze=OUT/'SENSITIVITY_PROTOCOL_FREEZE.json';packet=dict(source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),configs=cs,workloads=ws,units=13,geometry=[64,8,16,4096],cap=131072,metadata=8192,workspace=8192,selection='validation MSE, charge, distance from tau2, id; globally freeze before test',platform=legacy.environment())
 if not freeze.exists():write(freeze,packet)
 else:assert json.loads(freeze.read_text())['source_sha256']==packet['source_sha256']
 val=[]
 for ui,unit in enumerate(units):
  a=time.perf_counter();p=pass_unit(ui,unit,'validation',cs,ws);val+=p['rows'];print('validation',ui+1,13,round(time.perf_counter()-a,2),flush=True)
 selections=[]
 for ui,(ds,en,*_) in enumerate(units):
  for lab in ws:
   candidates=[x for x in val if x['dataset']==ds and x['entity']==en and x['workload']==lab and x['policy']=='online']
   best=min(candidates,key=lambda x:(x['mse'],x['charged_bytes'],abs(math.log(x['tau']/2)),x['id']))
   selections.append(dict(dataset=ds,entity=en,workload=lab,id=best['id'],validation_mse=best['mse']))
 # A single per-workload deployment setting chosen by macro validation NRMSE squared.
 global_select=[]
 for lab in list(ws)+['all_workloads']:
  score={c['id']:float(np.mean([x['nrmse']**2 for x in val if x['id']==c['id'] and (lab=='all_workloads' or x['workload']==lab)])) for c in cs if c['policy']=='online'}
  best=min(score,key=lambda k:(score[k],next(x['L'] for x in cs if x['id']==k),k));global_select.append(dict(workload=lab,id=best,validation_nmse=score[best]))
 f=OUT/'SENSITIVITY_SELECTION.json';frozen=dict(entity_workload=selections,shared=global_select,all_selections_before_test=True)
 content=json.dumps(frozen,indent=2,allow_nan=False)+'\n'
 if not f.exists():f.write_text(content)
 else:assert f.read_text()==content
 sh=hashlib.sha256(content.encode()).hexdigest();write(OUT/'SENSITIVITY_TEST_GATE.json',dict(selection_sha256=sh,all_validation_units=13,test_units_executed_at_initial_freeze=0))
 raw=[]
 for ui,unit in enumerate(units):
  a=time.perf_counter();p=pass_unit(ui,unit,'test',cs,ws,sh);raw+=p['rows'];print('test',ui+1,13,round(time.perf_counter()-a,2),flush=True)
 write(OUT/'sensitivity_test_results.json',raw);write(OUT/'sensitivity_validation_results.json',val)
 # Exact default/recent reproduction under the original schedule and warm start.
 archive=json.loads((ROOT/'results/rq3_symmetric_20261107/candidate_test_results.json').read_text());check=[]
 for x in raw:
  if x['id'] not in ['t2-L128','recent']:continue
  z=next(y for y in archive if y['dataset']==x['dataset'] and y['entity']==x['entity'] and y['workload']==x['workload'] and y['policy']==x['policy'] and y['layout']=='b64-f8-k16');delta=x['mse']-z['mse'];assert abs(delta)<1e-12
  check.append(dict(dataset=x['dataset'],entity=x['entity'],workload=x['workload'],id=x['id'],mse_difference=delta))
 write(OUT/'sensitivity_default_reproduction.json',check);print('reproduced',len(check),'default/recent cases',flush=True)
if __name__=='__main__':main()
