import sys,itertools
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'src'))
from mtmemory_icde.core.strong_baselines import BoundWorkspace,ComparisonService

def test_bound_dp_matches_bruteforce():
 x=np.array([[0,1],[0,2],[3,2],[4,0],[4,1],[9,1],[9,0],[0,0]],float);s=BoundWorkspace(8,3,2,(2,3,5));cuts=s.solve(x)
 def cost(c):return sum(float(np.ptp(x[a:b],axis=0).mean())*s.coefficient[b-a] for a,b in zip(c,c[1:]))
 for q in [2,3]:
  best=min(cost([0,*c,8]) for c in itertools.combinations(range(1,8),q-1))
  assert abs(cost(cuts[q])-best)<1e-12

def test_new_baselines_restore_active_and_sealed_cells():
 rng=np.random.default_rng(5);x=rng.normal(size=(901,4)).astype(np.float32)
 for variant in ['bound','fixed','sse']:
  s=ComparisonService(engine='histogram',base_width=128,bins=2,max_reach=512,budget=262144,hist_variant=variant);s.initialize_facts()
  for row in x:s.observe(row)
  s.put_fact(0,x[0]);z=ComparisonService.loads(s.dumps())
  assert all(np.array_equal(a,b) for a,b in zip(s._arrays().values(),z._arrays().values()))
  for d,w in [(0,60),(1,31),(256,127),(300,100)]:
   h=z.query(0,d,w)['history'];truth=x[len(x)-d-w:len(x)-d].astype(float).mean(0)
   assert np.all(np.abs(h['value']-truth)<=h['total_bound'])
  assert z.account(len(z.dumps()))['snapshot_fits']
