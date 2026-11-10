"""Fresh-workspace execution of registered experiments."""
from pathlib import Path
import json, os, shutil, subprocess, sys
from .io import ROOT, materialize

def catalog(root=ROOT):
    return json.loads((root / 'experiments/catalog.json').read_text())['experiments']

def write(p, x):
    Path(p).write_text(json.dumps(x, indent=2) + '\n')

def workspace(output, inputs=(), evidence_all=False):
    out = Path(output).expanduser().resolve()
    if out.exists():
        raise FileExistsError(f'refusing to overwrite existing output: {out}')
    for p in [ROOT / n for n in ['src', 'data', 'evidence', 'repro', 'figures', 'provenance', 'analysis', 'experiments', 'docs', 'licenses', 'tests', 'third_party']]:
        if p.resolve() == out or p.resolve() in out.parents:
            raise ValueError('output must not be inside packaged inputs')
    out.mkdir(parents=True)
    work = out / 'workspace'
    work.mkdir()
    for name in ['src', 'repro']:
        shutil.copytree(ROOT / name, work / name, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    shutil.copytree(ROOT / 'data/real', work / 'data/real')
    for name in ['review7_20261109', 'review6_20261109', 'review4_20261109', 'review3_20261104', 'review2_20261104', 'review_revision_20261104', 'rq3_symmetric_20261107', 'rq2_precision_20261107', 'rq2_tradeoff_20261107', 'review4_paper_20261109', 'review7_paper_20261109', 'framework_20261109', 'w2w3_20261110', 'w1w4_20261110', 'cert_age_slo_20261110']:
        (work / 'results' / name).mkdir(parents=True, exist_ok=True)
    (work / 'paper/IEEE-conference-template-062824/figures').mkdir(parents=True)
    if evidence_all:
        materialize(work)
    elif inputs:
        materialize(work, inputs)
    return (out, work)

def execute(commands, out, work):
    env = os.environ.copy()
    env['MTMEM_ICDE_ROOT'] = str(work)
    env['PYTHONPATH'] = str(work / 'src')
    env['MPLCONFIGDIR'] = str(out / 'mpl-cache')
    records = []
    for n, cmd in enumerate(commands, 1):
        argv = [t.replace('{python}', sys.executable) for t in cmd['argv']]
        cwd = work / cmd['cwd']
        cwd.mkdir(parents=True, exist_ok=True)
        log = out / f'command-{n:02d}.log'
        print(f"{n}/{len(commands)}: {cmd['cwd']}/{argv[1]} (log: {log.name})", flush=True)
        with log.open('w') as f:
            p = subprocess.run(argv, cwd=cwd, env=env, stdout=f, stderr=subprocess.STDOUT)
        records.append(dict(argv=argv, cwd=cmd['cwd'], returncode=p.returncode, log=log.name))
        write(out / 'RUN.json', dict(status='failed' if p.returncode else 'running', commands=records))
        if p.returncode:
            raise RuntimeError(f'command failed; inspect {log}')
    return records

def run(id, output):
    spec = next((x for x in catalog() if x['id'] == id), None)
    if not spec:
        raise ValueError(id)
    out, work = workspace(output, spec['reference_inputs'])
    write(out / 'PROTOCOL.json', spec)
    commands = execute(spec['commands'], out, work)
    result = dict(status='complete', experiment=id, scientific_rerun=True, workspace='workspace', commands=commands, comparison='Compare deterministic quality/counts to recorded evidence; remeasure performance, do not expect timing equality.')
    write(out / 'RUN.json', result)
    return result

def legacy_figures(output):
    needed = ['results/review4_20261109/rq2_records.json', 'results/rq3_symmetric_20261107/summary.json', 'results/rq3_symmetric_20261107/selected_results.json', 'results/rq3_symmetric_20261107/layouts.json', 'results/rq3_symmetric_20261107/same_layout_summary.json', 'results/frozen/rq_closure/rq3_boundary/calibration_summary.json', 'results/review7_20261109/performance_records.json', 'results/review7_20261109/cost_control_records.json', 'results/review7_20261109/cost_wide_records.json']
    out, work = workspace(output, needed)
    commands = execute([dict(cwd='repro/review4_paper_20261109', argv=['{python}', 'figures.py']), dict(cwd='repro/rq3_symmetric_20261107', argv=['{python}', 'figures.py']), dict(cwd='repro/review7_paper_20261109', argv=['{python}', 'figures.py'])], out, work)
    src = work / 'paper/IEEE-conference-template-062824/figures'
    target = out / 'figures'
    target.mkdir()
    paths = ['review4_rq2.pdf', 'rq3_symmetric_scope.pdf', 'review7_joint_operating.pdf', 'review7_framework/mtmemory_framework_en.pdf']
    for n in paths:
        for ext in ['.pdf', '.svg', '.png']:
            p = (src / n).with_suffix(ext)
            if p.exists():
                shutil.copy2(p, target / ('framework' + ext if '/mtmemory' in n else p.name))
    result = dict(status='complete', figure_count=4, commands=commands, scientific_rerun=False, note='Rebuild from recorded scientific values; no remeasurement. Font/platform differences may change pixels.')
    write(out / 'RUN.json', result)
    return result
