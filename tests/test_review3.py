"""Numerical and admission-bound regressions for the review-3 changes."""
from fractions import Fraction
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys
import numpy as np
import pytest
from mtmemory_icde.core.certified import CertifiedHistory
from mtmemory_icde.core.history import Config
from mtmemory_icde.core.rpo import CheckpointCoordinator
from mtmemory_icde.core.checkpoint import TwoSlotStore
from mtmemory_icde.core.service import IntegratedService
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'repro/review3'))
from plato_range import PlatoRange

@pytest.mark.parametrize('kind',['native','plato0','plato1'])
def test_binary64_allowance_covers_exact_oracle_and_sealed_restore(kind):
    s=CertifiedHistory(Config(budget=131072,max_reach=128,base_width=32,fine_width=4,overlay_capacity=2)) if kind=='native' else PlatoRange(131072,16,int(kind[-1]),128)
    values=np.resize(np.array([2.**90,1.,-2.**90,2.**-90],np.float32),257)
    for x in values:s.observe(np.repeat(x,4))
    for d,w in [(0,1),(1,32),(4,63),(30,64),(0,128)]:
        a=s.query(d,w);truth=sum((Fraction(float(x)) for x in values[len(values)-d-w:len(values)-d]),Fraction(0))/w
        assert abs(Fraction(float(a['value'][0]))-truth)<=Fraction(float(a['total_bound'][0]))
        b=type(s).loads(s.dumps()).query(d,w)
        assert np.array_equal(a['value'],b['value'])
        assert np.array_equal(a['total_bound'],b['total_bound'])

@pytest.mark.parametrize('verify',[True,False])
def test_strict_stalls_at_budget_even_with_slow_commit(tmp_path,verify):
    service=IntegratedService();store=TwoSlotStore(tmp_path);c=CheckpointCoordinator(service,store,4,verify_capture=verify)
    entered=threading.Event();release=threading.Event();commit=store.commit
    def held(payload,*args,**kwargs):
        entered.set();assert release.wait(10);return commit(payload,*args,**kwargs)
    store.commit=held
    try:
        with ThreadPoolExecutor(max_workers=8) as pool:
            futures=[pool.submit(c.mutate,lambda:service.observe(np.ones(4))) for _ in range(8)]
            assert entered.wait(10)
            with c._cv:assert service.ack_seq-c.durable_seq==4
            release.set()
            for f in futures:f.result(timeout=10)
        c.close();_,payload,_=store.recover();assert IntegratedService.loads(payload).ack_seq==service.ack_seq
        assert c.maximum_gap<=4
    finally:
        release.set()
        if c.thread.is_alive():c.close()
