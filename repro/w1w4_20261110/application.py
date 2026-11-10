from pathlib import Path
import sys,json,importlib.util,time
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'src'));sys.path.insert(0,str(ROOT/'repro/review7_20261109'))
from mtmemory_icde.core.strong_baselines import ComparisonService
from exact import ExactPrefix
OUT=ROOT/'results/w1w4_20261110'
def write(p,x):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,indent=2,allow_nan=False)+'\n')
def service_at(config,rows,t):
 s=ComparisonService(**config['options']);s.initialize_facts(128);b=config['options']['base_width'];R=config['options']['max_reach'];start=max(0,(t-R-2*b)//b*b);s.history.event_count=start
 for x in rows[start:t]:s.observe(x,count_ack=False)
 assert s.event_count==t
 return s

def main():
 choices=json.loads((OUT/'SELECTIONS.json').read_text());z=np.load(ROOT/'data/real/household.npz');tr,va,te=[z[f'{n}_0'] for n in ['train','validation','test']];rows=np.concatenate([tr,va,te]);std=z['std'];mean=z['mean'];physical=z['physical'];power_reconstruction=rows[:,0].astype(float)*std[0]+mean[0];delta=np.abs(power_reconstruction-physical[:,0]);dp=np.r_[0.,np.cumsum(delta)]
 records=[];seen=set();cross=[]
 for c in [x for x in choices if x['dataset']=='household']:
  key=c['B'],c['id']
  if key in seen:continue
  seen.add(key);options=c['config'];R=c['R'];b=options['options']['base_width'];local=[]
  for fraction in [.1,.5,.9]:
   t=len(tr)+len(va)+int(len(te)*fraction);s=service_at(options,rows,t);raw=s.dumps();ss=ComparisonService.loads(raw);assert all(np.array_equal(a,v) for a,v in zip(s._arrays().values(),ss._arrays().values()))
   # Configuration updates are controlled synthetic inputs, not dataset metadata.
   ss.put_fact(0,rows[t-1]);widths=[60,1440]+([10080] if R>=10080 else [])
   for w in widths:
    for d in [0,60,1440]:
     if d+w>R:continue
     answer=ss.query(0,d,w);h=answer['history'];lo=t-d-w;hi=t-d;oracle=ExactPrefix(rows[lo:hi]);assert oracle.contains(0,w,h['value'],h['total_bound'])
     pp=h['value'][0]*std[0]+mean[0];conversion=(dp[hi]-dp[lo])/w;T=np.nextafter(h['total_bound'][0]*std[0]+conversion+1e-12*(abs(pp)+1),np.inf);truth=float(physical[lo:hi,0].astype(float).mean());assert abs(pp-truth)<=T
     local.append(dict(t=t,window_minutes=w,delay_minutes=d,physical_mean_kw=float(pp),truth_kw=truth,bound_kw=float(T),error_kw=abs(float(pp)-truth),normalized_bound=float(np.sqrt(np.mean(h['total_bound']**2))),exact=h['resolution']=='EXACT',fact_version=answer['fact']['version'],conversion_allowance_kw=float(conversion)))
  records.append(dict(B=c['B'],R=R,id=c['id'],variant=c['variant'],config=options,queries=local,G_kw={str(e):float(np.mean([r['bound_kw']<=e for r in local])) for e in [.05,.1,.2]},U_kw={str(e):float(np.mean([r['error_kw']<=e for r in local])) for e in [.05,.1,.2]}))
  print('APPLICATION',c['id'],len(local),flush=True)
 write(OUT/'APPLICATION.json',dict(scope='one-hour/day/week retrospective mean; controlled synthetic fact changes; kW tolerances are sensitivity settings, not a production SLO',records=records,max_input_conversion_kw=float(delta.max())))
 # Exact rational audit of random selected queries, without allocating a full 2M-row integer log.
 checks=0
 for p in (OUT/'queries').glob('*.npz'):
  unit=int(p.name.split('-')[0]);dataset='bike' if unit==0 else 'beijing' if unit<13 else 'household';entity=0 if unit in [0,13] else unit-1
  with np.load(ROOT/f'data/real/{dataset}.npz') as data:xx=np.concatenate([data[f'{n}_{entity}'] for n in ['train','validation','test']])
  with np.load(p) as data:
   for i in np.linspace(0,len(data['queries'])-1,32,dtype=int):
    t,d,w,*_=data['queries'][i];oracle=ExactPrefix(xx[t-d-w:t-d]);assert oracle.contains(0,int(w),data['prediction'][i],data['bound'][i]),(p,i);checks+=1
 write(OUT/'EXACT_AUDIT.json',dict(passed=True,sampled_reconstructed_queries=checks,application_queries=sum(len(r['queries']) for r in records)))
 print('AUDIT COMPLETE',checks,flush=True)
if __name__=='__main__':main()
