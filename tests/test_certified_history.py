import numpy as np,pytest
from mtmemory_icde.core.certified import CertifiedHistory
from mtmemory_icde.core.history import Config

def test_certificates_cover_misalignment_active_cells_eviction_and_restore():
 rng=np.random.default_rng(93)
 for signal in [rng.normal(size=(353,4)),np.where(np.arange(353)[:,None]%31<3,100.,-7.)*np.ones((353,4))]:
  signal=signal.astype('float32');s=CertifiedHistory(Config(budget=131072,max_reach=256,base_width=64,fine_width=8,overlay_capacity=2,policy='error'))
  for t,row in enumerate(signal,1):
   s.observe(row)
   if t%17!=0:continue
   for d in [0,1,9,35]:
    for w in [1,3,8,31,64,127]:
     if d+w>min(t,256):continue
     a=s.query(d,w);truth=signal[t-d-w:t-d].astype('float64').mean(0)
     assert np.all(np.abs(a['value']-truth)<=a['bound']+1e-10)
  r=CertifiedHistory.loads(s.dumps())
  for d,w in [(0,7),(3,65),(90,129)]:
   a=s.query(d,w);b=r.query(d,w);assert np.array_equal(a['value'],b['value']);assert np.array_equal(a['bound'],b['bound'])
  assert s.account()['certificate_array_bytes']>0
  assert s.query(0,257)['status']=='UNKNOWN'
  with pytest.raises(NotImplementedError):s.delete_event(10)
  with pytest.raises(NotImplementedError):s.promote_from_replay(1)
