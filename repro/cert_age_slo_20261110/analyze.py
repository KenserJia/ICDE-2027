from pathlib import Path
import json,statistics as st,csv
import numpy as np
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'results/cert_age_slo_20261110';PAPER=ROOT/'paper'
NAMES={'recent':'Recent','sse':'SSE bins','bound':'Bound bins','fixed':'Fixed two-level','age':'Age rollup'}
def write(p,x):p.write_text(json.dumps(x,indent=2,allow_nan=False)+'\n')
def main():
    records=json.loads((OUT/'quality_records.json').read_text());fixed=json.loads((OUT/'FIXED_CONTROL.json').read_text());matched=json.loads((OUT/'MATCHED_AGE.json').read_text())
    rows=[]
    for domain in ['original','household']:
        for B in [131072,262144]:
            for variant in NAMES:
                pool=[r for r in records if (r['unit']==13)==(domain=='household') and r['B']==B and r['variant']==variant and r['prior']=='panels' and r['mode']=='sum' and r['objective']=='g01']
                old=[r for r in fixed if (r['unit']==13)==(domain=='household') and r['B']==B and r['variant']==variant and r['objective']=='g01']
                row=dict(domain=domain,B=B,variant=variant,n=len(pool),retuned_G=st.mean(x['test']['all']['G']['0.1'] for x in pool),retuned_nrmse=st.mean(x['test']['all']['nrmse'] for x in pool),charge_kib=st.mean(x['config']['ledger']['charged_bytes']/1024 for x in pool))
                if old:row.update(fixed_span_G=st.mean(x['metrics']['span']['all']['G']['0.1'] for x in old),fixed_sum_G=st.mean(x['metrics']['sum']['all']['G']['0.1'] for x in old))
                rows.append(row)
    write(OUT/'QUALITY_SUMMARY.json',rows)
    tex=[r'\begin{table*}[t]\centering\small',r'\caption{Same-statistic certificate and age-allocation controls. Fixed span/sum uses layouts frozen in the preceding study; sum retuned independently maximizes validation $G(.1)$ in each family. All cells report test results. Original is a descriptive macro mean over 13 units from two sources; Household is the third source. The newly added age rollup has no preceding-study selection. Budgets 128/256 KiB use $R=4096/16{,}384$.}\label{tab:certage}',r'\begin{tabular}{@{}lrlrrrr@{}}\toprule',r'Source & KiB & Representation & Fixed span/sum $G(.1)$ (\%) & Retuned sum $G(.1)$ (\%) & NRMSE & Charge (KiB)\\\midrule']
    for x in rows:
        control=f'{100*x["fixed_span_G"]:.2f} / {100*x["fixed_sum_G"]:.2f}' if 'fixed_span_G' in x else '--'
        tex.append(' & '.join([x['domain'].capitalize(),str(x['B']//1024),NAMES[x['variant']],control,f'{100*x["retuned_G"]:.2f}',f'{x["retuned_nrmse"]:.3f}',f'{x["charge_kib"]:.2f}'])+r'\\')
    tex.append(r'\bottomrule\end{tabular}\end{table*}');(PAPER/'cert_age_quality_table.tex').write_text('\n'.join(tex)+'\n')
    prior_rows=[]
    for kind in ['panels','far_heavy','uniform_reach']:
        row=dict(prior=kind)
        for variant in ['recent','age','sse']:
            x=next(x for x in records if x['unit']==13 and x['B']==262144 and x['prior']==kind and x['variant']==variant and x['mode']=='sum' and x['objective']=='g01')
            row[variant]=dict(id=x['id'],G=x['test']['all']['G']['0.1'],nrmse=x['test']['all']['nrmse'],groups=x['test'])
        prior_rows.append(row)
    write(OUT/'PRIOR_SUMMARY.json',prior_rows)
    tex=[r'\begin{table}[t]\centering\small',r'\caption{Household age-prior sensitivity, 256 KiB/$R=16{,}384$, sum-aware certificates. Each family is independently validation-selected for each prior. Entries are test $G(.1)$ percentages; far-heavy samples near/middle/far with probabilities .1/.1/.8. Uniform reach samples valid ages across the full reach.}\label{tab:ageprior}',r'\begin{tabular}{@{}lrrr@{}}\toprule',r'Prior & Recent & Age rollup & SSE bins\\\midrule']
    for row in prior_rows:
        label={'panels':'Equal panels','far_heavy':'Far-heavy','uniform_reach':'Uniform reach'}[row['prior']]
        tex.append(' & '.join([label,*[f'{100*row[v]["G"]:.2f}' for v in ['recent','age','sse']]])+r'\\')
    tex.append(r'\bottomrule\end{tabular}\end{table}');(PAPER/'age_prior_table.tex').write_text('\n'.join(tex)+'\n')
    matched_summary=dict(cases=len(matched),max_abs_G_difference=max(abs(x['recent']['all']['G']['0.1']-x['age']['all']['G']['0.1']) for x in matched),max_abs_nrmse_difference=max(abs(x['recent']['all']['nrmse']-x['age']['all']['nrmse']) for x in matched),age_minus_recent_charge_bytes_range=[min(x['age_charge']-x['recent_charge'] for x in matched),max(x['age_charge']-x['recent_charge'] for x in matched)])
    write(OUT/'MATCHED_SUMMARY.json',matched_summary)
    if not (OUT/'load_records.json').exists():
        print('Quality tables ready; load points pending');return
    raw=json.loads((OUT/'load_records.json').read_text());assert len(raw)==27
    timely=[]
    for x in raw:
        with np.load(OUT/'load_runs'/x['name']/'requests.npz') as z:
            q=z['kind']==0;on_time=z['scheduled_latency_ms']<=20
            assert int(q.sum())==x['queries'] and np.isfinite(z['scheduled_latency_ms']).all()
            x['timely_query_fraction_20ms']=float(on_time[q].mean())
            x['timely_certified_query_fraction_20ms']=float((on_time&z['certified'])[q].mean())
            timely.append({k:x[k] for k in ['name','method','rep','base','queries','timely_query_fraction_20ms','timely_certified_query_fraction_20ms']})
    write(OUT/'TIMELY_COMPLETION.json',dict(denominator='all history queries, including uncertified queries',deadline_ms=20,latency='scheduled end-to-end latency including queue delay',records=timely))
    summary=[]
    for rate in sorted({x['base'] for x in raw}):
        for method in ['recent','age','hist']:
            q=[x for x in raw if x['base']==rate and x['method']==method];assert len(q)==3
            keys=['G01','timely_query_fraction_20ms','timely_certified_query_fraction_20ms','timely_goodput_20ms','scheduled_query_p99_ms','max_sampled_backlog','sampled_peak_rss_mib','seconds_including_request_drain']
            center={k:st.median(x[k] for x in q) for k in keys};bounds={k:[min(x[k] for x in q),max(x[k] for x in q)] for k in keys}
            passed=sum(x['scheduled_query_p99_ms']<=20 for x in q)
            summary.append(dict(base=rate,burst=4*rate,method=method,median=center,range=bounds,tail_feasible_repeats=passed,alpha_max=min(x['G01'] for x in q) if passed==3 else None))
    write(OUT/'LOAD_SUMMARY.json',summary)
    with (OUT/'LOAD_SOURCE_DATA.csv').open('w',newline='') as f:
        keys=['method','rep','base','burst','requests','seconds_including_request_drain','G01','timely_query_fraction_20ms','timely_certified_query_fraction_20ms','timely_goodput_20ms','scheduled_query_p99_ms','max_gap','max_sampled_backlog','sampled_peak_rss_mib']
        w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows({k:r[k] for k in keys} for r in raw)
    tex=[r'\begin{table*}[t]\centering\small',r'\caption{Complete paired Household load points with sum-aware certificates, 256 KiB/$R=16{,}384$, eight clients and strict $K=500$. All layouts are selected only by validation $G(.1)$. Each point has three 60 s technical runs with two 5 s fourfold bursts. Cells are medians [full ranges]. Timely goodput counts individually certified completions within 20 ms; it does not imply whole-query tail feasibility. $\alpha_{\max}$ is the minimum observed $G(.1)$ only when all three whole-query p99 values meet 20 ms; otherwise the tested point has no jointly feasible $\alpha$.}\label{tab:loadpointsfull}',r'\begin{tabular}{@{}rrlrrrr@{}}\toprule',r'Base & Burst & Layout & $G(.1)$ (\%) & Timely (k/s) & Scheduled p99 (ms) & $\alpha_{\max}$ (\%)\\\midrule']
    for x in summary:
        a=x['median'];r=x['range'];label={'recent':'Recent','age':'Age rollup','hist':'SSE bins'}[x['method']]
        def fmt(k,scale):return f'{a[k]*scale:.2f} [{r[k][0]*scale:.2f},{r[k][1]*scale:.2f}]'
        tex.append(' & '.join([str(x['base']),str(x['burst']),label,fmt('G01',100),fmt('timely_goodput_20ms',.001),fmt('scheduled_query_p99_ms',1),'--' if x['alpha_max'] is None else f'{100*x["alpha_max"]:.2f}'])+r'\\')
    tex.append(r'\bottomrule\end{tabular}\end{table*}');(PAPER/'load_points_table.tex').write_text('\n'.join(tex)+'\n')
    tex=[r'\begin{table}[t]\centering\small',r'\caption{Joint feasibility and timely completion, sum-aware certificates. Cells are $\alpha_{\max}/T_{20}$ (\%): minimum certified fraction when all three p99 values meet 20 ms (-- if infeasible), and median percentage of all queries completed within 20 ms, including uncertified queries. Rates are base/burst in thousands/s. Figure~\ref{fig:loadpoints} reports the other metrics.}\label{tab:loadpoints}',r'\begin{tabular}{@{}lrrr@{}}\toprule',r'Load (k/s) & Recent & Age rollup & SSE bins\\\midrule']
    for rate in sorted({x['base'] for x in summary}):
        q=[next(x for x in summary if x['base']==rate and x['method']==m) for m in ['recent','age','hist']]
        cells=[('--' if x['alpha_max'] is None else f'{100*x["alpha_max"]:.2f}')+f'/{100*x["median"]["timely_query_fraction_20ms"]:.2f}' for x in q]
        tex.append(' & '.join([f'{rate/1000:g}/{4*rate/1000:g}',*cells])+r'\\')
    tex.append(r'\bottomrule\end{tabular}\end{table}');(PAPER/'joint_feasibility_table.tex').write_text('\n'.join(tex)+'\n')
    print('All quality and paired-load summaries generated')
if __name__=='__main__':main()
