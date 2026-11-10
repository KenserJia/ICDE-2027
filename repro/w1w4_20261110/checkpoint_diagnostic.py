"""Separate short checkpoint-cost diagnostic; never pooled with prolonged latency."""
from pathlib import Path
import sys,json,time
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'src'))
from mtmemory_icde.core.strong_baselines import ComparisonService
from mtmemory_icde.core.rpo import CheckpointCoordinator
from mtmemory_icde.core.checkpoint import TwoSlotStore
OUT=ROOT/'results/w1w4_20261110'
def main():
 assert (OUT/'long_records.json').exists(),'do not overlap with prolonged measurement'
 protocol=json.loads((OUT/'LONG_PROTOCOL.json').read_text());data=np.load(ROOT/'data/real/household.npz');test=data['test_0'];records=[]
 for method in ['recent','strong']:
  for rep in range(3):
   case=OUT/'checkpoint_diagnostic'/f'{method}-{rep}';case.mkdir(parents=True,exist_ok=False)
   s=ComparisonService.loads((OUT/'long_initial'/f'{method}.bin').read_bytes());co=CheckpointCoordinator(s,TwoSlotStore(case/'checkpoint'),500,verify_capture=False);rng=np.random.default_rng(70000+rep);observed=0
   for i in range(100000):
    r=float(rng.random())
    if r<.95:s.query(i%256,int(rng.integers(256,3801)),int(rng.integers(16,129)))
    elif r<.99:
     co.mutate(lambda:s.observe(test[observed]));observed+=1
    else:co.mutate(lambda:s.put_fact(i%256,test[i%len(test)]))
   co.close();timings=[dict(r) for r in co.records if 'total_ms' in r and not r.get('initial',False)];rows=dict(method=method,rep=rep,requests=100000,scope='separate short diagnostic, not prolonged-run checkpoint percentiles',records=timings,max_gap=co.maximum_gap)
   (case/'records.json').write_text(json.dumps(rows,indent=2)+'\n');records.append(rows)
 (OUT/'CHECKPOINT_DIAGNOSTIC.json').write_text(json.dumps(records,indent=2)+'\n');print('checkpoint diagnostic complete',sum(len(r['records']) for r in records))
if __name__=='__main__':main()
