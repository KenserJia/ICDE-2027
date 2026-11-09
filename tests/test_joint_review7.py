from pathlib import Path
from fractions import Fraction
from itertools import combinations
from concurrent.futures import ThreadPoolExecutor
import sys,threading,time,json
import numpy as np
import pytest
from mtmemory_icde.core.joint import JointService,HEADER,MAGIC
from mtmemory_icde.core.histogram import partitions
from mtmemory_icde.core.rpo import CheckpointCoordinator,CheckpointFailure
from mtmemory_icde.core.checkpoint import TwoSlotStore
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'repro/review7_20261109'))
from exact import ExactPrefix

def service(engine='certified',**kw):return JointService(engine=engine,base_width=32,fine_width=4,overlay_capacity=4,max_reach=128,bins=3,budget=131072,**kw)

def test_histogram_DP_matches_bruteforce():
 x=np.array([[1,2],[2,3],[30,4],[31,4],[2,7],[1,9],[9,9],[4,1]],np.float32)
 got=partitions(x,3)
 def score(cuts):return sum(float(((x[a:b].astype(float)-x[a:b].astype(float).mean(0))**2).sum()) for a,b in zip(cuts,cuts[1:]))
 for q in [1,2,3]:
  best=min(score([0,*ix,len(x)]) for ix in combinations(range(1,len(x)),q-1));assert np.isclose(score(got[q]),best,rtol=0,atol=1e-10)

@pytest.mark.parametrize('engine',['native','certified','histogram'])
def test_joint_restore_actual_arrays_and_continue(engine):
 s=service(engine);s.initialize_facts(16);x=np.random.default_rng(81).normal(size=(477,4)).astype(np.float32)
 for t,row in enumerate(x,1):
  s.observe(row)
  if t%19==0:s.put_fact(t%16,row,delete=t%38==0)
  if t%37==0:
   s.query(3,7,63,certificate=engine!='native');z=JointService.loads(s.dumps())
   assert z.ack_seq==s.ack_seq and z.version==s.version and z.event_count==s.event_count
   assert all(np.array_equal(a,b) for a,b in zip(s._arrays().values(),z._arrays().values()))
   a=s.query(3,7,63,False,certificate=engine!='native');b=z.query(3,7,63,False,certificate=engine!='native');assert np.array_equal(a['history']['value'],b['history']['value'])
 s2=JointService.loads(s.dumps());s.observe(x[0]);s2.observe(x[0]);assert all(np.array_equal(a,b) for a,b in zip(s._arrays().values(),s2._arrays().values()))
 assert s.account(len(s.dumps()))['snapshot_fits']

@pytest.mark.parametrize('engine',['certified','histogram'])
def test_full_exact_oracle_floats_active_expiration(engine):
 rng=np.random.default_rng(83)
 for values in [rng.normal(size=383).astype(np.float32),np.resize(np.array([2.**90,1,-2.**90,2.**-90],np.float32),383),np.resize(np.array([np.nextafter(np.float32(0),np.float32(1)),0,-np.nextafter(np.float32(0),np.float32(1))],np.float32),383)]:
  rows=np.repeat(values[:,None],4,axis=1);oracle=ExactPrefix(rows);s=service(engine)
  for t,row in enumerate(rows,1):
   s.observe(row)
   if t%7:continue
   for d,w in [(0,1),(0,17),(1,31),(7,63),(0,128)]:
    if d+w>min(t,128):continue
    a=s.query(0,d,w)['history'];assert oracle.contains(t-d-w,t-d,a['value'],a['total_bound'])
   assert s.query(0,128,1)['history']['status']=='UNKNOWN'

def test_cache_controls_extrema_fact_freshness_and_restore():
 s=service(cache_capacity=32,policy='online');rows=np.random.default_rng(61).normal(size=(700,4)).astype(np.float32);oracle=ExactPrefix(rows)
 for row in rows:s.observe(row)
 a=s.query(3,7,63);a['history']['value'][:]=1e99;b=s.query(3,7,63);assert s.history.cache_hits==1 and np.all(abs(b['history']['value'])<100)
 s.put_fact(3,np.full(4,17));c=s.query(3,7,63);assert c['fact']['version']>b['fact']['version'] and c['prefix']==b['prefix']+1 and np.array_equal(c['fact']['value'],np.full(4,17))
 s.set_active_capacity(2);assert len(s.history.cache)==0
 for j,bid in enumerate(s.history.overlay_ids):
  if bid>=0:
   target=rows[int(bid)*32:(int(bid)+1)*32].reshape(8,4,4);assert np.array_equal(s.history.fine_min[j],target.min(1)) and np.array_equal(s.history.fine_max[j],target.max(1))
 for cap in [0,4,1,4]:
  s.set_active_capacity(cap)
  for d,w in [(7,63),(0,17),(32,32)]:
   z=s.query(0,d,w)['history'];assert oracle.contains(700-d-w,700-d,z['value'],z['total_bound'])
 z=JointService.loads(s.dumps());assert not z.history.cache
 s.observe(np.ones(4));assert not s.history.cache
 with pytest.raises(NotImplementedError):s.history.delete_event(1)
 with pytest.raises(NotImplementedError):s.history.promote_from_replay(1)

def test_budget_schema_and_invalid_requests_are_explicit():
 s=JointService(engine='histogram');assert s.account()['charged_bytes']==130716
 with pytest.raises(MemoryError):JointService(engine='histogram',bins=8,base_width=256)
 blob=s.dumps()
 for b in [blob[:8],b'badmagic'+blob[8:],blob+b'extra']:
  with pytest.raises(ValueError):JointService.loads(b)
 old=(s.ack_seq,s.version,s.request_seq)
 with pytest.raises(ValueError):s.put_fact(-1,np.ones(4))
 with pytest.raises(ValueError):s.observe(np.full(4,np.nan))
 assert old==(s.ack_seq,s.version,s.request_seq)
 with pytest.raises(ValueError):JointService(engine='native').query(0,0,1)

def test_strict_joint_concurrent_commit_and_failure(tmp_path):
 s=service(cache_capacity=32);s.initialize_facts();store=TwoSlotStore(tmp_path);co=CheckpointCoordinator(s,store,17,verify_capture=False)
 try:
  with ThreadPoolExecutor(max_workers=8) as pool:
   fs=[pool.submit(co.mutate,lambda i=i:s.observe(np.full(4,i))) for i in range(300)]
   for f in fs:f.result(timeout=10)
  co.close();_,blob,_=store.recover();z=JointService.loads(blob);assert z.ack_seq==s.ack_seq and co.maximum_gap<=17
  assert all(np.array_equal(a,b) for a,b in zip(s._arrays().values(),z._arrays().values()))
 finally:
  if co.thread.is_alive():co.close()
 co=CheckpointCoordinator(z,store,2,verify_capture=False);entered=threading.Event()
 def broken(payload,*a,**kw):entered.set();raise OSError('injected storage error')
 store.commit=broken
 for _ in range(2):co.mutate(lambda:z.observe(np.ones(4)))
 assert entered.wait(2)
 deadline=time.monotonic()+2
 while co.thread.is_alive() and time.monotonic()<deadline:time.sleep(.001)
 with pytest.raises(CheckpointFailure):co.mutate(lambda:z.observe(np.ones(4)))
 with pytest.raises(CheckpointFailure):co.force_checkpoint()
 assert z.ack_seq-co.durable_seq==2
 with pytest.raises(CheckpointFailure):co.close()
 assert not co.thread.is_alive()
