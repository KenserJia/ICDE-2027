from pathlib import Path
import sys,json
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'src'))
from mtmemory_icde.core.numerics import certified_mean,gamma_upper,up
from quality import OUT,write,sha
from exact import ExactPrefix

def main():
 rng=np.random.default_rng(71112);checks=0;worst=0.;cases=[]
 for b in [3,16,64,128,256]:
  for shape in ['normal','cancellation','subnormal','large']:
   x=rng.normal(size=(b,4)).astype(np.float32)
   if shape=='cancellation':x=np.resize(np.array([2.**90,1,-2.**90,2.**-90],np.float32),(b,4))
   elif shape=='subnormal':x=np.resize(np.array([np.nextafter(np.float32(0),np.float32(1)),0,-np.nextafter(np.float32(0),np.float32(1))],np.float32),(b,4))
   elif shape=='large':x*=np.float32(2.**100)
   exact=ExactPrefix(x)
   seq=np.zeros(4)
   for z in x:seq+=z
   for kernel,S in [('sequential',seq),('numpy_binary64',np.sum(x,axis=0,dtype=np.float64))]:
    for lo,hi in [(0,b),(0,1),(b//3,max(b//3+1,b-1))]:
     a=certified_mean([(0,b,S,x.min(0).astype(float),x.max(0).astype(float))],lo,hi,4,b)
     assert exact.contains(lo,hi,a['value'],a['total_bound']);checks+=1
     cases.append(dict(b=b,shape=shape,kernel=kernel,lo=lo,hi=hi,contained=True))
 x=np.repeat(np.array([2.**24,1.,-2.**24],np.float32)[:,None],4,axis=1);S=np.zeros(4,np.float32)
 for z in x:S+=z
 wrong=certified_mean([(0,3,S.astype(float),x.min(0).astype(float),x.max(0).astype(float))],0,3,4,3)
 exact=ExactPrefix(x);assert not exact.contains(0,3,wrong['value'],wrong['total_bound'])
 gamma32=gamma_upper(wrong['arithmetic_depth'],2.**-24);allowance=up(gamma32*float(2.**24));assert exact.contains(0,3,wrong['value'],np.full(4,allowance))
 write(OUT/'numerical_kernel.json',dict(source_sha256=sha(Path(__file__)),supported_checks=checks,cases=cases,negative_control=dict(description='unsupported binary32 cell-sum accumulator reused with binary64 allowance',true_mean=1/3,prediction=wrong['value'].tolist(),wrong_binary64_allowance=wrong['total_bound'].tolist(),violates_misapplied_allowance=True,binary32_unit_roundoff_shadow_allowance=float(allowance),shadow_contains=True,production_supported=False)))
if __name__=='__main__':main()
