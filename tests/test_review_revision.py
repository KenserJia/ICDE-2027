from concurrent.futures import ThreadPoolExecutor
import numpy as np
from mtmemory_icde.core import CheckpointCoordinator, IntegratedService, TwoSlotStore


def test_capture_without_decode_keeps_concurrent_prefix_and_image(tmp_path):
    service = IntegratedService()
    service.initialize_facts(16)
    for i in range(600):
        service.observe(np.full(4, i, np.float32), count_ack=False)
    coordinator = CheckpointCoordinator(service, TwoSlotStore(tmp_path), 7,
                                        verify_capture=False)
    def writer(worker):
        for i in range(31):
            coordinator.mutate(lambda i=i: service.observe(np.full(4, i, np.float32)))
            coordinator.mutate(lambda i=i: service.put_fact(worker, np.full(4, i, np.float32)))
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(writer, range(4)))
    coordinator.close(force=True)
    _, blob, _ = coordinator.store.recover()
    recovered = IntegratedService.loads(blob)
    assert recovered.ack_seq == service.ack_seq == 248
    assert coordinator.maximum_gap <= 7
    assert np.array_equal(recovered.fact_versions, service.fact_versions)
    assert np.array_equal(recovered.fact_values, service.fact_values)
    assert np.allclose(recovered.query(0, 32, 64)['history']['value'],
                       service.query(0, 32, 64)['history']['value'])
