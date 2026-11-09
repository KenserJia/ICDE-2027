from pathlib import Path
import sys,json
import numpy as np
from concurrency import ROOT,OUT,write
from mtmemory_icde.core.history import Config
from mtmemory_icde.core.certified import CertifiedHistory
from optimized import FusedCertified,CachedCertified

def main():
 result=[];checks=0
 for ds,n in [('bike',1),('beijing',12)]:
  data=np.load(ROOT/f'data/real/{ds}.npz')
  for e in range(n):
   rows=np.concatenate([data[f'{p}_{e}'] for p in ['train','validation','test']]).astype(np.float32)
   for b,f,k in [(64,8,8),(128,8,8),(128,16,16)]:
    cfg=Config(budget=1000000,base_width=b,fine_width=f,overlay_capacity=k,max_reach=4096,policy='recent');ss=[c(cfg) for c in [CertifiedHistory,FusedCertified,CachedCertified]];count=unknown=violations=0;maxdiff=bdiff=0.;roundratio=[]
    for t,row in enumerate(rows,1):
     for s in ss:s.observe(row);s.actions.clear()
     if t<4096 or t%97:continue
     for d,w in [(0,1),(0,17),(7,63),(135,127),(1031,63),(2055,256),(3500,63),(4096,1)]:
      a=[s.query(d,w,False) for s in ss];assert len({z['status'] for z in a})==1
      if a[0]['value'] is None:unknown+=1;continue
      truth=rows[t-d-w:t-d].astype(float).mean(0)
      for z in a:
       violations+=int(np.any(np.abs(z['value']-truth)>z['total_bound']+1e-14))
      assert all(z['resolution']==a[0]['resolution'] for z in a)
      maxdiff=max(maxdiff,float(np.max(np.abs(a[0]['value']-a[1]['value']))));bdiff=max(bdiff,float(np.max(np.abs(a[0]['bound']-a[1]['bound']))));assert bdiff==0
      roundratio.extend((a[1]['rounding_bound']/a[0]['rounding_bound']).tolist())
      again=ss[2].query(d,w,False);assert np.array_equal(again['value'],a[2]['value']);count+=1
    assert violations==0 and maxdiff<1e-12
    for s in ss:
     blob=s.dumps();z=type(s).loads(blob);a=s.query(7,63,False);bq=z.query(7,63,False);assert np.array_equal(a['value'],bq['value']) and np.array_equal(a['total_bound'],bq['total_bound'])
    result.append(dict(dataset=ds,entity=e,b=b,f=f,k=k,answered_cases=count,unknown_cases=unknown,violations=violations,max_prediction_difference=maxdiff,max_analytical_bound_difference=bdiff,rounding_ratio_range=[float(min(roundratio)),float(max(roundratio))],cache_hit_checks=count,snapshot_restores=3));write(OUT/'optimized_quality.json',result)
   print('optimized quality',ds,e,flush=True)
if __name__=='__main__':main()
