from fractions import Fraction
import numpy as np
from mtmemory_icde.core.history import Config,TieredOverlayStore
from mtmemory_icde.core.certified import CertifiedHistory
from optimized import FusedCertified,CachedCertified

def test_values_bounds_active_edges_and_restore():
 rng=np.random.default_rng(73)
 for b,f,k in [(16,1,0),(32,8,2),(64,16,4)]:
  cfg=Config(budget=1000000,base_width=b,fine_width=f,overlay_capacity=k,max_reach=128)
  ss=[c(cfg) for c in [TieredOverlayStore,CertifiedHistory,FusedCertified,CachedCertified]];x=rng.normal(size=(389,4)).astype(np.float32)
  for t,row in enumerate(x,1):
   for s in ss:s.observe(row);s.actions.clear()
   if t<32:continue
   for d,w in [(0,1),(0,17),(1,31),(7,63),(32,64),(0,128),(128,1),(-1,3),(0,0)]:
    a=[s.query(d,w) for s in ss]
    assert len({z['status'] for z in a})==1
    if a[0]['value'] is None:continue
    truth=x[t-d-w:t-d].astype(float).mean(0)
    for z in a[1:]:
     assert np.allclose(z['value'],a[0]['value'],rtol=1e-12,atol=1e-12)
     assert np.all(np.abs(z['value']-truth)<=z['total_bound']+1e-14)
     assert (z['resolution']=='EXACT')==(a[0]['resolution']=='EXACT')
    assert np.array_equal(a[1]['bound'],a[2]['bound'])
   assert all(np.array_equal(s.q_delays,ss[1].q_delays) for s in ss[1:])
  for s in ss[1:]:
   z=type(s).loads(s.dumps());a=s.query(7,63,False);c=z.query(7,63,False)
   assert np.array_equal(a['value'],c['value']) and np.array_equal(a['total_bound'],c['total_bound'])
   if isinstance(z,CachedCertified):assert z.cache_hits==0

def test_fraction_containment_cancellation_extrema():
 counts=0
 for values in [[2**50,1,-2**50,1]*70,[0,0,0,1000]*70,[-7.]*280,[1e-35,-1e-35,1e-30,-1e-30]*70]:
  x=np.repeat(np.asarray(values,np.float32)[:,None],4,axis=1)
  for cls in [FusedCertified,CachedCertified]:
   s=cls(Config(budget=1000000,base_width=16,fine_width=4,overlay_capacity=2,max_reach=64))
   for t,row in enumerate(x,1):
    s.observe(row);s.actions.clear()
    if t<32 or t%7:continue
    for d,w in [(0,1),(0,9),(1,17),(3,29),(15,16)]:
     z=s.query(d,w,False);exact=sum((Fraction(float(v)) for v in x[t-d-w:t-d,0]),Fraction())/w
     error=abs(Fraction(float(z['value'][0]))-exact)
     assert error<=Fraction(float(z['total_bound'][0]));counts+=1
 assert counts>1000

def test_cache_invalidation_capacity_alias_and_history():
 cfg=Config(budget=1000000,base_width=32,fine_width=8,overlay_capacity=2,max_reach=128)
 s=CachedCertified(cfg)
 for t in range(200):s.observe(np.full(4,t,np.float32))
 a=s.query(0,17);expected=a['value'].copy();a['value'][:]=1e90;a['total_bound'][:]=0
 b=s.query(0,17);assert np.array_equal(b['value'],expected) and s.cache_hits==1
 assert s.q_pos==2
 for d in range(60):s.query(d,17)
 assert len(s.cache)==s.CAPACITY
 s.observe(np.full(4,999));assert len(s.cache)==0
 c=s.query(0,17);assert not np.array_equal(c['value'],expected)
 s.drop_overlay(int(s.overlay_ids[0]));assert not s.cache

def test_on_demand_values_have_no_certificate_claim():
 s=FusedCertified(Config());s.observe_many(np.ones((400,4),np.float32))
 a=s.query(3,63,certificate=False);b=s.query(3,63)
 assert np.array_equal(a['value'],b['value']) and a['bound'] is None and 'total_bound' not in a
