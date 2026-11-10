from pathlib import Path
import sys,json,importlib.util,hashlib,time,itertools
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'src'));sys.path.insert(0,str(ROOT/'repro/review7_20261109'));(ROOT/'results').mkdir(exist_ok=True)
spec=importlib.util.spec_from_file_location('w2quality',ROOT/'repro/w2w3_20261110/quality.py');w2=importlib.util.module_from_spec(spec);spec.loader.exec_module(w2)
from mtmemory_icde.core.strong_baselines import ComparisonService,BoundWorkspace
from mtmemory_icde.core.histogram import HistogramWorkspace
from exact import ExactPrefix
OUT=ROOT/'results/w1w4_20261110'
WIDTHS=(16,17,31,32,63,64,127,128)
def write(p,x):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,indent=2,allow_nan=False)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def units():
 for ds,n in [('bike',1),('beijing',12),('household',1)]:
  if not (ROOT/f'data/real/{ds}.npz').exists():continue
  with np.load(ROOT/f'data/real/{ds}.npz') as z:
   for e in range(n):yield ds,e,*[z[f'{name}_{e}'].astype(np.float32) for name in ['train','validation','test']]
def configs(B,R):
 result=[]
 for b in [128,256]:
  for f,k in itertools.product([8,16],[0,4,8,16]):
   o=dict(engine='certified',base_width=b,fine_width=f,overlay_capacity=k,max_reach=R,budget=B,policy='recent')
   try:s=ComparisonService(**o)
   except MemoryError:continue
   result.append(dict(id=f'recent-b{b}-f{f}-k{k}',family='native',variant='recent',options=o,ledger=s.account()))
  for variant in ['sse','bound','fixed']:
   for q in [1,2,4]:
    o=dict(engine='histogram',base_width=b,bins=q,max_reach=R,budget=B,hist_variant=variant,prior_widths=WIDTHS)
    try:s=ComparisonService(**o)
    except MemoryError:continue
    result.append(dict(id=f'{variant}-b{b}-q{q}',family='histogram',variant=variant,options=o,ledger=s.account()))
 return result
class Offline(w2.Offline):
 def __init__(self,rows,cache,variant='sse'):super().__init__(rows,cache);self.variant=variant
 def histogram(self,b):
  if self.variant=='sse':return super().histogram(b)
  if b in self.hist:return self.hist[b]
  path=self.cache/f'{self.variant}-b{b}.npz'
  if path.exists():
   with np.load(path) as z:self.hist[b]={q:{k:z[f'{q}/{k}'] for k in ['ends','sums','mins','maxs']} for q in [1,2,4]}
   return self.hist[b]
  n=len(self.x)//b;out={q:dict(ends=np.zeros((n,q),np.int32),sums=np.zeros((n,q,4)),mins=np.zeros((n,q,4)),maxs=np.zeros((n,q,4))) for q in [1,2,4]}
  solver=BoundWorkspace(b,4,4,WIDTHS) if self.variant=='bound' else None
  for bid in range(n):
   block=self.x[bid*b:(bid+1)*b];cuts=solver.solve(block) if solver is not None else {q:np.linspace(0,b,q+1,dtype=int) for q in out}
   for q,item in out.items():
    cut=cuts[q];item['ends'][bid]=cut[1:]
    for j,(a,z) in enumerate(zip(cut,cut[1:])):
     xx=block[a:z];item['sums'][bid,j]=xx.sum(0);item['mins'][bid,j]=xx.min(0);item['maxs'][bid,j]=xx.max(0)
  self.hist[b]=out;self.cache.mkdir(parents=True,exist_ok=True);np.savez_compressed(path,**{f'{q}/{k}':a for q,v in out.items() for k,a in v.items()});return out
 def feature(self,q,c,rough):
  o=c['options'];b=o['base_width'];w=q[:,2];age=q[:,1]+w
  if c['variant']=='recent':
   hit=age<=b*o['overlay_capacity'];h=np.where(hit,o['fine_width'],b)
  else:h=np.full(len(q),b/o['bins']);hit=np.full(len(q),o['bins']>1,bool)
  ratio=h/w
  return [1.,float(np.log1p(ratio).mean()),float(hit.mean()),float(np.log1p(ratio*rough/.1).mean())]
def main():
 OUT.mkdir(parents=True,exist_ok=True);U=list(units());grids={(B,R):configs(B,R) for B,R in [(131072,4096),(262144,16384)]}
 packet=dict(cases=list(grids),families=['recent','sse','bound','fixed'],query_prior=list(WIDTHS),selection='validation MSE and G(.1), independently per family',rule='linear least squares on old-domain validation G using training roughness and query geometry; frozen before household validation/test',seeds=[0,1,2],hashes={str(p.relative_to(ROOT)):sha(p) for p in [Path(__file__),ROOT/'src/mtmemory_icde/core/strong_baselines.py']})
 write(OUT/'QUALITY_PROTOCOL.json',packet);selected=[];trainrows=[];rule=None
 for ui,(ds,e,tr,va,te) in enumerate(U):
  dest=OUT/'validation'/f'{ui:02d}.json'
  if dest.exists():
   z=json.loads(dest.read_text());selected+=z['selected'];trainrows+=z['candidates'];continue
  tick=time.perf_counter();rows=np.concatenate([tr,va]);var=float(np.var(tr.astype(float),axis=0).mean());rough=float(np.quantile(np.abs(np.diff(tr.astype(float),axis=0)),.9)/np.sqrt(var));tabs={v:Offline(rows,OUT/'cache'/f'val{ui}-{v}',v) for v in ['sse','bound','fixed']};local=[];choices=[]
  if ds=='household':
   xx=np.asarray([r['features'] for r in trainrows]);yy=np.asarray([r['metrics']['G']['0.1'] for r in trainrows]);coef=np.linalg.lstsq(xx,yy,rcond=None)[0];rule=dict(coefficients=coef.tolist(),training_units=13,training_rows=len(yy),features=['intercept','mean log1p(h/w)','fine-coverage fraction','mean log1p((h/w)*training-roughness/.1)']);write(OUT/'RULE_FREEZE.json',rule)
  for (B,R),grid in grids.items():
   q=w2.schedule(len(tr),len(rows),R,9100+ui*31,'random_uniform')
   for c in grid:
    tab=tabs['sse' if c['variant']=='recent' else c['variant']];p,bd,truth,ex=tab.evaluate(q,c);m=w2.metrics(q,p,bd,truth,ex,var);features=tab.feature(q,c,rough);local.append(dict(unit=ui,dataset=ds,entity=e,B=B,R=R,id=c['id'],variant=c['variant'],config=c,features=features,metrics=m))
   for variant in packet['families']:
    pool=[r for r in local if r['B']==B and r['variant']==variant]
    for objective in ['mse','g01']:
     best=min(pool,key=lambda r:(r['metrics']['mse'] if objective=='mse' else -r['metrics']['G']['0.1'],r['config']['ledger']['charged_bytes'],r['id']))
     choices.append(dict(**best,objective=objective))
   if ds=='household':
    pool=[r for r in local if r['B']==B];best=max(pool,key=lambda r:(float(np.dot(r['features'],rule['coefficients'])),-r['config']['ledger']['charged_bytes'],r['id']));choices.append(dict(**best,objective='frozen_rule'))
    best=min(pool,key=lambda r:(-r['metrics']['G']['0.1'],r['config']['ledger']['charged_bytes'],r['id']));choices.append(dict(**best,objective='validation_global'))
  write(dest,dict(selected=choices,candidates=local));selected+=choices;trainrows+=local;print('VALIDATION',ui,ds,'seconds',round(time.perf_counter()-tick,1),flush=True)
 if '--validation-only' in sys.argv:return
 write(OUT/'SELECTIONS.json',selected);print('ALL FROZEN',len(selected),flush=True)
 records=[]
 for ui,(ds,e,tr,va,te) in enumerate(U):
  dest=OUT/'test'/f'{ui:02d}.json'
  if dest.exists():records+=json.loads(dest.read_text());continue
  tick=time.perf_counter();rows=np.concatenate([tr,va,te]);var=float(np.var(tr.astype(float),axis=0).mean());tabs={v:Offline(rows,OUT/'cache'/f'test{ui}-{v}',v) for v in ['sse','bound','fixed']};local=[];cache={}
  # Exact oracle only over query endpoints; use integer prefix in a sampled live audit later.
  for c in [r for r in selected if r['unit']==ui]:
   config=c['config'];R=c['R'];key=(R,c['id'])
   if key not in cache:
    q=np.concatenate([w2.schedule(len(tr)+len(va),len(rows),R,9200+ui*31+seed*1001,'random_uniform') for seed in range(3)]);tab=tabs['sse' if c['variant']=='recent' else c['variant']];p,bd,truth,ex=tab.evaluate(q,config);cache[key]=(q,p,bd,truth,ex)
    pp=OUT/'queries'/f'{ui}-{R}-{c["id"]}.npz';pp.parent.mkdir(exist_ok=True);np.savez_compressed(pp,queries=q,prediction=p,bound=bd,truth=truth,exact=ex)
   q,p,bd,truth,ex=cache[key];local.append({k:v for k,v in c.items() if k!='metrics'}|dict(validation_metrics=c['metrics'],test=w2.metrics(q,p,bd,truth,ex,var)))
  write(dest,local);records+=local;print('TEST',ui,ds,'seconds',round(time.perf_counter()-tick,1),flush=True)
 write(OUT/'quality_records.json',records);print('COMPLETE',len(records),flush=True)
if __name__=='__main__':main()
