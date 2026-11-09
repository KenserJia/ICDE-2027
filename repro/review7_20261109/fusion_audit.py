from pathlib import Path
import sys,numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'src'))
from mtmemory_icde.core.joint import JointService
from exact import ExactPrefix
from quality import OUT,write,sha
from fault_child import value

def main():
 x=np.asarray([value(i) for i in range(8355)],np.float32);oracle=ExactPrefix(x);s=[JointService(fused=z) for z in [False,True]]
 for a in s:
  for row in x:a.observe(row)
 rng=np.random.default_rng(71114);records=[]
 for label in ['short_random','wide_recent']:
  terms=[];difference=0.;improved=0
  for j in range(2000):
   if label=='short_random':d=int(rng.integers(3801));w=int(rng.choice([17,31,63,127]))
   else:d=int(rng.integers(256));w=int(rng.choice([255,511,1023]))
   a,b=[z.query(0,d,w,record=False)['history'] for z in s];lo=len(x)-d-w;hi=len(x)-d
   assert np.array_equal(a['bound'],b['bound']) and a['resolution']==b['resolution']
   assert oracle.contains(lo,hi,a['value'],a['total_bound']) and oracle.contains(lo,hi,b['value'],b['total_bound'])
   difference=max(difference,float(np.max(abs(a['value']-b['value']))));terms.append([a['contributing_cells'],b['contributing_cells']]);improved+=b['contributing_cells']<a['contributing_cells']
  records.append(dict(workload=label,queries=2000,reference_mean_cells=float(np.mean(np.asarray(terms)[:,0])),fused_mean_cells=float(np.mean(np.asarray(terms)[:,1])),queries_with_fewer_cells=improved,max_prediction_difference=difference,analytical_bounds_equal=True,structural_resolution_equal=True,exact_oracle_checks=4000,violations=0))
 write(OUT/'fusion_audit.json',dict(source_sha256=sha(Path(__file__)),records=records,scope='fixed retained state diagnostic; not a timing benchmark; total arithmetic allowances may differ because path depth and magnitude enclosure change'))
if __name__=='__main__':main()
