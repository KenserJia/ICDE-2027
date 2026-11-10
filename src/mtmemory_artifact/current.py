"""Current-paper evidence reconstruction and behavioral validation.

Recorded-data reconstruction does not remeasure service performance. Frozen
scientific modules and protocol drivers remain separate from artifact plumbing.
"""
from pathlib import Path
import csv,json,re,shutil,statistics as st
import numpy as np
from .io import ROOT,load_json
from .analysis import save

def _json(name,root):return load_json('results/'+name,root)
def _data_rows(text):return text.split(r'\midrule',1)[1].split(r'\bottomrule',1)[0]
def _write_table(out,root,name,rows):
    recorded=(root/'analysis/recorded'/name).read_text()
    body='\n'.join(' & '.join(row)+r'\\' for row in rows)+'\n'
    norm=lambda x:re.sub(r'\s+','',x)
    if norm(body)!=norm(_data_rows(recorded)):
        raise AssertionError(f'reconstructed cells do not match the paper: {name}')
    before,rest=recorded.split(r'\midrule',1);_,after=rest.split(r'\bottomrule',1)
    (out/name).write_text(before+'\\midrule\n'+body+'\\bottomrule'+after)

def tables(output,root=ROOT):
    out=Path(output).resolve()
    if out.exists():raise FileExistsError(out)
    out.mkdir(parents=True);L=lambda n:_json(n,root);checks={}
    rq2=L('review4_20261109/rq2_records.json');cells=[];records=[]
    for B in [65536,131072,262144]:
        values=[]
        for R in [8192,16384]:
            q=[x for x in rq2 if x['B']==B and x['R']==R and x['selected']];assert len(q)==39
            values.append(st.mean(x['metrics']['1/-1/-1']['nrmse'] for x in q))
        a,b=values;change='Higher error' if b>a+1e-12 else 'Tie' if abs(a-b)<=1e-12 else 'Slightly lower'
        cells.append([str(B//1024),f'{a:.5f}',f'{b:.5f}',change]);records.append(dict(KiB=B//1024,R8192=a,R16384=b))
    save(out,'table_I_reach',records);_write_table(out,root,'table_I_reach.tex',cells);checks['I']=True
    q=L('cert_age_slo_20261110/quality_records.json');fixed=L('cert_age_slo_20261110/FIXED_CONTROL.json');assert len(q)==780 and len(fixed)==228
    names={'recent':'Recent','sse':'SSE bins','bound':'Bound bins','fixed':'Fixed two-level','age':'Age rollup'};cells=[];records=[]
    for house in [False,True]:
        for B in [131072,262144]:
            for variant,label in names.items():
                pool=[x for x in q if (x['unit']==13)==house and x['B']==B and x['variant']==variant and x['prior']=='panels' and x['mode']=='sum' and x['objective']=='g01']
                old=[x for x in fixed if (x['unit']==13)==house and x['B']==B and x['variant']==variant and x['objective']=='g01']
                assert len(pool)==(1 if house else 13)
                G=st.mean(x['test']['all']['G']['0.1'] for x in pool);rmse=st.mean(x['test']['all']['nrmse'] for x in pool);charge=st.mean(x['config']['ledger']['charged_bytes']/1024 for x in pool)
                row=dict(source='Household' if house else 'Bike+Beijing',KiB=B//1024,variant=variant,G=G,nrmse=rmse,charge_kib=charge)
                if old:
                    row['span_G']=st.mean(x['metrics']['span']['all']['G']['0.1'] for x in old);row['fixed_sum_G']=st.mean(x['metrics']['sum']['all']['G']['0.1'] for x in old)
                    paired=f'{100*row["span_G"]:.2f} / {100*row["fixed_sum_G"]:.2f}'
                else:paired='--';row.update(span_G=None,fixed_sum_G=None)
                cells.append([row['source'],str(B//1024),label,paired,f'{100*G:.2f}',f'{rmse:.3f}',f'{charge:.2f}']);records.append(row)
    save(out,'table_II_certificate_age',records);_write_table(out,root,'cert_age_quality_table.tex',cells);checks['II']=True
    cells=[];records=[]
    for prior,label in [('panels','Equal panels'),('far_heavy','Far-heavy'),('uniform_reach','Uniform reach')]:
        row=dict(prior=prior)
        for variant in ['recent','age','sse']:
            x=next(x for x in q if x['unit']==13 and x['B']==262144 and x['prior']==prior and x['mode']=='sum' and x['objective']=='g01' and x['variant']==variant);row[variant]=100*x['test']['all']['G']['0.1']
        records.append(row);cells.append([label,*[f'{row[k]:.2f}' for k in ['recent','age','sse']]])
    save(out,'table_III_age_prior',records);_write_table(out,root,'age_prior_table.tex',cells);checks['III']=True
    faults=L('review7_20261109/fault_records.json');groups=[('Five commit-point stops',['after_partial_write','before_file_fsync','after_file_fsync','after_replace_before_dir_fsync','after_dir_fsync']),('Admission boundary',['boundary']),('Offset target',['random']),('Newest-slot corruption',['newest_corrupt']),('Both slots corrupt',['both_corrupt']),('Malformed service image',['semantic_invalid'])]
    descriptions=[r'Prior/new coherent prefix; loss $\leq K$.',r'Loss exactly $K$.',r'Loss 7--13; within $K$.',r'Older prefix; loss 199 at $K=100$.','Explicit rejection.','Explicit rejection.'];cells=[];records=[]
    for (label,modes),desc in zip(groups,descriptions):
        rows=[x for x in faults if x['mode'] in modes];loss=[x['loss'] for x in rows if 'loss' in x]
        records.append(dict(condition=label,cases=len(rows),minimum_loss=min(loss) if loss else None,maximum_loss=max(loss) if loss else None));cells.append([label,str(len(rows)),desc])
    assert [r['cases'] for r in records]==[135,27,27,9,9,9] and all(x.get('loss',0)<=x['K'] for x in faults if x.get('bound_claimed'))
    save(out,'table_IV_recovery',records);_write_table(out,root,'table_IV_recovery.tex',cells);checks['IV']=True
    cells=[];records=[]
    for name,label in [('cost_control_records','Short random'),('cost_wide_records','Wide recent')]:
        raw=L('review7_20261109/'+name+'.json')
        for mode,mode_label in [('sync','Sync'),('strict','Strict')]:
            values={m:st.median(x['throughput_rps'] for x in raw if x['method']==m and x['mode']==mode)/1000 for m in ['native','reference','fused']}
            cells.append([label,mode_label,*[f'{values[m]:.2f}' for m in ['native','reference','fused']]]);records.append(dict(intervals=label,checkpoint=mode,**values))
    save(out,'table_V_cost',records);_write_table(out,root,'table_V_cost.tex',cells);checks['V']=True
    raw=L('cert_age_slo_20261110/load_records.json');timely=L('cert_age_slo_20261110/TIMELY_COMPLETION.json');T={x['name']:x for x in timely['records']};assert len(raw)==len(T)==27
    cells=[];records=[]
    for rate in sorted({r['base'] for r in raw}):
        rendered=[]
        for method in ['recent','age','hist']:
            rows=[x for x in raw if x['base']==rate and x['method']==method];assert len(rows)==3
            feasible=all(x['scheduled_query_p99_ms']<=20 for x in rows);alpha=min(x['G01'] for x in rows) if feasible else None;t=st.median(T[x['name']]['timely_query_fraction_20ms'] for x in rows)
            rendered.append(('--' if alpha is None else f'{100*alpha:.2f}')+f'/{100*t:.2f}')
            records.append(dict(base=rate,burst=4*rate,method=method,alpha_max=alpha,T20=t,median_G=st.median(x['G01'] for x in rows),median_p99_ms=st.median(x['scheduled_query_p99_ms'] for x in rows),timely_certified_per_second=st.median(x['timely_goodput_20ms'] for x in rows)))
        cells.append([f'{rate/1000:g}/{4*rate/1000:g}',*rendered])
    save(out,'table_VI_joint_feasibility',records);_write_table(out,root,'joint_feasibility_table.tex',cells);checks['VI']=True
    # Also verify every claimed current run and keep exact failures in the source data.
    assert sum(x['requests'] for x in raw)==8019000 and sum(x['exact_oracle_checks'] for x in raw)==1545
    assert all(x['max_gap']<=500 and x['final_image_restored'] and x['source_cycles']==0 for x in raw)
    result=dict(passed=all(checks.values()),current_body_tables=list(checks),checks=checks,scientific_rerun=False,source='Complete recorded per-entity/per-run values; T20 comes from indexed per-run completion records, not new timing',rows_written=len(q),load_runs=len(raw))
    (out/'TABLE_CHECKS.json').write_text(json.dumps(result,indent=2)+'\n');return result

def figures(output):
    from .cli import workspace,execute
    out,work=workspace(output,['results/cert_age_slo_20261110/LOAD_SUMMARY.json','results/cert_age_slo_20261110/load_records.json'])
    commands=execute([dict(cwd='repro/framework_20261109',argv=['{python}','current.py']),dict(cwd='repro/cert_age_slo_20261110',argv=['{python}','plot_load_points.py'])],out,work)
    target=out/'figures';target.mkdir()
    for source,name in [(work/'paper/IEEE-conference-template-062824/figures/review7_framework/mtmemory_framework_en.pdf','framework.pdf'),(work/'paper/figures/cert_age_slo/quality_latency_points.pdf','quality_latency_points.pdf')]:shutil.copy2(source,target/name)
    result=dict(passed=True,figure_count=2,scientific_rerun=False,commands=commands,scope='Current framework diagram and all27 recorded paired load runs; regenerated font metrics may change pixels')
    (out/'RUN.json').write_text(json.dumps(result,indent=2)+'\n');return result

def smoke(output):
    from .checks import smoke as legacy_smoke
    from mtmemory_icde.core.evidence_service import EvidenceService
    from mtmemory_icde.core.rpo import CheckpointCoordinator
    from mtmemory_icde.core.checkpoint import TwoSlotStore
    import importlib.util
    out=Path(output).resolve();old=legacy_smoke(out);spec=importlib.util.spec_from_file_location('artifact_exact',ROOT/'repro/review7_20261109/exact.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    rows=np.load(ROOT/'data/real/bike.npz')['train_0'][:400];oracle=m.ExactPrefix(rows);cases=[]
    for family in ['recent','age','sse']:
        for mode in ['span','sum']:
            options=dict(base_width=32,fine_width=4,overlay_capacity=4,max_reach=128,budget=131072,certificate_mode=mode)
            if family=='recent':options.update(engine='certified',policy='recent')
            elif family=='age':options.update(engine='histogram',age_rollup=True,bins=1)
            else:options.update(engine='histogram',hist_variant='sse',bins=2)
            s=EvidenceService(**options);s.initialize_facts(16);co=CheckpointCoordinator(s,TwoSlotStore(out/f'{family}-{mode}'),17,verify_capture=False)
            for row in rows:co.mutate(lambda row=row:s.observe(row))
            for d,w in [(0,1),(0,17),(7,31),(31,63),(1,127)]:
                answer=s.query(3,d,w);h=answer['history'];assert h['status']=='ANSWERED';assert oracle.contains(400-d-w,400-d,h['value'],h['total_bound'])
            assert s.query(0,128,1)['history']['status']=='UNKNOWN';co.close();_,image,_=co.store.recover();restored=EvidenceService.loads(image)
            assert co.maximum_gap<=17 and all(np.array_equal(v,restored._arrays()[k]) for k,v in s._arrays().items())
            cases.append(dict(family=family,certificate=mode,queries=5,active_wrapped_restore=True,charge=s.account(len(image))['charged_bytes']))
    result=dict(passed=True,scientific_rerun=False,prior_service_cases=old['behavioral_cases'],current_certificate_cases=cases,certificate_checks=15+30,note='Fast behavior checks; no scientific throughput or long-run claim is inferred')
    (out/'SMOKE_CURRENT.json').write_text(json.dumps(result,indent=2)+'\n');return result


def audit_raw(output,root=ROOT):
    """Independently derive completion rates from all saved request arrays.

    Requires the matching raw Release archive. This checks recorded timings;
    it does not execute requests or make a new latency measurement.
    """
    from .io import record
    out=Path(output).resolve()
    if out.exists():raise FileExistsError(out)
    raw=_json('cert_age_slo_20261110/load_records.json',root)
    timely=_json('cert_age_slo_20261110/TIMELY_COMPLETION.json',root)
    expected={x['name']:x for x in timely['records']};records=[];requests=0
    for run in raw:
        name=run['name'];entry,path=record('results/cert_age_slo_20261110/load_runs/'+name+'/requests.npz',root)
        with np.load(path) as z:
            kind=z['kind'];latency=z['scheduled_latency_ms'];cert=z['certified'];q=kind==0
            assert len(kind)==run['requests'] and q.any()
            assert np.isfinite(latency).all()
            n=int(q.sum());t=float(np.mean(latency[q]<=20));g=float(np.mean(cert[q]));tc=float(np.mean((latency[q]<=20)&cert[q]));p99=float(np.percentile(latency[q],99))
            ref=expected[name]
            assert n==ref['queries']
            assert abs(t-ref['timely_query_fraction_20ms'])<=1e-12
            assert abs(tc-ref['timely_certified_query_fraction_20ms'])<=1e-12
            assert abs(g-run['G01'])<=1e-12
            assert abs(p99-run['scheduled_query_p99_ms'])<=1e-9
            records.append(dict(name=name,queries=n,timely_query_fraction_20ms=t,timely_certified_query_fraction_20ms=tc,G01=g,scheduled_query_p99_ms=p99))
            requests+=len(kind)
    assert len(records)==27 and requests==8019000
    out.mkdir(parents=True)
    result=dict(passed=True,scientific_rerun=False,run_count=len(records),requests=requests,denominator='all history queries including uncertified queries',latency='scheduled end-to-end including queue delay',records=records)
    (out/'RAW_COMPLETION_AUDIT.json').write_text(json.dumps(result,indent=2)+'\n')
    return dict(passed=True,scientific_rerun=False,run_count=len(records),requests=requests,report='RAW_COMPLETION_AUDIT.json')
