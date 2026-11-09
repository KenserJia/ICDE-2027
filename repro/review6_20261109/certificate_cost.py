from pathlib import Path
import sys,json,time,random,hashlib,argparse
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'src'))
from mtmemory_icde.core.history import Config,TieredOverlayStore
from mtmemory_icde.core.certified import CertifiedHistory
from optimized import FusedCertified,CachedCertified
from concurrency import dist,write
OUT=ROOT/'results/review6_20261109';LAYOUTS=[(64,8,8),(128,8,8),(128,16,16)]
VARIANTS={'native':TieredOverlayStore,'reference':CertifiedHistory,'fused':FusedCertified,'cache32':CachedCertified,'on_demand':FusedCertified,'cache32_on_demand':CachedCertified}
WORKLOADS=[('mixed28_unique',.28,False,1.,False),('mixed70_unique',.70,False,1.,False),('mixed95_unique',.95,False,1.,False),('mixed95_hot',.95,True,1.,False),('readonly_unique',1.,False,1.,False),('readonly_hot',1.,True,1.,False),('mixed95_optional25_hot',.95,True,.25,False),('readonly_aligned',1.,False,1.,True)]
def trace(spec,rep,n):
 name,qmix,hot,cf,aligned=spec;rng=np.random.default_rng(6000+rep)
 isq=rng.random(n)<qmix;wanted=rng.random(n)<cf
 if hot:
  shapes=np.array([(d,w) for d in [7,135,1031,2055] for w in [31,127]],int);p=rng.integers(0,len(shapes),n);d,w=shapes[p].T
 elif aligned:
  d=rng.integers(1,20,n)*128;w=rng.integers(1,8,n)*128
 else:d=rng.integers(0,3000,n);w=rng.choice([17,31,63,127,256],n)
 return isq,wanted,d,w

def one(layout,spec,variant,rep,n):
 b,f,k=layout;cls=VARIANTS[variant];cfg=Config(budget=10000000,base_width=b,fine_width=f,overlay_capacity=k,max_reach=4096,policy='recent')
 s=cls(cfg);data=np.load(ROOT/'data/real/beijing.npz');rows=data['test_0'].astype(np.float32)
 warm=data['validation_0'][-4096:].astype(np.float32);s.observe_many(warm);s.actions.clear()
 isq,wanted,ds,ws=trace(spec,rep,n);lat=np.empty(n);checksum=0.;returned=0
 # Warm code paths before measurement, without changing retained state or demand.
 for j in range(32):
  if variant in ['on_demand','cache32_on_demand']:s.query(int(ds[j]),int(ws[j]),False,certificate=bool(wanted[j]))
  else:s.query(int(ds[j]),int(ws[j]),False)
 if hasattr(s,'cache'):s.cache.clear();s.cache_hits=s.cache_misses=0
 begin=time.perf_counter_ns();updates=0
 for j in range(n):
  a=time.perf_counter_ns()
  if isq[j]:
   if variant in ['on_demand','cache32_on_demand']:z=s.query(int(ds[j]),int(ws[j]),False,certificate=bool(wanted[j]))
   else:z=s.query(int(ds[j]),int(ws[j]),False)
   assert z['status']=='ANSWERED'
   checksum+=float(z['value'][0]);returned+=int('total_bound' in z)
  else:s.observe(rows[updates%len(rows)]);s.actions.clear();updates+=1
  lat[j]=(time.perf_counter_ns()-a)/1e3
 elapsed=(time.perf_counter_ns()-begin)/1e9
 a=time.perf_counter_ns();blob=s.dumps();serialize_ms=(time.perf_counter_ns()-a)/1e6
 array_bytes=s.account()['resident_array_bytes'];cache_reserve=getattr(s,'PAYLOAD_RESERVE',0);charge=3*(array_bytes+8192)+8192+cache_reserve
 assert len(blob)<=array_bytes+8192 and charge<=131072
 ledger=dict(array_bytes=array_bytes,metadata_per_image=8192,workspace=8192,cache_payload_reserve=cache_reserve,charged=charge,cap=131072,image_bytes=len(blob),physical_RAM_bound=False)
 return dict(layout=list(layout),workload=spec[0],variant=variant,rep=rep,operations=n,queries=int(isq.sum()),updates=updates,requested_certificate_queries=int((isq&wanted).sum()),returned_certificate_queries=returned,query_us=dist(lat[isq]),update_us=dist(lat[~isq]),mixed_ops_per_second=n/elapsed,checksum=checksum,cache_hits=getattr(s,'cache_hits',0),cache_misses=getattr(s,'cache_misses',0),serialize_ms=serialize_ms,ledger=ledger)

def main():
 a=argparse.ArgumentParser();a.add_argument('--n',type=int,default=10000);args=a.parse_args()
 blocks=[(lay,sp,rep) for lay in LAYOUTS for sp in WORKLOADS for rep in range(7)];rng=random.Random(20261109);rng.shuffle(blocks);jobs=[]
 for lay,sp,rep in blocks:
  variants=list(VARIANTS);rng.shuffle(variants)
  for v in variants:jobs.append([lay,sp,v,rep])
 packet=dict(n=args.n,order=jobs,source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),optimized_sha256=hashlib.sha256((Path(__file__).parent/'optimized.py').read_bytes()).hexdigest(),design='seven paired technical timing repeats; randomized blocks/order; fixed geometry and same request trace; on-demand compared by requested guarantee; cache payload charged with same131072cap')
 frozen=OUT/'CERTIFICATE_COST_FREEZE.json'
 if frozen.exists():assert json.loads(frozen.read_text())==json.loads(json.dumps(packet))
 else:write(frozen,packet)
 dest=OUT/'certificate_cost';dest.mkdir(exist_ok=True)
 for i,(lay,sp,v,rep) in enumerate(jobs):
  name=f'b{lay[0]}-f{lay[1]}-k{lay[2]}-{sp[0]}-{v}-r{rep}'
  p=dest/(name+'.json')
  if not p.exists():write(p,one(lay,sp,v,rep,args.n))
  if (i+1)%12==0:print(i+1,len(jobs),name,flush=True)
if __name__=='__main__':main()
