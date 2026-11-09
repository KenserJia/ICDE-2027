from pathlib import Path
import sys,json,argparse,hashlib
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'repro/review_revision')]
import performance as harness
OUT=ROOT/'results/review3_20261104'

def main():
    p=argparse.ArgumentParser();p.add_argument('--operations',type=int,default=1000000);args=p.parse_args()
    workloads=json.loads((ROOT/'results/frozen/rq_closure/rq3_boundary/RQ3_FREEZE.json').read_text())['workloads']
    jobs=[dict(workload=label,spec=v['spec'],allocation=a,variant=d,seed=seed) for seed in (0,1,2) for label,v in workloads.items() for a in ('fixed','dynamic') for d in ('sync','original','optimized')]
    np.random.default_rng(20261104).shuffle(jobs)
    freeze=OUT/'PERFORMANCE_FREEZE.json'
    if not freeze.exists():harness.old.write_json(freeze,dict(operations=args.operations,clients=8,warmup=20000,K=500,order=jobs,harness_sha256=hashlib.sha256((ROOT/'repro/review_revision/performance.py').read_bytes()).hexdigest()))
    else:assert json.loads(freeze.read_text())['operations']==args.operations
    harness.old.write_json(OUT/'performance_environment.json',harness.old.environment())
    rows=harness.old.all_split_units(5)[-1][-1];raw=[]
    for j,job in enumerate(jobs):
        label,a,v,seed=job['workload'],job['allocation'],job['variant'],job['seed']
        case=OUT/'performance'/f'{label}-{a}-{v}-s{seed}'
        if (case/'result.json').exists():r=json.loads((case/'result.json').read_text())
        else:r=harness.one(case,rows,job['spec'],a,'sync' if v=='sync' else 'strict',20261104+seed*211,8,args.operations,False,v!='optimized')
        r.update(workload=label,variant=v,paired_seed=seed);raw.append(r)
        harness.old.write_json(OUT/'performance_raw.json',raw)
        print(j+1,len(jobs),label,a,v,seed,round(r['throughput_ops_s']),round(r['latency_ms']['p99_9'],3),flush=True)
    summary=[]
    for label in workloads:
        for a in ('fixed','dynamic'):
            for v in ('sync','original','optimized'):
                group=[r for r in raw if (r['workload'],r['allocation'],r['variant'])==(label,a,v)]
                base={r['paired_seed']:r for r in raw if (r['workload'],r['allocation'],r['variant'])==(label,a,'sync')}
                summary.append(dict(workload=label,allocation=a,variant=v,n=len(group),throughput=float(np.median([r['throughput_ops_s'] for r in group])),p99_9_ms=float(np.median([r['latency_ms']['p99_9'] for r in group])),throughput_paired_ratio=float(np.median([r['throughput_ops_s']/base[r['paired_seed']]['throughput_ops_s'] for r in group])),tail_paired_ratio=float(np.median([r['latency_ms']['p99_9']/base[r['paired_seed']]['latency_ms']['p99_9'] for r in group]))))
    harness.old.write_json(OUT/'performance_summary.json',summary)
if __name__=='__main__':main()
