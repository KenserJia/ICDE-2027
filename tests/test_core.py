from __future__ import annotations

import tempfile

import numpy as np

from mtmemory_icde.core import CheckpointCoordinator, IntegratedService, TwoSlotStore
from mtmemory_icde.core.history import stream


def service_with_history() -> IntegratedService:
    service=IntegratedService();service.initialize_facts(16)
    for row in stream(11,640):service.observe(row,count_ack=False)
    return service


def test_integrated_service_roundtrip():
    service=service_with_history();service.put_fact(3,np.ones(4,np.float32))
    before=service.query(3,64,128);restored=IntegratedService.loads(service.dumps())
    after=restored.query(3,64,128)
    assert before["history"]["status"]==after["history"]["status"]=="ANSWERED"
    assert np.array_equal(before["fact"]["value"],after["fact"]["value"])
    assert restored.account(len(restored.dumps()))["within_budget"]


def test_two_slot_corruption_falls_back():
    with tempfile.TemporaryDirectory() as directory:
        store=TwoSlotStore(directory);store.commit(b"old",1);new=store.commit(b"new",2)
        path=store.paths[new["slot"]];path.write_bytes(path.read_bytes()[:9])
        generation,payload,audit=store.recover()
        assert (generation,payload)==(1,b"old")
        assert audit["invalid"]


def test_strict_rpo_gap_is_bounded():
    with tempfile.TemporaryDirectory() as directory:
        service=service_with_history();coordinator=CheckpointCoordinator(service,TwoSlotStore(directory),4,True)
        for index in range(13):
            row=np.full(4,index,np.float32)
            coordinator.mutate(lambda row=row:service.observe(row))
        coordinator.close(force=True)
        assert coordinator.maximum_gap<=4
