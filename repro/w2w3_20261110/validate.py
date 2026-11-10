"""Independent live-service crosscheck for follow-up reconstructed quality."""
from pathlib import Path
import sys,json,importlib.util
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'src'));sys.path.insert(0,str(ROOT/'repro/review7_20261109'))
spec=importlib.util.spec_from_file_location('followup_quality',Path(__file__).with_name('quality.py'));qmod=importlib.util.module_from_spec(spec);spec.loader.exec_module(qmod)
from mtmemory_icde.core.joint import JointService
from exact import ExactPrefix
OUT=ROOT/'results/w2w3_20261110'
def main():
 protocol=json.loads((OUT/'PERFORMANCE_PROTOCOL.json').read_text());records=[];count=0
 for cid,c in protocol['configs'].items():
  ui=c['unit'];ds='bike' if ui==0 else 'beijing'
  with np.load(ROOT/f'data/real/{ds}.npz') as z:tr,va,te=[z[f'{name}_0'].astype(np.float32) for name in ['train','validation','test']]
  initial=np.concatenate([tr,va]);s=JointService.loads((OUT/'initial_images'/f'{cid}.bin').read_bytes())
  maxp=maxb=0.;local=0
  for extension in [0,65]:
   if extension:
    for row in te[:extension]:s.observe(row)
    s.put_fact(0,te[0])
   rows=np.concatenate([initial,te[:extension]]);t=len(rows);tab=qmod.Offline(rows,OUT/'cache'/f'live-check-{ui}-{extension}');oracle=ExactPrefix(rows)
   rng=np.random.default_rng(20261110);queries=[]
   for panel,(a,z) in enumerate([(384,512),(1536,2048),(3072,4096) if c['R']==4096 else (6144,8192)]):
    for i in range(128):
     w=int(rng.integers(16,129));age=int(rng.integers(a,z+1));queries.append((t,age-w,w,panel,0))
   q=np.asarray(queries,np.int64);pred,bounds,truth,ex=tab.evaluate(q,c['config']);var=float(np.var(tr.astype(float),axis=0).mean())
   for i,(_,d,w,*_) in enumerate(q):
    answer=s.query(0,int(d),int(w));h=answer['history'];assert h['status']=='ANSWERED'
    dp=float(np.max(np.abs(pred[i]-h['value'])));db=float(np.max(np.abs(bounds[i]-h['total_bound'])));maxp=max(maxp,dp);maxb=max(maxb,db)
    assert dp<1e-10 and db<1e-10 and bool(ex[i])==(h['resolution']=='EXACT')
    assert oracle.contains(t-int(d)-int(w),t-int(d),h['value'],h['total_bound'])
    for eps in [.01,.05,.1,.2]:assert (np.sqrt(np.mean(bounds[i]**2)/var)<=eps)==(np.sqrt(np.mean(h['total_bound']**2)/var)<=eps)
    local+=1
   blob=s.dumps();s2=JointService.loads(blob);assert all(np.array_equal(x,y) for x,y in zip(s._arrays().values(),s2._arrays().values()));s=s2
  count+=local;records.append(dict(cid=cid,queries=local,max_prediction_difference=maxp,max_certificate_difference=maxb,all_tolerance_classifications_equal=True,full_array_restores=True))
 qmod.write(OUT/'LIVE_CROSSCHECK.json',dict(passed=True,queries=count,configs=len(records),records=records))
 print('LIVE CROSSCHECK',len(records),count,'max pred',max(x['max_prediction_difference'] for x in records),'max bound',max(x['max_certificate_difference'] for x in records),flush=True)
if __name__=='__main__':main()
