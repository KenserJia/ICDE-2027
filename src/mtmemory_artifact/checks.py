"""Fast behavioral smoke checks, distinct from the full experiment protocols."""
from pathlib import Path
import json, importlib.util, sys
import numpy as np
from .io import ROOT

def smoke(output):
    out = Path(output).resolve()
    if out.exists():
        raise FileExistsError(out)
    out.mkdir(parents=True)
    import mtmemory_icde
    if not Path(mtmemory_icde.__file__).resolve().is_relative_to(ROOT):
        raise RuntimeError('an external source checkout was imported')
    from mtmemory_icde.core.joint import JointService
    from mtmemory_icde.core.checkpoint import TwoSlotStore
    from mtmemory_icde.core.rpo import CheckpointCoordinator
    sp = importlib.util.spec_from_file_location('smoke_exact', ROOT / 'repro/review7_20261109/exact.py')
    m = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(m)
    raw = np.load(ROOT / 'data/real/bike.npz')['train_0'][:400]
    oracle = m.ExactPrefix(raw)
    cases = []
    for engine, cache in [('certified', 0), ('certified', 32), ('histogram', 0)]:
        s = JointService(engine=engine, cache_capacity=cache, base_width=32, fine_width=4, overlay_capacity=4, max_reach=128, bins=3)
        s.initialize_facts(16)
        store = TwoSlotStore(out / f'{engine}-{cache}')
        c = CheckpointCoordinator(s, store, 17, verify_capture=False)
        for row in raw:
            c.mutate(lambda row=row: s.observe(row))
        checked = 0
        for delay, width in [(0, 1), (0, 17), (7, 31), (31, 63), (1, 127)]:
            a = s.query(3, delay, width)
            h = a['history']
            assert h['status'] == 'ANSWERED' and m.ExactPrefix.contains(oracle, len(raw) - delay - width, len(raw) - delay, h['value'], h['total_bound'])
            checked += 1
        assert s.query(0, 128, 1)['history']['status'] == 'UNKNOWN'
        c.close()
        _, blob, info = store.recover()
        restored = JointService.loads(blob)
        assert restored.ack_seq == s.ack_seq and c.maximum_gap <= 17
        assert all((np.array_equal(a, b) for a, b in zip(s._arrays().values(), restored._arrays().values())))
        if hasattr(restored.history, 'cache'):
            assert len(restored.history.cache) == 0
        latest = store.paths[info['slot']]
        data = bytearray(latest.read_bytes())
        data[len(data) // 2] ^= 1
        latest.write_bytes(data)
        _, old, _ = store.recover()
        prior = JointService.loads(old)
        assert prior.ack_seq <= restored.ack_seq
        cases.append(dict(engine=engine, cache=cache, certificate_checks=checked, full_array_restore=True, corruption_fallback=True, charged_bytes=s.account(len(blob))['charged_bytes']))
    result = dict(passed=True, scientific_rerun=False, behavioral_cases=cases, source_import='packaged checkout', note='Smoke checks validate interfaces, data access, certificates, snapshots and fallback; full protocol counts are not inferred from this test.')
    (out / 'SMOKE.json').write_text(json.dumps(result, indent=2) + '\n')
    return result
