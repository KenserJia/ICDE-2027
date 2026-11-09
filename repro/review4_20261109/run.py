from pathlib import Path
import sys,json,hashlib,time,math,importlib.util,platform,csv
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'repro/review3')]
from mtmemory_icde.core.history import Config,TieredOverlayStore
from mtmemory_icde.core.certified import CertifiedHistory
from plato_range import PlatoRange
OUT=ROOT/'results/review4_20261109';REPRO=ROOT/'repro/review4_20261109'
BUDGETS=[65536,131072,262144];RS=[512,1024,2048,4096,8192,16384];BS=[64,128,256];HS=[1,4,8,16];M=6144;W=8192

def write(name,obj):
 (OUT/name).write_text(json.dumps(obj,indent=2,allow_nan=False)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def units():
 for ds,n in [('bike',1),('beijing',12)]:
  z=np.load(ROOT/f'data/real/{ds}.npz')
  for e in range(n):yield ds,e,*[z[f'{x}_{e}'].astype(np.float32) for x in ['train','validation','test']]
def ledger(s,reserve=0):return 3*(s.account()['resident_array_bytes']+M)+W+reserve
def cfg(b,h,k,R=16384):return Config(budget=10000000,base_width=b,fine_width=h,overlay_capacity=k,max_reach=R,policy='recent' if k else 'none')
def grid(cert=False,reserve=0):
 out=[];cls=CertifiedHistory if cert else TieredOverlayStore
 for B in BUDGETS:
  for R in RS:
   for b in BS:
    for h in HS:
     s=cls(cfg(b,h,0,R));a=ledger(s,reserve)
     s1=cls(cfg(b,h,1,R));inc=ledger(s1,reserve)-a
     if a>B:continue
     k=min(math.ceil(R/b)+1,(B-a)//inc)
     for kk in sorted(set([0,k//2,k])):
      out.append(dict(B=B,R=R,b=b,h=h,k=int(kk),charge=int(a+kk*inc),cert=cert,reserve=reserve))
 return out

def sched(start,end,seed,validation=False):
 # One anchor per residue modulo 256, stratified over eligible test prefixes.
 low=max(start+1,8192 if validation else 16384);assert end-low>=256
 rng=np.random.default_rng(seed);ts=[]
 for phase in range(256):
  eligible=np.arange(low+((phase-low)%256),end+1,256);ts.append(int(rng.choice(eligible)))
 qs=[]
 for t in ts:
  for bi,(lowage,highage) in enumerate(zip([384,512,1024,2048,4096,8192],[512,1024,2048,4096,8192,16384])):
   for align in [0,1]:
    if validation:continue
    w=int(rng.choice([16,32,64,128] if align else [17,31,63,127]));a=int(rng.integers(lowage+1,highage+1))
    if align:a=t-16*int(rng.integers(math.ceil((t-highage)/16),math.floor((t-lowage-1)/16)+1))
    a=min(a,16384)
    qs.append([t,0,bi,align,a,w])
  for bi,(lo,hi) in enumerate([(384,512),(1536,2048),(6144,8192)]):
   for align in [0,1]:
    w=int(rng.choice([16,32,64,128] if align else [17,31,63,127]));a=int(rng.integers(lo,hi+1))
    if align:a=t-16*int(rng.integers(math.ceil((t-hi)/16),math.floor((t-lo)/16)+1))
    qs.append([t,1,bi,align,a,w])
 return np.array(qs,np.int64)
class Tables:
 def __init__(self,rows):
  self.rows=rows.astype(np.float64);self.p=np.vstack([np.zeros(4),np.cumsum(self.rows,axis=0)]);self.cache={}
 def cells(self,h):
  if h not in self.cache:
   n=len(self.rows)//h;x=self.rows[:n*h].reshape(n,h,4)
   self.cache[h]=(x.sum(1),x.min(1),x.max(1))
  return self.cache[h]
 def eval(self,q,c,bound=False):
  t=q[:,0];a=q[:,4];w=q[:,5];lo=t-a;hi=lo+w;b=c['b'];h=c['h'];k=c['k'];cut=((t-1)//b-k)*b
  def endpoint(x):
   f=np.where(x>=cut,h,b);left=x//f*f;m=f;full=self.p[left];s=self.p[left+f]-full
   return full+(x-left)[:,None]/f[:,None]*s,f
  fl,hl=endpoint(lo);fh,hh=endpoint(hi)
  pred=(fh-fl)/w[:,None];state=np.where(a>c['R'],0,np.where((lo%hl==0)&(hi%hh==0),2,1))
  truth=(self.p[hi]-self.p[lo])/w[:,None];bd=np.zeros_like(pred)
  if bound:
   # Only boundary cells contribute; avoid double-counting a shared cell.
   for endpoint_,isright in [(lo,False),(hi-1,True)]:
    f=np.where(endpoint_>=cut,h,b);left=endpoint_//f*f;right=left+f
    prevf=np.where(lo>=cut,h,b);prevleft=lo//prevf*prevf
    use=np.ones(len(q),bool) if not isright else left!=prevleft
    r=np.maximum(0,np.minimum(hi,right)-np.maximum(lo,left))
    for width in np.unique(f):
     sums,mn,mx=self.cells(int(width));ix=np.where((f==width)&use)[0];D=mx[left[ix]//width]-mn[left[ix]//width]
     bd[ix]+=(r[ix]*(width-r[ix])/width/w[ix])[:,None]*D
  return pred,state,truth,bd

def metrics(q,p,s,y,var,bd=None):
 err=((p-y)**2).mean(1)/var;result={}
 for fam in [0,1]:
  for bi in ([-1] if fam==0 else [-1,0,1,2]):
   for al in [-1,0,1]:
    mask=(q[:,1]==fam)&((q[:,2]==bi) if bi>=0 else True)&((q[:,3]==al) if al>=0 else True);ok=mask&(s>0)
    if not mask.any():continue
    r=dict(family=fam,distance=bi,alignment=al,n=int(mask.sum()),coverage=float(np.mean(s[mask]>0)),exact=float(np.mean(s[mask]==2)),nrmse=float(np.sqrt(err[ok].mean())) if ok.any() else None)
    for ep in [.01,.05,.1,.2]:r[f'U{ep}']=float(np.sum(ok&(np.sqrt(err)<=ep))/mask.sum())
    if bd is not None:
     be=np.sqrt((bd**2).mean(1)/var)
     for ep in [.01,.05,.1,.2]:r[f'G{ep}']=float(np.sum(ok&(be<=ep))/mask.sum())
    result[f'{fam}/{bi}/{al}']=r
 return result

def rq2():
 specs=grid();write('grid.json',specs);records=[];choices=[];transitions=[];cross=[]
 for ui,(ds,en,tr,va,te) in enumerate(units()):
  rows=np.concatenate([tr,va,te]);tab=Tables(rows);var=float(np.var(tr.astype(float),axis=0).mean());unit=OUT/f'unit_{ui:02d}.json'
  if unit.exists():
   r=json.loads(unit.read_text());records+=r['records'];choices+=r['choices'];transitions+=r['transitions'];cross+=r['cross'];continue
  # Freeze all validation choices before this entity's test is evaluated.
  vq=sched(len(tr),len(tr)+len(va),20261109+ui,validation=True);loss=[]
  for c in specs:
   p,s,y,_=tab.eval(vq,c);common=(vq[:,1]==1)&(vq[:,4]<=c["R"])
   loss.append(float(np.mean(((p-y)**2)[common])))
  selected={}
  for B in BUDGETS:
   for R in RS:
    ix=[i for i,c in enumerate(specs) if c['B']==B and c['R']==R];j=min(ix,key=lambda i:(loss[i],specs[i]['charge'],specs[i]['b'],specs[i]['h'],specs[i]['k']))
    selected[B,R]=j;choices.append(dict(unit=ui,B=B,R=R,index=j,validation_mse=loss[j],**{k:specs[j][k] for k in ['b','h','k','charge']}))
  write(f'selection_{ui:02d}.json',dict(selection=[x for x in choices if x['unit']==ui],validation_only=True,test_evaluated=False))
  rr=[];tt=[];cc=[]
  for seed in range(3):
   q=sched(len(tr)+len(va),len(rows),20261109+ui*101+seed*10007);pred=[];states=[]
   np.savez_compressed(OUT/f'queries_{ui:02d}_{seed}.npz',queries=q)
   for ci,c in enumerate(specs):
    p,s,y,_=tab.eval(q,c);pred.append(p);states.append(s)
    # Save all fixed-b maximal-capacity curves and validation-selected results.
    maxk=max(x['k'] for x in specs if all(x[k]==c[k] for k in ['B','R','b','h']))
    if c['k']==maxk or selected[c['B'],c['R']]==ci:
     rr.append(dict(unit=ui,dataset=ds,entity=en,seed=seed,index=ci,selected=selected[c['B'],c['R']]==ci,**c,metrics=metrics(q,p,s,y,var)))
   # Matched per-query transitions for original b128 maximal k rule.
   for B in BUDGETS:
    for h in HS:
     for R0,R1 in zip(RS[:-1],RS[1:]):
      ids=[]
      for R in [R0,R1]:
       ix=[i for i,c in enumerate(specs) if c['B']==B and c['R']==R and c['b']==128 and c['h']==h];ids.append(max(ix,key=lambda i:specs[i]['k']))
      i,j=ids;mask=q[:,1]==1
      changes=np.sqrt(np.mean((pred[j]-y)**2,1)/var)-np.sqrt(np.mean((pred[i]-y)**2,1)/var)
      tt.append(dict(unit=ui,seed=seed,B=B,h=h,R0=R0,R1=R1,gained=int(np.sum((states[i]==0)&(states[j]>0))),lost_exact=int(np.sum((states[i]==2)&(states[j]==1))),common_prediction_changes=int(np.sum(mask&np.any(pred[i]!=pred[j],1))),common_query_error_delta=float(changes[mask].mean())))
   if seed==0:
    # Independent live-stream equivalence checks, including ring wrap and full phase sweep.
    for b,h,k in [(64,4,3),(128,4,3),(256,16,2),(128,1,0)]:
     c=dict(b=b,h=h,k=k,R=16384);st=TieredOverlayStore(cfg(b,h,k));by={int(t):[] for t in q[:,0]}
     for qi in range(0,len(q),16):by[int(q[qi,0])].append(qi)
     check=0;maxdiff=0.
     off=0
     # Replay sufficient preceding state, keeping absolute segment identity.
     for t,row in enumerate(rows,1):
      st.observe(row);st.actions.clear()
      for qi in by.get(t,[]):
       qq=q[qi:qi+1];p,s,y,_=tab.eval(qq,c);ans=st.query(int(qq[0,4]-qq[0,5]),int(qq[0,5]),record=False);d=float(np.max(np.abs(ans['value']-p[0])));maxdiff=max(maxdiff,d);assert d<1e-9;assert (ans['resolution']=='EXACT')==(s[0]==2);check+=1
     cc.append(dict(b=b,h=h,k=k,cases=check,max_difference=maxdiff))
  r=dict(records=rr,choices=[x for x in choices if x['unit']==ui],transitions=tt,cross=cc);write(f'unit_{ui:02d}.json',r);records+=rr;transitions+=tt;cross+=cc
  print('RQ2 unit',ui,'complete',len(rr),flush=True)
 write('rq2_records.json',records);write('selections.json',choices);write('transitions.json',transitions);write('equivalence.json',cross)

if __name__=='__main__':rq2()
