"""Rebuild the six body tables from recorded per-entity/per-run values."""
from pathlib import Path
import csv, io, json
from collections import Counter
import numpy as np
from .io import ROOT, load_json, read_bytes

def save(out, name, rows):
    with (out / (name + '.csv')).open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

def tables(output, root=ROOT):
    out = Path(output).resolve()
    if out.exists():
        raise FileExistsError(f'refusing to overwrite {out}')
    out.mkdir(parents=True)
    L = lambda n: load_json('results/' + n, root)
    checks = {}
    written = []
    rq2 = L('review4_20261109/rq2_records.json')
    t = []
    for B in [65536, 131072, 262144]:
        a = [r for r in rq2 if r['B'] == B and r['R'] == 8192 and r['selected']]
        b = [r for r in rq2 if r['B'] == B and r['R'] == 16384 and r['selected']]
        assert len(a) == len(b) == 39
        t.append(dict(KiB=B // 1024, R8192=float(np.mean([x['metrics']['1/-1/-1']['nrmse'] for x in a])), R16384=float(np.mean([x['metrics']['1/-1/-1']['nrmse'] for x in b]))))
    save(out, 'table_I_reach', t)
    checks['table_I'] = all((round(r['R8192'], 5) == x and round(r['R16384'], 5) == y for r, (x, y) in zip(t, [(0.19371, 0.2546), (0.0679, 0.0679), (0.02856, 0.02795)])))
    written.append('I')
    q = L('review7_20261109/quality_test.json')
    t = []
    for B in [131072, 262144]:
        for R in [4096, 16384]:
            for family in ['native', 'histogram']:
                r = [x for x in q if (x['B'], x['R'], x['family']) == (B, R, family)]
                assert len(r) == 13
                m = [x['metrics']['all'] for x in r]
                t.append(dict(KiB=B // 1024, R=R, family=family, nrmse=float(np.mean([x['nrmse'] for x in m])), exact_percent=100 * float(np.mean([x['exact_fraction'] for x in m])), normalized_bound=float(np.mean([x['mean_normalized_bound'] for x in m])), guaranteed_within_0_1=float(np.mean([x['guaranteed_within_0_1'] for x in m]))))
    save(out, 'table_II_joint_summary', t)
    checks['table_II'] = len(q) == 104 and sum((x['checks'] for x in q)) == 479232 and (sum((x['violations'] for x in q)) == 0)
    written.append('II')
    baseline = L('review4_20261109/baseline_records.json')
    t = []
    for B in [131072, 262144]:
        for method in ['certified', 'polynomial']:
            r = [x for x in baseline if (x['B'], x['R'], x['method']) == (B, 16384, method)]
            assert len(r) == 13
            t.append(dict(KiB=B // 1024, method=method, **{label: float(np.mean([x['metrics'][f'1/{i}/-1']['nrmse'] for x in r])) for i, label in enumerate(['near', 'middle', 'far'])}))
    save(out, 'table_III_history_model', t)
    checks['table_III'] = all((round(r['near'], 5) == x for r, x in zip(t, [0.06767, 0.24802, 0.06767, 0.16113])))
    written.append('III')
    entities = list(csv.DictReader(io.StringIO(read_bytes('results/review6_20261109/sensitivity_selected_entities.csv', root).decode())))
    t = []
    for label in ['stable', 'dynamic_dominant', 'critical', 'held12', 'held24', 'held28']:
        r = [x for x in entities if x['workload'] == label]
        assert len(r) == 13
        delta = [float(x['selected_mse']) - float(x['default_mse']) for x in r]
        t.append(dict(workload=label, default_mse=float(np.mean([float(x['default_mse']) for x in r])), selected_mse=float(np.mean([float(x['selected_mse']) for x in r])), better=sum((d < -1e-12 for d in delta)), tie=sum((abs(d) <= 1e-12 for d in delta)), worse=sum((d > 1e-12 for d in delta))))
    save(out, 'table_IV_score_selection', t)
    checks['table_IV'] = len(entities) == 78 and t[4]['worse'] == 9 and (round(t[4]['selected_mse'], 6) == 0.010642)
    written.append('IV')
    faults = L('review7_20261109/fault_records.json')
    t = []
    groups = [('Commit points', ['after_partial_write', 'before_file_fsync', 'after_file_fsync', 'after_replace_before_dir_fsync', 'after_dir_fsync']), ('Boundary', ['boundary']), ('Offset target', ['random']), ('Newest corrupt', ['newest_corrupt']), ('Both corrupt', ['both_corrupt']), ('Malformed format', ['semantic_invalid'])]
    for label, modes in groups:
        r = [x for x in faults if x['mode'] in modes]
        loss = [x['loss'] for x in r if 'loss' in x]
        t.append(dict(condition=label, cases=len(r), minimum_loss=min(loss) if loss else None, maximum_loss=max(loss) if loss else None, explicit_errors=sum(('explicit_failure' in x for x in r))))
    save(out, 'table_V_recovery', t)
    checks['table_V'] = [x['cases'] for x in t] == [135, 27, 27, 9, 9, 9] and all((x.get('loss', 0) <= x['K'] for x in faults if x.get('bound_claimed')))
    written.append('V')
    t = []
    for label, name in [('short', 'cost_control_records'), ('wide', 'cost_wide_records')]:
        data = L('review7_20261109/' + name + '.json')
        for mode in ['sync', 'strict']:
            vals = {m: float(np.median([x['throughput_rps'] for x in data if x['method'] == m and x['mode'] == mode])) / 1000 for m in ['native', 'reference', 'fused']}
            t.append(dict(intervals=label, checkpoint=mode, **vals, gain_percent=100 * (vals['fused'] / vals['reference'] - 1)))
    save(out, 'table_VI_certificate_cost', t)
    checks['table_VI'] = round(t[2]['gain_percent'], 1) == 62.7 and round(t[3]['gain_percent'], 1) == 60.2
    written.append('VI')
    raw = L('rq3_symmetric_20261107/selected_results.json')
    t = []
    for label in ['stable', 'critical', 'dynamic_dominant', 'held12', 'held24', 'held28']:
        r = [x for x in raw if x['profile'] == 'verified50924' and x['workload'] == label]
        recent = {(x['dataset'], x['entity']): x['mse'] for x in r if x['policy'] == 'recent'}
        online = {(x['dataset'], x['entity']): x['mse'] for x in r if x['policy'] == 'online'}
        ds = [online[k] - recent[k] for k in recent]
        t.append(dict(workload=label, recent_mse=float(np.mean(list(recent.values()))), online_mse=float(np.mean(list(online.values()))), dynamic_wins=sum((d < -1e-12 for d in ds)), recent_wins=sum((d > 1e-12 for d in ds)), ties=sum((abs(d) <= 1e-12 for d in ds))))
    save(out, 'rq3_paired', t)
    checks['rq3'] = t[2]['recent_wins'] == 13 and round(t[2]['online_mse'], 6) == 0.005816
    if not all(checks.values()):
        raise AssertionError(checks)
    result = dict(passed=True, reconstructed_tables=written, checks=checks, scientific_rerun=False, description='Recomputed manuscript tables from complete recorded entity/run values; not a new performance measurement.')
    (out / 'TABLE_CHECKS.json').write_text(json.dumps(result, indent=2) + '\n')
    return result
