"""Same joint contract and full payload budget; validation freeze precedes tests."""
from pathlib import Path
import sys,json,time,hashlib,math
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'src'))
from mtmemory_icde.core.joint import JointService
from mtmemory_icde.core.histogram import HistogramWorkspace
from mtmemory_icde.core.rpo import CheckpointCoordinator
from mtmemory_icde.core.checkpoint import TwoSlotStore
from exact import ExactPrefix
OUT=ROOT/'results/review7_20261109';OUT.mkdir(exist_ok=True)
def write(p,x):p.write_text(json.dumps(x,indent=2,allow_nan=False)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def units():
 for ds,n in [('bike',1),('beijing',12)]:
  z=np.load(ROOT/f'data/real/{ds}.npz')
  for e in range(n):yield ds,e,*[z[f'{name}_{e}'].astype(np.float32) for name in ['train','validation','test']]
def configs(B,R):
 out=[]
 for b in [64,128,256]:
  for f in [4,8,16]:
   for k in [0,4,8,16]:
    c=dict(engine='certified',base_width=b,fine_width=f,overlay_capacity=k,max_reach=R,budget=B,policy='recent')
    try:s=JointService(**c)
    except MemoryError:continue
    out.append(dict(id=f'n-b{b}-f{f}-k{k}',family='native',options=c,ledger=s.account()))
  for q in [1,2,4,8]:
   c=dict(engine='histogram',base_width=b,bins=q,max_reach=R,budget=B)
   try:s=JointService(**c)
   except MemoryError:continue
   out.append(dict(id=f'h-b{b}-q{q}',family='histogram',options=c,ledger=s.account()))
 return out

def schedule(start,end,R,seed):
 rng=np.random.default_rng(seed);rows=[];low=max(start+1,8192)
 for phase in range(256):
  eligible=np.arange(low+((phase-low)%256),end+1,256);assert len(eligible)>0;t=int(rng.choice(eligible))
  panels=[(384,512),(1536,2048),(3072,4096) if R==4096 else (6144,8192)]
  for p,(a,z) in enumerate(panels):
   for aligned in [False,True]:
    w=int(rng.choice([16,32,64,128] if aligned else [17,31,63,127]))
    ages=np.arange(a,z+1)
    if aligned:ages=ages[(t-ages)%16==0]
    age=int(rng.choice(ages));rows.append((t,age-w,w,p,int(aligned)))
 return np.asarray(rows,np.int64)

class Offline:
 def __init__(self,rows):
  self.x=rows.astype(np.float64);self.p=np.vstack([np.zeros(4),np.cumsum(self.x,axis=0)]);self.fixed={};self.hist={}
 def fixed_cells(self,width):
  if width not in self.fixed:
   n=len(self.x)//width;xx=self.x[:n*width].reshape(n,width,4);self.fixed[width]=(xx.sum(1),xx.min(1),xx.max(1))
  return self.fixed[width]
 def histogram(self,b):
  if b in self.hist:return self.hist[b]
  n=len(self.x)//b;solver=HistogramWorkspace(b,8,4);out={q:dict(ends=np.zeros((n,q),np.int32),sums=np.zeros((n,q,4)),mins=np.zeros((n,q,4)),maxs=np.zeros((n,q,4))) for q in [1,2,4,8]}
  for bid in range(n):
   block=self.x[bid*b:(bid+1)*b].astype(np.float32);allcuts=solver.solve(block)
   for q in out:
    cuts=allcuts[q];item=out[q];item['ends'][bid]=cuts[1:]
    for j,(a,z) in enumerate(zip(cuts,cuts[1:])):
     x=block[a:z].astype(float);item['sums'][bid,j]=x.sum(0);item['mins'][bid,j]=x.min(0);item['maxs'][bid,j]=x.max(0)
  self.hist[b]=out;return out
 def evaluate(self,queries,c):
  opts=c['options'];b=opts['base_width'];t,d,w,panel,al=queries.T;lo=t-d-w;hi=t-d
  def cell(pos):
   if c['family']=='native':
    cut=((t-1)//b-opts['overlay_capacity'])*b;h=np.where(pos>=cut,opts['fine_width'],b);left=pos//h*h;length=h;sums=np.zeros((len(pos),4));mn=sums.copy();mx=sums.copy()
    for width in np.unique(h):
     a,aa,bb=self.fixed_cells(int(width));ix=np.where(h==width)[0];j=left[ix]//width;sums[ix]=a[j];mn[ix]=aa[j];mx[ix]=bb[j]
    return left,length,sums,mn,mx
   item=self.histogram(b)[opts['bins']];bid=pos//b;local=pos%b;assert np.all(bid<(t-1)//b)
   j=(item['ends'][bid]<=local[:,None]).sum(1);right=item['ends'][bid,j];left=np.where(j==0,0,item['ends'][bid,np.maximum(0,j-1)]);m=right-left
   return bid*b+left,m,item['sums'][bid,j],item['mins'][bid,j],item['maxs'][bid,j]
  left,m,S,mn,mx=cell(lo);right,n,T,tn,tx=cell(hi-1)
  Flo=self.p[left]+((lo-left)/m)[:,None]*S;Fhi=self.p[right]+((hi-right)/n)[:,None]*T;prediction=(Fhi-Flo)/w[:,None]
  bound=np.zeros_like(prediction)
  for l,mm,aa,bb,use in [(left,m,mn,mx,np.ones(len(lo),bool)),(right,n,tn,tx,right!=left)]:
   r=np.minimum(hi,l+mm)-np.maximum(lo,l);bound[use]+=(r[use]*(mm[use]-r[use])/mm[use]/w[use])[:,None]*(bb[use]-aa[use])
  truth=(self.p[hi]-self.p[lo])/w[:,None];exact=(lo==left)&(hi==right+n)
  return prediction,bound,truth,exact

def metrics(q,p,truth,exact,var,bound=None):
 e=((p-truth)**2).mean(1);out={}
 for label,mask in [('all',np.ones(len(q),bool))]+[(name,q[:,3]==i) for i,name in enumerate(['near','middle','far'])]:
  out[label]=dict(queries=int(mask.sum()),coverage=1.,mse=float(e[mask].mean()),nrmse=float(np.sqrt(e[mask].mean()/var)),exact_fraction=float(exact[mask].mean()))
  if bound is not None:
   norm=np.sqrt((bound[mask]**2).mean(1)/var);out[label]['mean_normalized_bound']=float(norm.mean());out[label]['guaranteed_within_0_1']=float((norm<=.1).mean())
 return out

def main():
 for sub in ['quality_validation','quality_test','quality_cache']:(OUT/sub).mkdir(exist_ok=True)
 grids={(B,R):configs(B,R) for B in [131072,262144] for R in [4096,16384]}
 sources=[Path(__file__),ROOT/'repro/review7_20261109/exact.py',*list((ROOT/'src/mtmemory_icde/core').glob('*.py')),ROOT/'data/real/bike.npz',ROOT/'data/real/beijing.npz']
 packet=dict(hashes={str(p.relative_to(ROOT)):sha(p) for p in sources},grids={f'{B}/{R}':v for (B,R),v in grids.items()},scope='validation-only independently selected joint service; same facts/reach/codec/admission/certificate; no full DigitHist claim')
 freeze=OUT/'QUALITY_PROTOCOL_FREEZE.json'
 if not freeze.exists():write(freeze,packet)
 else:assert json.loads(freeze.read_text())==packet
 selected=[];allval=[];U=list(units())
 for ui,(ds,e,tr,va,te) in enumerate(U):
  dest=OUT/'quality_validation'/f'{ui:02d}.json'
  if dest.exists():p=json.loads(dest.read_text());allval+=p['rows'];selected+=p['selected'];continue
  a=time.perf_counter();rows=np.concatenate([tr,va,te]);tab=Offline(rows);records=[];sel=[]
  for R in [4096,16384]:
   q=schedule(len(tr),len(tr)+len(va),R,7100+ui*31)
   for B in [131072,262144]:
    for c in grids[B,R]:
     p,bd,truth,exact=tab.evaluate(q,c);loss=float(((p-truth)**2).mean());records.append(dict(unit=ui,dataset=ds,entity=e,B=B,R=R,id=c['id'],family=c['family'],validation_mse=loss,charge=c['ledger']['charged_bytes']))
    for family in ['native','histogram']:
     candidates=[x for x in records if x['B']==B and x['R']==R and x['family']==family];best=min(candidates,key=lambda x:(x['validation_mse'],x['charge'],x['id']));c=next(x for x in grids[B,R] if x['id']==best['id']);sel.append(dict(**best,config=c))
  write(dest,dict(rows=records,selected=sel));allval+=records;selected+=sel;print('validation',ui+1,13,round(time.perf_counter()-a,1),'seconds',flush=True)
 serialized=json.dumps(selected,indent=2,allow_nan=False)+'\n';gate=OUT/'QUALITY_SELECTION.json'
 if gate.exists():assert gate.read_text()==serialized
 else:gate.write_text(serialized)
 signature=hashlib.sha256(serialized.encode()).hexdigest();test_gate=OUT/'QUALITY_TEST_GATE.json'
 if not test_gate.exists():write(test_gate,dict(selection_sha256=signature,all_validation_units=13,test_units_at_initial_freeze=0))
 print('ALL SELECTIONS FROZEN',len(selected),flush=True)
 alltest=[]
 for ui,(ds,e,tr,va,te) in enumerate(U):
  dest=OUT/'quality_test'/f'{ui:02d}.json'
  if dest.exists():alltest+=json.loads(dest.read_text())['rows'];continue
  a=time.perf_counter();rows=np.concatenate([tr,va,te]);var=float(np.var(tr.astype(float),axis=0).mean());oracle=ExactPrefix(rows);tab=Offline(rows);records=[]
  for chosen in [x for x in selected if x['unit']==ui]:
   R,B=chosen['R'],chosen['B'];c=chosen['config'];qs=np.concatenate([schedule(len(tr)+len(va),len(rows),R,7200+ui*31+seed*1001) for seed in range(3)])
   expected,bd,truth,ex=tab.evaluate(qs,c);s=JointService(**c['options']);s.initialize_facts(128);case=OUT/'quality_test'/f'{ui:02d}-{B}-{R}-{c["family"]}';case.mkdir(exist_ok=True);co=CheckpointCoordinator(s,TwoSlotStore(case/'checkpoint'),500,verify_capture=False)
   by={int(t):[] for t in np.unique(qs[:,0])}
   for qi,q in enumerate(qs):by[int(q[0])].append(qi)
   pred=np.zeros((len(qs),4));bounds=pred.copy();exact=np.zeros(len(qs),bool);maxdiff=0.;image_margin=None;arrays_ok=True;checks=0
   for t,row in enumerate(rows,1):
    co.mutate(lambda row=row:s.observe(row))
    if t%257==0:co.mutate(lambda t=t,row=row:s.put_fact(t%256,row,delete=t%514==0))
    if t==len(tr)+len(va):
     co.close();_,blob,_=co.store.recover();z=JointService.loads(blob);arrays_ok &= all(np.array_equal(a,b) for a,b in zip(s._arrays().values(),z._arrays().values()));assert arrays_ok;s=z;co=CheckpointCoordinator(s,co.store,500,verify_capture=False)
    for qi in by.get(t,[]):
     _,d,w,panel,aligned=qs[qi];answer=s.query(0,int(d),int(w));h=answer['history'];assert h['status']=='ANSWERED';lo=t-int(d)-int(w);hi=t-int(d)
     assert oracle.contains(lo,hi,h['value'],h['total_bound']),('certificate failure',ui,c['id'],t,d,w)
     pred[qi]=h['value'];bounds[qi]=h['total_bound'];exact[qi]=h['resolution']=='EXACT';maxdiff=max(maxdiff,float(np.max(np.abs(pred[qi]-expected[qi]))));checks+=1
   co.close();_,blob,_=co.store.recover();z=JointService.loads(blob);account=s.account(len(blob));assert account['within_budget'] and account['snapshot_fits'] and z.ack_seq==s.ack_seq and co.maximum_gap<=500
   assert all(np.array_equal(a,b) for a,b in zip(s._arrays().values(),z._arrays().values()))
   assert maxdiff<1e-10,maxdiff
   rec=dict(unit=ui,dataset=ds,entity=e,B=B,R=R,family=c['family'],id=c['id'],config=c,validation_mse=chosen['validation_mse'],metrics=metrics(qs,pred,truth,exact,var,bounds),checks=checks,violations=0,max_reconstruction_difference=maxdiff,ledger=account,restored_prefix=z.ack_seq,full_array_roundtrip=True,selection_sha256=signature)
   np.savez_compressed(case/'queries.npz',queries=qs,prediction=pred,truth=truth,bound=bounds,exact=exact);records.append(rec)
  write(dest,dict(rows=records));alltest+=records;print('test',ui+1,13,round(time.perf_counter()-a,1),'seconds',flush=True)
 write(OUT/'quality_validation.json',allval);write(OUT/'quality_test.json',alltest);print('QUALITY COMPLETE',len(alltest),sum(x['checks'] for x in alltest),flush=True)
if __name__=='__main__':main()
