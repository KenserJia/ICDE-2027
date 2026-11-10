"""Generate every new manuscript number from retained records."""
from pathlib import Path
import json,statistics,itertools
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'results/w2w3_20261110'
PAPER=ROOT/'paper' if (ROOT/'paper/IEEE-conference-template-062824.tex').exists() else ROOT/'paper/IEEE-conference-template-062824'
def write(path,x):path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(x,indent=2,allow_nan=False)+'\n')
def avg(xs):return statistics.mean(xs)
def median(xs):return statistics.median(xs)
def main():
 quality=json.loads((OUT/'quality_records.json').read_text());perf=json.loads((OUT/'performance_records.json').read_text())
 protocol=json.loads((OUT/'PERFORMANCE_PROTOCOL.json').read_text());assert len(perf)==len(protocol['jobs'])
 summary=[]
 for B,R,prot,obj in itertools.product([131072,262144],[4096,16384],['mixed','random_phase','random_uniform'],['mse','g01','bound']):
  for group in (['all','aligned','unaligned'] if prot=='mixed' else ['all']):
   rr=[x for x in quality if (x['B'],x['R'],x['protocol'],x['objective'])==(B,R,prot,obj)]
   item=dict(B=B,R=R,protocol=prot,objective=obj,group=group)
   for family in ['native','histogram']:
    ff=[x for x in rr if x['family']==family];assert len(ff)==13
    item[family]={k:avg([x['test'][group][k] for x in ff]) for k in ['coverage','nrmse','exact','bound']}
    for metric in ['G','U']:item[family][metric]={eps:avg([x['test'][group][metric][eps] for x in ff]) for eps in ['0.01','0.05','0.1','0.2']}
   a=sorted([x for x in rr if x['family']=='native'],key=lambda x:x['unit']);b=sorted([x for x in rr if x['family']=='histogram'],key=lambda x:x['unit'])
   item['native_g01_wins_ties_losses']=[sum((u['test'][group]['G']['0.1']-v['test'][group]['G']['0.1'])>1e-12 for u,v in zip(a,b)),sum(abs(u['test'][group]['G']['0.1']-v['test'][group]['G']['0.1'])<=1e-12 for u,v in zip(a,b)),sum((u['test'][group]['G']['0.1']-v['test'][group]['G']['0.1']) < -1e-12 for u,v in zip(a,b))]
   summary.append(item)
 stats=[]
 keys=sorted(set((x['cid'],x['mode'],x['rate']) for x in perf))
 metrics=['throughput','G01','certified_goodput','certified_goodput_5ms','certified_goodput_20ms','query_p99_ms','scheduled_query_p99_ms','scheduled_query_p999_ms','backlog_drain_seconds','final_checkpoint_drain_seconds','checkpoint_bytes']
 for cid,mode,rate in keys:
  rr=sorted([x for x in perf if (x['cid'],x['mode'],x['rate'])==(cid,mode,rate)],key=lambda x:x['rep']);assert len(rr)==3
  stats.append(dict(cid=cid,mode=mode,rate=rate,config=rr[0]['config'],metrics={m:dict(median=median([x[m] for x in rr]),min=min(x[m] for x in rr),max=max(x[m] for x in rr)) for m in metrics}))
 def get(B,R,prot,obj,group='all'):return next(x for x in summary if (x['B'],x['R'],x['protocol'],x['objective'],x['group'])==(B,R,prot,obj,group))
 tex=[]
 tex.append(r'\begin{table*}[t]\centering\small'+'\n'+r'\caption{Alignment and selection-objective controls at 256 KiB and $R=16{,}384$. Entries are Recent / block V-optimal, macro means over all 13 entities. $G$ is the percentage of all requests certified within the stated normalized tolerance. Both families independently select on validation by MSE, $G(0.1)$, or mean bound. Aligned/irregular rows split the original mixed MSE-selected test requests without reselection.}\label{tab:alignment}\begin{tabular}{@{}llrrrrrr@{}}\toprule'+'\n'+r'Demand & Selection & NRMSE & Exact (\%) & $G(.01)$ & $G(.05)$ & $G(.1)$ & $G(.2)$\\\midrule')
 rows=[('Mixed: aligned','mixed','mse','aligned'),('Mixed: irregular','mixed','mse','unaligned')]+[(label,p,o,'all') for p,label in [('mixed','Mixed'),('random_phase','Random phase'),('random_uniform','Random width/start')] for o in ['mse','g01','bound']]
 for label,p,o,g in rows:
  x=get(262144,16384,p,o,g);a=x['native'];b=x['histogram'];selector={'mse':'MSE','g01':r'$G(.1)$','bound':'Bound'}[o]
  cols=[label,selector,f'{a["nrmse"]:.3f} / {b["nrmse"]:.3f}',f'{100*a["exact"]:.2f} / {100*b["exact"]:.2f}']+[f'{100*a["G"][e]:.2f} / {100*b["G"][e]:.2f}' for e in ['0.01','0.05','0.1','0.2']]
  tex.append(' & '.join(cols)+r'\\')
 tex.append(r'\bottomrule\end{tabular}\end{table*}')
 (PAPER/'w2_alignment_table.tex').write_text('\n'.join(tex)+'\n')
 def cost(ui,B,R,family,obj,mode,rate):
  return next(x for x in stats if x['config']['unit']==ui and x['config']['B']==B and x['config']['R']==R and x['config']['family']==family and obj in x['config']['objectives'] and x['mode']==mode and x['rate']==rate)
 def pair(ui,B,R,obj,mode,rate,metric,scale=1,dec=1):
  vals=[cost(ui,B,R,f,obj,mode,rate)['metrics'][metric]['median']/scale for f in ['native','histogram']]
  return ' / '.join(f'{v:.{dec}f}' for v in vals)
 tex=[r'\begin{table*}[t]\centering\small',r'\caption{Same-contract real-data closed-loop comparison. Recent / block V-optimal medians of three runs, eight clients, 95\% queries, $K=500$. Layouts are frozen independently by validation MSE or $G(.1)$. Goodput is thousands of certified-within-.1 queries per second; p99 is query latency in ms. Each run has 30,000 requests. The 128/256 KiB cases use $R=4096/16{,}384$, respectively.}\label{tab:goodput}',r'\begin{tabular}{@{}lllrrrr@{}}\toprule',r'KiB & Data & Selection & Sync goodput & Strict goodput & Sync p99 & Strict p99\\\midrule']
 closed=[]
 for B,R in [(131072,4096),(262144,16384)]:
  for ui,ds in [(0,'Bike'),(1,'Beijing-0')]:
   for obj in ['mse','g01']:
    tex.append(' & '.join([str(B//1024),ds,'MSE' if obj=='mse' else r'$G(.1)$',pair(ui,B,R,obj,'sync',0,'certified_goodput',1000,2),pair(ui,B,R,obj,'strict',0,'certified_goodput',1000,2),pair(ui,B,R,obj,'sync',0,'query_p99_ms',1,2),pair(ui,B,R,obj,'strict',0,'query_p99_ms',1,2)])+r'\\')
    for mode in ['sync','strict']:
     a=cost(ui,B,R,'native',obj,mode,0);b=cost(ui,B,R,'histogram',obj,mode,0)
     closed.append(dict(unit=ui,B=B,R=R,objective=obj,mode=mode,native_goodput=a['metrics']['certified_goodput']['median'],histogram_goodput=b['metrics']['certified_goodput']['median'],ratio=a['metrics']['certified_goodput']['median']/b['metrics']['certified_goodput']['median']))
 tex.append(r'\bottomrule\end{tabular}\end{table*}');(PAPER/'w3_goodput_table.tex').write_text('\n'.join(tex)+'\n')
 tex=[r'\begin{table*}[t]\centering\small',r'\caption{Paced certified service, four-second arrivals and three runs per cell. Recent / block V-optimal medians, $G(.1)$-selected configurations, eight clients and $K=500$. p99 includes scheduled waiting and backlog. Timely goodput counts certified-within-.1 queries completed within 20 ms, in thousands/s. All arrivals drain; rates are thousands of total requests/s. Cases use the same reach/budget as Table~\ref{tab:goodput}.}\label{tab:paced}',r'\begin{tabular}{@{}llrrrr@{}}\toprule',r'KiB/data & Rate & Sync p99 (ms) & Strict p99 (ms) & Sync timely goodput & Strict timely goodput\\\midrule']
 paced=[]
 for B,R in [(131072,4096),(262144,16384)]:
  for ui,ds in [(0,'Bike'),(1,'Beijing-0')]:
   for rate in [5000,20000]:
    tex.append(' & '.join([f'{B//1024}/{ds}',str(rate//1000),pair(ui,B,R,'g01','sync',rate,'scheduled_query_p99_ms',1,2),pair(ui,B,R,'g01','strict',rate,'scheduled_query_p99_ms',1,2),pair(ui,B,R,'g01','sync',rate,'certified_goodput_20ms',1000,2),pair(ui,B,R,'g01','strict',rate,'certified_goodput_20ms',1000,2)])+r'\\')
    for mode in ['sync','strict']:
     a=cost(ui,B,R,'native','g01',mode,rate);b=cost(ui,B,R,'histogram','g01',mode,rate)
     paced.append(dict(unit=ui,B=B,R=R,mode=mode,rate=rate,native=a['metrics'],histogram=b['metrics']))
 tex.append(r'\bottomrule\end{tabular}\end{table*}');(PAPER/'w3_paced_table.tex').write_text('\n'.join(tex)+'\n')
 counts=dict(choices=len(quality),exact_oracle_quality_queries=sum(json.loads(f.read_text())['exact_oracle_queries'] for f in (OUT/'test').glob('*.json')),timing_runs=len(perf),timing_requests=sum(x['N'] for x in perf),timing_oracle_checks=sum(x['exact_oracle_checks'] for x in perf),max_gap=max(x['max_gap'] for x in perf),full_array_restores=all(x['restored_all_arrays'] for x in perf),all_budget_checks=all(x['ledger']['within_budget'] and x['ledger']['snapshot_fits'] for x in perf))
 write(OUT/'SUMMARY.json',dict(counts=counts,quality=summary,performance=stats,closed_comparisons=closed,paced_comparisons=paced))
 print(json.dumps(counts,indent=2));print('closed goodput ratios min/max',min(x['ratio'] for x in closed),max(x['ratio'] for x in closed))
 print((PAPER/'w3_goodput_table.tex').read_text());print((PAPER/'w3_paced_table.tex').read_text())
if __name__=='__main__':main()
