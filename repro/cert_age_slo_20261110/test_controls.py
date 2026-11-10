from pathlib import Path
import sys,itertools
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'src'));sys.path.insert(0,str(ROOT/'repro/review7_20261109'))
from exact import ExactPrefix
from mtmemory_icde.core.numerics import certified_mean
from mtmemory_icde.core.sum_aware import sum_aware_mean
from mtmemory_icde.core.evidence_service import EvidenceService

def test_sum_aware_exhaustive_subsets_and_rounding():
    signals=[np.asarray(x,np.float32) for x in itertools.product([-3.,0.,7.],repeat=4)]
    signals += [np.array([2**24,1,-2**24,1],np.float32),np.array([1e30,-1e30,1e-30,-1e-30],np.float32),np.array([1e-40,2e-40,-1e-40,0],np.float32)]
    for x in signals:
        for r in [1,2,3,4]:
            for ids in itertools.combinations(range(4),r):
                order=[*ids,*[i for i in range(4) if i not in ids]]
                rows=np.repeat(x[order,None],4,axis=1);s=rows.astype(float).sum(0)
                cells=[(0,4,s,rows.min(0).astype(float),rows.max(0).astype(float))]
                old=certified_mean(iter(cells),0,r,4,4);new=sum_aware_mean(iter(cells),0,r,4,4)
                assert np.array_equal(old['value'],new['value'])
                assert np.all(new['total_bound']<=old['total_bound'])
                assert ExactPrefix(rows).contains(0,r,new['value'],new['total_bound'])

def test_sum_aware_uses_sum_without_state():
    x=np.repeat(np.array([0,10,10,10],np.float32)[:,None],4,1)
    cells=[(0,4,x.astype(float).sum(0),x.min(0).astype(float),x.max(0).astype(float))]
    a=certified_mean(iter(cells),0,2,4,4);b=sum_aware_mean(iter(cells),0,2,4,4)
    assert np.allclose(a['bound'],5) and np.allclose(b['bound'],2.5)
    assert np.all(b['total_bound']<a['total_bound'])

def test_sum_aware_multicell_adversarial_sequential_sums():
    rng=np.random.default_rng(99173);sizes=[127,128,64,15];n=sum(sizes)
    x=(rng.choice([-1.,1.],size=(n,4))*np.exp2(rng.integers(-120,121,size=(n,4)))).astype(np.float32)
    x[:,0]=np.resize(np.array([1e30,1,-1e30,1e-30],np.float32),n)
    x[:,1]=np.resize(np.array([2**24,1,-2**24,1],np.float32),n)
    cells=[];start=0
    for m in sizes:
        rows=x[start:start+m];s=np.zeros(4)
        for row in rows:s+=row
        cells.append((start,m,s,rows.min(0).astype(float),rows.max(0).astype(float)));start+=m
    oracle=ExactPrefix(x)
    for lo in [0,1,63,126,127,129]:
        for hi in [130,190,255,300,n]:
            if hi<=lo:continue
            a=certified_mean(iter(cells),lo,hi,4,512);b=sum_aware_mean(iter(cells),lo,hi,4,512)
            assert np.array_equal(a['value'],b['value'])
            assert np.all(b['total_bound']<=a['total_bound'])
            assert oracle.contains(lo,hi,b['value'],b['total_bound'])

def test_live_controls_wrapping_active_restore_and_continue():
    rng=np.random.default_rng(309);rows=rng.normal(size=(1701,4)).astype(np.float32)
    specs=[dict(engine='certified',fine_width=8,overlay_capacity=4),dict(engine='histogram',bins=2),dict(engine='histogram',bins=1,fine_width=8,overlay_capacity=4,age_rollup=True)]
    for spec in specs:
        a=EvidenceService(**spec,base_width=128,max_reach=512,budget=262144,certificate_mode='span')
        b=EvidenceService(**spec,base_width=128,max_reach=512,budget=262144,certificate_mode='sum')
        a.initialize_facts(128);b.initialize_facts(128)
        for t,row in enumerate(rows,1):
            a.observe(row);b.observe(row)
            if t not in [127,128,129,901,1025,1701]:continue
            assert a.account()['array_bytes']==b.account()['array_bytes']
            assert a.account()['charged_bytes']==b.account()['charged_bytes']
            for d,w in [(0,17),(0,60),(1,31),(59,63),(256,127),(300,100)]:
                if d+w>t:continue
                ha=a.query(0,d,w)['history'];hb=b.query(0,d,w)['history']
                assert np.array_equal(ha['value'],hb['value'])
                assert np.all(hb['total_bound']<=ha['total_bound'])
                assert ExactPrefix(rows[t-d-w:t-d]).contains(0,w,hb['value'],hb['total_bound'])
            image=b.dumps();z=EvidenceService.loads(image)
            assert b._arrays().keys()==z._arrays().keys()
            assert all(np.array_equal(b._arrays()[k],z._arrays()[k]) for k in b._arrays())
            assert z.account(len(image))['snapshot_fits']
            b=z

def test_matched_rollup_age_support_and_estimates():
    rows=np.random.default_rng(812).normal(size=(1801,4)).astype(np.float32)
    for k in [0,2,4]:
        a=EvidenceService(engine='certified',base_width=128,fine_width=8,overlay_capacity=k,max_reach=1024,budget=262144,certificate_mode='sum')
        b=EvidenceService(engine='histogram',bins=1,age_rollup=True,base_width=128,fine_width=8,overlay_capacity=k,max_reach=1024,budget=262144,certificate_mode='sum')
        for t,row in enumerate(rows,1):
            a.observe(row);b.observe(row)
            if t not in [127,128,129,1300,1801]:continue
            for d,w in [(0,60),(1,31),(300,100),(700,128)]:
                if d+w>t:continue
                cells_a=list(a.history._cells(t-d-w,t-d));cells_b=list(b.history._cells(t-d-w,t-d))
                assert [(x[0],x[1]) for x in cells_a]==[(x[0],x[1]) for x in cells_b]
                ha=a.query(0,d,w)['history'];hb=b.query(0,d,w)['history']
                assert np.allclose(ha['value'],hb['value'],rtol=0,atol=1e-14)
                assert np.allclose(ha['total_bound'],hb['total_bound'],rtol=0,atol=1e-13)
