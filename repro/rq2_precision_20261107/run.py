"""Frozen, uniform-granularity native RQ2 extension; no test selection."""
from __future__ import annotations
from collections import defaultdict
from pathlib import Path
import argparse, csv, hashlib, json, platform, sys, time
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'src'))
sys.path.insert(0,str(ROOT/'repro/round78_rq_closure'))
import run as old
from mtmemory_icde.core.history import Config, TieredOverlayStore
BUDGETS=(65536,131072,262144)
REACHES=(512,1024,2048,4096,8192,16384)
WIDTHS=(8,16,32,64,128)
OUT=ROOT/'results/rq2_precision_20261107'
M=6144

def write(path,obj):
    path.write_text(json.dumps(obj,indent=2,ensure_ascii=False,allow_nan=False)+'\n')
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def adjusted(s):
    a=s.account();a['native_charged_bytes']=a['charged_bytes'];a['native_metadata_bytes']=a['metadata_bytes']
    a['metadata_bytes']=M;a['snapshot_slot_bytes']=a['resident_array_bytes']+M
    a['charged_bytes']=3*(a['resident_array_bytes']+M)+a['workspace_bytes']
    return a

def make(r,h,budget=max(BUDGETS)):
    return TieredOverlayStore(Config(budget=budget,channels=4,base_width=h,fine_width=h,max_reach=r,overlay_capacity=0,policy='none',query_history=128))

def cell_oracle(rows,t,d,w,h):
    # Independent reconstruction of the native prorated SUM/COUNT estimator.
    # For the active partial cell, preserve its actual count and native h divisor.
    lo=t-d-w;hi=t-d;total=np.zeros(4);count=0.
    for bid in range(lo//h,(hi-1)//h+1):
        left=bid*h;right=min(t,left+h)
        overlap=max(0,min(hi,right)-max(lo,left))
        cell=rows[left:right].astype(np.float64)
        total+=(overlap/h)*cell.sum(axis=0)
        count+=(overlap/h)*len(cell)
    return total/count

def controls():
    # Small deterministic real prefix, including active and sealed cells.
    rows=old.all_split_units()[0][2][:1500]
    cases=0;maxdiff=0.;max_excess=0
    for h in WIDTHS:
        for budget in BUDGETS:
            s=make(512,h,budget);ref=make(512,h,max(BUDGETS))
            for t,row in enumerate(rows,1):
                s.observe(row);ref.observe(row)
                if t not in (511,512,513,777,1024,1499,1500):continue
                for d,w in ((0,1),(1,7),(7,32),(127,128),(256,256)):
                    if d+w>min(t,512):continue
                    a=s.query(d,w,record=False);b=ref.query(d,w,record=False)
                    assert a['status']=='ANSWERED' and np.array_equal(a['value'],b['value'])
                    oracle=cell_oracle(rows,t,d,w,h);diff=float(np.max(np.abs(a['value']-oracle)));maxdiff=max(maxdiff,diff)
                    assert np.allclose(a['value'],oracle,rtol=2e-13,atol=2e-13)
                    restored=TieredOverlayStore.loads(s.dumps());c=restored.query(d,w,record=False)
                    assert np.array_equal(a['value'],c['value'])
                    cases+=1
            a=adjusted(s);max_excess=max(max_excess,len(s.dumps())-a['snapshot_slot_bytes'])
            assert len(s.dumps())<=a['snapshot_slot_bytes']
    return dict(cases=cases,maximum_oracle_abs_difference=maxdiff,cap_predictions_identical=True,restored_predictions_identical=True,snapshot_excess=max_excess)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--unit',type=int);args=parser.parse_args()
    OUT.mkdir(exist_ok=True);(OUT/'units').mkdir(exist_ok=True)
    units=old.all_split_units();specs=[]
    for r in REACHES:
        for h in WIDTHS:
            s=make(r,h,10000000);a=adjusted(s)
            for budget in BUDGETS:specs.append(dict(reach=r,h=h,budget_bytes=budget,feasible=a['charged_bytes']<=budget,**{k:v for k,v in a.items() if k!='budget_bytes'}))
    write(OUT/'grid.json',specs)
    hashes={str(p.relative_to(ROOT)):sha(p) for p in [ROOT/'data/real/bike.npz',ROOT/'data/real/beijing.npz',ROOT/'src/mtmemory_icde/core/history.py',ROOT/'repro/round78_rq_closure/run.py',Path(__file__),ROOT/'results/frozen/rq_closure/rq2_range/raw.json',ROOT/'results/review_revision_20261104/range_training_variance_raw.json']}
    write(OUT/'protocol.json',dict(budgets=BUDGETS,reaches=REACHES,widths=WIDTHS,metadata_reserve=M,seed=old.SEED,bootstrap_resamples=5000,normalization='sqrt(per-entity test MSE / mean training channel variance)',selection='none: widths fixed before test',query_schedule='original range_queries, every=128',hashes=hashes,python=sys.version,numpy=np.__version__,platform=platform.platform(),machine=platform.machine()))
    if args.unit is None:write(OUT/'controls.json',controls())
    for ui,(dataset,entity,train,validation,test) in enumerate(units):
        if args.unit is not None and args.unit!=ui:continue
        dest=OUT/'units'/f'{ui:02d}.json'
        if dest.exists():print(f'resume {ui}',flush=True);continue
        started=time.perf_counter();rows=np.concatenate([train,validation,test]);v=float(np.var(train.astype(np.float64),axis=0).mean());assert np.isfinite(v) and v>0
        stores={(r,h):make(r,h) for r in REACHES for h in WIDTHS if next(x for x in specs if x['reach']==r and x['h']==h)['charged_bytes']<=max(BUDGETS)}
        by_t=defaultdict(list);firstlast={};schedules={}
        for r in REACHES:
            for stage,start,end,seed in [('validation',len(train),len(train)+len(validation),old.SEED+ui*17),('test',len(train)+len(validation),len(rows),old.SEED+ui*17+19)]:
                qs=old.range_queries(start,end,r,seed,128);assert qs
                schedules[f'{r}-{stage}']=qs;firstlast[r,stage]=(qs[0]['t'],qs[-1]['t'])
                for q in qs:
                    assert 0<=q['t']-q['delay']-q['window'] and q['delay']+q['window']<=r
                    by_t[q['t']].append((r,stage,q))
        meta=[];preds=[];truths=[];stages=[];stats=defaultdict(lambda:dict(errors=[],queries=0,answered=0));oracle_cases=0;max_oracle=0.
        for t,row in enumerate(rows,1):
            for s in stores.values():s.observe(row)
            for r,stage,q in by_t.get(t,()):
                truth=rows[t-q['delay']-q['window']:t-q['delay']].astype(np.float64).mean(axis=0)
                for h in WIDTHS:
                    s=stores.get((r,h))
                    if s is None:continue
                    a=s.query(q['delay'],q['window']);st=stats[r,h,stage];st['queries']+=1
                    assert a['status']=='ANSWERED' and np.all(np.isfinite(a['value']))
                    st['answered']+=1;st['errors'].append(float(np.mean((a['value']-truth)**2)))
                    meta.append([r,h,t,q['delay'],q['window'],int(t-q['delay']>((t-1)//h)*h)]);stages.append(0 if stage=='validation' else 1);preds.append(a['value']);truths.append(truth)
                    if t in firstlast[r,stage]:
                        oracle=cell_oracle(rows,t,q['delay'],q['window'],h);diff=float(np.max(np.abs(a['value']-oracle)));max_oracle=max(max_oracle,diff)
                        assert np.allclose(a['value'],oracle,rtol=2e-13,atol=2e-13);oracle_cases+=1
        result=[];serial=[]
        for (r,h),s in stores.items():
            a=adjusted(s);payload=len(s.dumps());assert payload<=a['snapshot_slot_bytes']
            serial.append(dict(reach=r,h=h,actual_npz_bytes=payload,reserved_slot_bytes=a['snapshot_slot_bytes'],native_slot_bytes=s.account()['snapshot_slot_bytes']))
            for stage in ('validation','test'):
                st=stats[r,h,stage];mse=float(np.mean(st['errors']));assert st['answered']==st['queries']>0
                result.append(dict(dataset=dataset,entity=entity,reach=r,h=h,stage=stage,queries=st['queries'],answered=st['answered'],coverage=1.,mse=mse,nrmse=float(np.sqrt(mse/v)),training_variance=v,charged_bytes=a['charged_bytes']))
        np.savez_compressed(OUT/'units'/f'{ui:02d}_queries.npz',metadata=np.array(meta,np.int64),stage=np.array(stages,np.int8),prediction=np.array(preds),truth=np.array(truths))
        write(dest,dict(dataset=dataset,entity=entity,rows=result,snapshot_checks=serial,query_schedules=schedules,oracle_checks=oracle_cases,oracle_max_abs_difference=max_oracle,elapsed_seconds=time.perf_counter()-started))
        print(f'unit {ui+1}/13 {dataset}/{entity}: {len(meta)} unique query-method cases, {time.perf_counter()-started:.1f}s',flush=True)
    if args.unit is not None:return
    records=[json.loads((OUT/'units'/f'{i:02d}.json').read_text()) for i in range(13)]
    raw=[row for x in records for row in x['rows']];write(OUT/'entity_results.json',raw)
    summary=[]
    for spec in specs:
        vals=[x for x in raw if x['reach']==spec['reach'] and x['h']==spec['h'] and x['stage']=='test'] if spec['feasible'] else []
        assert len(vals)==13 if spec['feasible'] else not vals
        ys=[v['nrmse'] for v in vals]
        summary.append(dict(budget_bytes=spec['budget_bytes'],reach=spec['reach'],h=spec['h'],feasible=spec['feasible'],charged_bytes=spec['charged_bytes'],entities=len(vals),test_queries=sum(v['queries'] for v in vals),coverage_min=min(v['coverage'] for v in vals) if vals else None,nrmse_mean=float(np.mean(ys)) if ys else None,bootstrap95=old.bootstrap_ci(ys) if ys else None))
    write(OUT/'summary.json',summary)
    fields=['budget_KiB','reach','h','status','charged_bytes','entities','test_queries','coverage_min','test_nrmse','ci95_low','ci95_high']
    with (OUT/'source_data.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
        for x in summary:w.writerow(dict(budget_KiB=x['budget_bytes']//1024,reach=x['reach'],h=x['h'],status='feasible' if x['feasible'] else 'over_budget',charged_bytes=x['charged_bytes'],entities=x['entities'],test_queries=x['test_queries'],coverage_min=x['coverage_min'],test_nrmse=x['nrmse_mean'],ci95_low=x['bootstrap95'][0] if x['bootstrap95'] else None,ci95_high=x['bootstrap95'][1] if x['bootstrap95'] else None))
    with (OUT/'entity_source_data.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(raw[0]));w.writeheader();w.writerows(raw)
    counts={stage:sum(r['queries'] for r in raw if r['stage']==stage) for stage in ('validation','test')}
    write(OUT/'QA.json',dict(entities=13,grid_points=len(summary),feasible_points=sum(x['feasible'] for x in summary),infeasible_points=sum(not x['feasible'] for x in summary),unique_query_method_counts=counts,budget_expanded_test_cases=sum(x['test_queries'] for x in summary),oracle_checks=sum(x['oracle_checks'] for x in records),oracle_max_abs_difference=max(x['oracle_max_abs_difference'] for x in records),all_feasible_coverage_one=all(x['coverage_min']==1 for x in summary if x['feasible']),all_ledger_checks_pass=all(x['charged_bytes']<=x['budget_bytes'] for x in summary if x['feasible']),all_serialization_checks_pass=True,snapshot_checks=sum(len(x['snapshot_checks']) for x in records),original_hashes_unchanged=all(sha(ROOT/p)==h for p,h in hashes.items()),snapshot_reserve_min_margin=min(s['reserved_slot_bytes']-s['actual_npz_bytes'] for x in records for s in x['snapshot_checks']),limitations=['Single macOS/arm64 host','13 entities including 12 correlated stations','Controlled original RQ2 schedule; queried history changes with R','Uniform b=f=h, no overlays: not the original tuned-layout frontier','6 KiB metadata reserve differs from original 4 KiB; old results untouched','Ledger is not a RAM cap','No test-selected configuration; no monotonicity or universality claim']))
    print(json.dumps(json.loads((OUT/'QA.json').read_text()),indent=2),flush=True)
if __name__=='__main__':main()
