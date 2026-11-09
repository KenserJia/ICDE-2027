import numpy as np
from mtmemory_icde.core.history import Config,TieredOverlayStore
from mtmemory_icde.core.certified import CertifiedHistory

def test_populated_active_cell_crossing_has_correct_weight():
    # A sealed cell has mean0, active populated singleton has mean80.
    # Nominal-width prorating would give the singleton weight1/8 instead of1.
    s=TieredOverlayStore(Config(base_width=16,fine_width=8,overlay_capacity=2,max_reach=64))
    for value in [0]*16+[80]:s.observe(np.full(4,value))
    a=s.query(0,9,False)
    assert a['resolution']=='EXACT'
    assert np.allclose(a['value'],80/9,rtol=0,atol=1e-14)
    z=TieredOverlayStore.loads(s.dumps())
    assert np.array_equal(z.query(0,9,False)['value'],a['value'])

def test_native_and_certificate_agree_on_active_support():
    rng=np.random.default_rng(9)
    cfg=Config(base_width=32,fine_width=8,overlay_capacity=2,max_reach=128)
    a=TieredOverlayStore(cfg);b=CertifiedHistory(cfg)
    rows=rng.normal(size=(333,4)).astype(np.float32)
    for i,row in enumerate(rows,1):
        a.observe(row);b.observe(row)
        for d,w in [(0,1),(0,17),(1,31),(7,63)]:
            if d+w>min(i,128):continue
            x=a.query(d,w,False);y=b.query(d,w,False)
            assert np.allclose(x['value'],y['value'],rtol=1e-12,atol=1e-12)
            assert (x['resolution']=='EXACT')==(y['resolution']=='EXACT')


def test_declared_reach_rejects_ring_padding_and_invalid_intervals():
    s=TieredOverlayStore(Config(base_width=32,fine_width=8,overlay_capacity=2,max_reach=64))
    for i in range(200):s.observe(np.full(4,i))
    for d,w in [(64,1),(0,65),(-1,3),(0,0),(0,-1)]:
        ans=s.query(d,w,False)
        assert ans['status']=='UNKNOWN' and ans['value'] is None
    assert s.query(0,64,False)['status']=='ANSWERED'
