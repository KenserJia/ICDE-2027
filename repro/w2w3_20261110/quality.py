"""Frozen alignment/objective study. Original scientific implementation is unchanged."""
from pathlib import Path
import sys,json,time,hashlib,platform
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
(ROOT/'results').mkdir(exist_ok=True)
sys.path.insert(0,str(ROOT/'src'))
sys.path.insert(0,str(ROOT/'repro/review7_20261109'))
import quality as old
from exact import ExactPrefix
from mtmemory_icde.core.numerics import gamma_upper
OUT=ROOT/'results/w2w3_20261110'
EPS=[.01,.05,.1,.2]
OBJECTIVES=['mse','g01','bound']
PROTOCOLS=['mixed','random_phase','random_uniform']
def write(path,x):
 path.parent.mkdir(parents=True,exist_ok=True)
 path.write_text(json.dumps(x,indent=2,allow_nan=False)+'\n')
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def schedule(start,end,R,seed,protocol):
 if protocol=='mixed':return old.schedule(start,end,R,seed)
 rng=np.random.default_rng(seed);rows=[];low=max(start+1,8192)
 for phase in range(256):
  choices=np.arange(low+(phase-low)%256,end+1,256);t=int(rng.choice(choices))
  for panel,(a,z) in enumerate([(384,512),(1536,2048),(3072,4096) if R==4096 else (6144,8192)]):
   for stratum in range(2):
    w=int(rng.integers(16,129)) if protocol=='random_uniform' else int(rng.choice([16,32,64,128] if stratum else [17,31,63,127]))
    age=int(rng.integers(a,z+1));rows.append((t,age-w,w,panel,stratum))
 return np.asarray(rows,np.int64)

class Offline(old.Offline):
 def __init__(self,rows,cache):super().__init__(rows);self.cache=cache
 def histogram(self,b):
  if b in self.hist:return self.hist[b]
  path=self.cache/f'hist-{b}.npz'
  if path.exists():
   with np.load(path) as z:self.hist[b]={q:{k:z[f'{q}/{k}'] for k in ['ends','sums','mins','maxs']} for q in [1,2,4,8]}
   return self.hist[b]
  result=super().histogram(b);self.cache.mkdir(parents=True,exist_ok=True)
  np.savez_compressed(path,**{f'{q}/{k}':a for q,v in result.items() for k,a in v.items()})
  return result
 def evaluate(self,queries,c):
  """Vectorized execution of disjoint-cell accumulation and outward Eq.(7)."""
  opts=c['options'];b=opts['base_width'];t,d,w=queries[:,:3].T;hi=t-d;lo=hi-w
  cursor=lo.copy();N=len(lo);total=np.zeros((N,4));raw=total.copy();upper=total.copy();mag=total.copy();terms=np.zeros(N,np.int64);partial=np.zeros(N,bool)
  if c['family']=='histogram':item=self.histogram(b)[opts['bins']]
  while np.any(cursor<hi):
   ix=np.flatnonzero(cursor<hi);pos=cursor[ix];base=pos//b*b
   full=(pos==base)&(hi[ix]>=base+b)
   if c['family']=='native':
    cut=((t[ix]-1)//b-opts['overlay_capacity'])*b
    h=np.where((pos>=cut)&(~full),opts['fine_width'],b)
    left=pos//h*h;m=h;S=np.zeros((len(ix),4));mn=S.copy();mx=S.copy()
    for width in np.unique(h):
     a,z,y=self.fixed_cells(int(width));take=np.flatnonzero(h==width);bid=left[take]//width
     S[take]=a[bid];mn[take]=z[bid];mx[take]=y[bid]
   else:
    bid=pos//b;local=pos%b;j=(item['ends'][bid]<=local[:,None]).sum(1)
    right=item['ends'][bid,j];l=np.where(j==0,0,item['ends'][bid,np.maximum(j-1,0)])
    left=base+l;m=right-l;S=item['sums'][bid,j].copy();mn=item['mins'][bid,j].copy();mx=item['maxs'][bid,j].copy()
    if np.any(full):
     sums,mins,maxs=self.fixed_cells(b);ii=np.flatnonzero(full)
     left[ii]=base[ii];m[ii]=b;S[ii]=sums[bid[ii]];mn[ii]=mins[bid[ii]];mx[ii]=maxs[bid[ii]]
   r=np.minimum(hi[ix],left+m)-pos;assert np.all(r>0)
   total[ix]+=(r/m)[:,None]*S;terms[ix]+=1
   mag[ix]=np.nextafter(mag[ix]+np.nextafter(r[:,None]*np.maximum(np.abs(mn),np.abs(mx)),np.inf),np.inf)
   hit=r!=m;ii=ix[hit];coef=r[hit]*(m[hit]-r[hit]);span=mx[hit]-mn[hit]
   raw[ii]+=(coef/m[hit])[:,None]*span
   upper[ii]=np.nextafter(upper[ii]+np.nextafter(np.nextafter((coef/m[hit])[:,None],np.inf)*np.nextafter(span,np.inf),np.inf),np.inf)
   partial[ii]=True;cursor[ix]+=r
  pred=total/w[:,None];analytical=raw/w[:,None];Bup=np.nextafter(upper/w[:,None],np.inf);Gup=np.nextafter(mag/w[:,None],np.inf)
  gamma=np.asarray([gamma_upper(b+int(v)+4) for v in terms])
  numerical=np.nextafter(gamma[:,None]*Gup,np.inf)
  evaluation=np.nextafter(np.maximum(0.,Bup-analytical),np.inf)
  bounds=np.nextafter(analytical+np.nextafter(numerical+evaluation,np.inf),np.inf)
  truth=(self.p[hi]-self.p[lo])/w[:,None]
  return pred,bounds,truth,~partial

def metrics(q,p,bounds,truth,exact,var,mask=None):
 if mask is None:mask=np.ones(len(q),bool)
 e=np.sqrt(np.mean((p[mask]-truth[mask])**2,axis=1)/var)
 z=np.sqrt(np.mean(bounds[mask]**2,axis=1)/var)
 return dict(n=int(mask.sum()),coverage=1.,mse=float(np.mean((p[mask]-truth[mask])**2)),nrmse=float(np.sqrt(np.mean(e*e))),exact=float(exact[mask].mean()),bound=float(z.mean()),G={str(x):float((z<=x).mean()) for x in EPS},U={str(x):float((e<=x).mean()) for x in EPS})

def main():
 OUT.mkdir(parents=True,exist_ok=True)
 freeze=OUT/'QUALITY_PROTOCOL.json'
 packet=dict(protocols=PROTOCOLS,objectives=OBJECTIVES,eps=EPS,budgets=[131072,262144],reaches=[4096,16384],selection='validation only; per protocol and family; charge then ID tie break',test_seeds=[0,1,2],quality_queries_per_selection=4608,scope='all queries in sealed history; fixed-grid block V-optimal, not all histograms',source_hashes={str(p.relative_to(ROOT)):digest(p) for p in [Path(__file__),*sorted((ROOT/'src/mtmemory_icde/core').glob('*.py'))]},python=sys.version,numpy=np.__version__,platform=platform.platform())
 if freeze.exists():assert json.loads(freeze.read_text())==packet
 else:write(freeze,packet)
 grids={(B,R):old.configs(B,R) for B in packet['budgets'] for R in packet['reaches']}
 units=list(old.units());selections=[]
 for ui,(ds,e,tr,va,te) in enumerate(units):
  dest=OUT/'validation'/f'{ui:02d}.json'
  if dest.exists():selections+=json.loads(dest.read_text())['selected'];continue
  tick=time.perf_counter();rows=np.concatenate([tr,va]);var=float(np.var(tr.astype(float),axis=0).mean());tab=Offline(rows,OUT/'cache'/f'validation-{ui:02d}')
  records=[];selected=[]
  for R in packet['reaches']:
   for protocol in PROTOCOLS:
    q=schedule(len(tr),len(rows),R,7100+ui*31,protocol)
    for B in packet['budgets']:
     for c in grids[B,R]:
      p,bd,truth,ex=tab.evaluate(q,c);m=metrics(q,p,bd,truth,ex,var)
      records.append(dict(unit=ui,dataset=ds,entity=e,B=B,R=R,protocol=protocol,id=c['id'],family=c['family'],metrics=m,config=c))
     for family in ['native','histogram']:
      pool=[x for x in records if x['B']==B and x['R']==R and x['protocol']==protocol and x['family']==family]
      for objective in OBJECTIVES:
       def score(x):
        m=x['metrics'];v=m['mse'] if objective=='mse' else -m['G']['0.1'] if objective=='g01' else m['bound']
        return v,x['config']['ledger']['charged_bytes'],x['id']
       best=min(pool,key=score);selected.append(dict(**best,objective=objective))
  write(dest,dict(selected=selected,candidates=records));selections+=selected
  print('VALIDATION',ui,ds,e,'seconds',round(time.perf_counter()-tick,1),flush=True)
 # All entities and objectives freeze before any new test queries are evaluated.
 gate=OUT/'SELECTIONS.json'
 if gate.exists():assert json.loads(gate.read_text())==selections
 else:write(gate,selections)
 signature=digest(gate);print('ALL SELECTIONS FROZEN',len(selections),signature,flush=True)
 records=[]
 for ui,(ds,e,tr,va,te) in enumerate(units):
  dest=OUT/'test'/f'{ui:02d}.json'
  if dest.exists():records+=json.loads(dest.read_text())['records'];continue
  tick=time.perf_counter();rows=np.concatenate([tr,va,te]);var=float(np.var(tr.astype(float),axis=0).mean());tab=Offline(rows,OUT/'cache'/f'test-{ui:02d}');oracle=ExactPrefix(rows);local=[];checked=0;cache={}
  for chosen in [x for x in selections if x['unit']==ui]:
   R=chosen['R'];protocol=chosen['protocol'];c=chosen['config'];key=(R,protocol,c['id'])
   if key not in cache:
    q=np.concatenate([schedule(len(tr)+len(va),len(rows),R,7200+ui*31+seed*1001,protocol) for seed in range(3)])
    p,bd,truth,ex=tab.evaluate(q,c)
    for qi,(t,d,w,*_) in enumerate(q):assert oracle.contains(int(t-d-w),int(t-d),p[qi],bd[qi]),(ui,c['id'],qi)
    checked+=len(q);cache[key]=(q,p,bd,truth,ex)
    path=OUT/'queries'/f'{ui:02d}-{R}-{protocol}-{c["id"]}.npz';path.parent.mkdir(exist_ok=True)
    np.savez_compressed(path,queries=q,prediction=p,bound=bd,truth=truth,exact=ex)
   q,p,bd,truth,ex=cache[key];groups={'all':np.ones(len(q),bool)}
   if protocol=='mixed':groups.update(aligned=q[:,4]==1,unaligned=q[:,4]==0)
   for i,name in enumerate(['near','middle','far']):groups[name]=q[:,3]==i
   local.append({k:v for k,v in chosen.items() if k!='metrics'}|dict(validation_metrics=chosen['metrics'],test={g:metrics(q,p,bd,truth,ex,var,mask) for g,mask in groups.items()},selection_sha256=signature))
  write(dest,dict(records=local,exact_oracle_queries=checked));records+=local
  print('TEST',ui,ds,e,'unique oracle checks',checked,'seconds',round(time.perf_counter()-tick,1),flush=True)
 write(OUT/'quality_records.json',records)
 print('QUALITY COMPLETE',len(records),flush=True)
if __name__=='__main__':main()
