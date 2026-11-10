from pathlib import Path
import json,statistics,itertools,sys
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'results/w1w4_20261110';PAPER=ROOT/'paper' if (ROOT/'paper/IEEE-conference-template-062824.tex').exists() else ROOT/'paper/IEEE-conference-template-062824'
def write(p,x):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,indent=2,allow_nan=False)+'\n')
def main():
 r=json.loads((OUT/'quality_records.json').read_text());names={'recent':'Recent','sse':'SSE bins','bound':'Bound bins','fixed':'Fixed two-level'};summary=[]
 for B,domain,v,obj in itertools.product([131072,262144],['original','household'],names,['mse','g01']):
  q=[x for x in r if x['B']==B and (x['dataset']=='household')==(domain=='household') and x['variant']==v and x['objective']==obj]
  summary.append(dict(B=B,domain=domain,variant=v,objective=obj,n=len(q),G=statistics.mean(x['test']['G']['0.1'] for x in q),nrmse=statistics.mean(x['test']['nrmse'] for x in q),bound=statistics.mean(x['test']['bound'] for x in q),charge_kib=statistics.mean(x['config']['ledger']['charged_bytes']/1024 for x in q)))
 tex=[r'\begin{table*}[t]\centering\small',r'\caption{Stronger contract-matched representations. Each pair is validation-MSE / validation-$G(.1)$ selection on random-start/width test queries. Original averages the 13 entities from two sources; Household is the independent third source. Budgets 128/256 KiB use reach 4096/16,384. Bound bins optimize a fixed-prior mean-bound surrogate.}\label{tab:strong}',r'\begin{tabular}{@{}lr l rrr@{}}\toprule',r'Source & KiB & Representation & $G(.1)$ (\%) & NRMSE & Bound ($G$-selected)\\\midrule']
 for domain in ['original','household']:
  for B in [131072,262144]:
   for v,name in names.items():
    a,b=[next(x for x in summary if (x['B'],x['domain'],x['variant'],x['objective'])==(B,domain,v,obj)) for obj in ['mse','g01']]
    tex.append(' & '.join([domain.capitalize(),str(B//1024),name,f'{100*a["G"]:.2f} / {100*b["G"]:.2f}',f'{a["nrmse"]:.3f} / {b["nrmse"]:.3f}',f'{b["bound"]:.3f}'])+r'\\')
 tex.append(r'\bottomrule\end{tabular}\end{table*}');(PAPER/'w1_strong_table.tex').write_text('\n'.join(tex)+'\n')
 transfer=[x for x in r if x['dataset']=='household' and x['objective'] in ['frozen_rule','validation_global']]
 tex=[r'\begin{table}[t]\centering\small',r'\caption{Frozen configuration rule on Household. Rule coefficients use only the original domains; Household training roughness and the declared query geometry are inputs. Validation-global searches all four families on Household validation. No Household result fits the rule.}\label{tab:transfer}',r'\begin{tabular}{@{}rllrr@{}}\toprule',r'KiB & Selector & $(b,f,k)$ & $G(.1)$ (\%) & NRMSE\\\midrule']
 for x in transfer:
  o=x['config']['options'];tex.append(' & '.join([str(x['B']//1024),'Frozen' if x['objective']=='frozen_rule' else 'Validation',f'{o["base_width"]},{o["fine_width"]},{o["overlay_capacity"]}',f'{100*x["test"]["G"]["0.1"]:.2f}',f'{x["test"]["nrmse"]:.3f}'])+r'\\')
 tex.append(r'\bottomrule\end{tabular}\end{table}');(PAPER/'w4_transfer_table.tex').write_text('\n'.join(tex)+'\n')
 app=json.loads((OUT/'APPLICATION.json').read_text());longprotocol=json.loads((OUT/'LONG_PROTOCOL.json').read_text());selected=[x for x in app['records'] if x['id'] in [c['id'] for c in longprotocol['choices'].values()] and x['B']==262144]
 tex=[r'\begin{table}[t]\centering\small',r'\caption{Application examples at three prespecified Household prefixes. Recent / validation-selected SSE bins, 256 KiB. Nine queries per width use current and lagged intervals. $G$ is a percentage and includes input-conversion allowance in kW. Tolerances are sensitivity settings, not production SLOs.}\label{tab:power}',r'\begin{tabular}{@{}lrrr@{}}\toprule',r'Window & $G(.05\,\mathrm{kW})$ & $G(.1\,\mathrm{kW})$ & $G(.2\,\mathrm{kW})$\\\midrule']
 for w,name in [(60,'Hour'),(1440,'Day'),(10080,'Week')]:
  cols=[name]
  for eps in [.05,.1,.2]:
   vals=[]
   for key in ['recent','strong']:
    item=next(x for x in selected if x['id']==longprotocol['choices'][key]['id']);q=[x for x in item['queries'] if x['window_minutes']==w];vals.append(sum(x['bound_kw']<=eps for x in q)/len(q)*100)
   cols.append(f'{vals[0]:.1f} / {vals[1]:.1f}')
  tex.append(' & '.join(cols)+r'\\')
 tex.append(r'\bottomrule\end{tabular}\end{table}');(PAPER/'w4_power_table.tex').write_text('\n'.join(tex)+'\n')
 result=dict(quality=summary,transfer=transfer,application=app,oracle=json.loads((OUT/'EXACT_AUDIT.json').read_text()))
 if (OUT/'long_records.json').exists() or '--primary' in sys.argv:
  long=json.loads((OUT/'long_records.json').read_text()) if (OUT/'long_records.json').exists() else [json.loads(p.read_text()) for p in (OUT/'longrun').glob('*-10min/result.json')];result['long_records']=long;rows=[]
  for method in ['recent','strong']:
   q=[x for x in long if x['method']==method and x['duration']==600];assert len(q)==3
   rows.append(dict(method=method,median={k:statistics.median(x[k] for x in q) for k in ['throughput','G01','certified_goodput','timely_goodput_20ms','scheduled_query_p99_ms','max_backlog','max_rss_mib']},range={k:[min(x[k] for x in q),max(x[k] for x in q)] for k in ['G01','timely_goodput_20ms','scheduled_query_p99_ms','max_backlog','max_rss_mib']}))
  result['long_summary']=rows
  tex=[r'\begin{table*}[t]\centering\small',r'\caption{Sustained Household load, 256 KiB/$R=16,384$, strict $K=500$. Three ten-minute runs per method include two ten-second arrival bursts. Cells are median [full range]; goodput is thousands/s. Scheduled p99 includes backlog; backlog/RSS are sampled each second.}\label{tab:sustained}',r'\begin{tabular}{@{}lrr@{}}\toprule',r'Metric & Recent & SSE bins\\\midrule']
  for k,label,scale in [('G01',r'$G(.1)$ (\%)',.01),('timely_goodput_20ms','Timely certified/s',1000),('scheduled_query_p99_ms','Scheduled p99 (ms)',1),('max_backlog','Sampled max backlog',1),('max_rss_mib','Sampled peak RSS (MiB)',1)]:
   spec='.0f' if k=='max_backlog' else '.2f'
   values=[f'{x["median"][k]/scale:{spec}} [{x["range"][k][0]/scale:{spec}},{x["range"][k][1]/scale:{spec}}]' for x in rows];tex.append(' & '.join([label,*values])+r'\\')
  tex.append(r'\bottomrule\end{tabular}\end{table*}');(PAPER/'w4_long_table.tex').write_text('\n'.join(tex)+'\n')
 write(OUT/'SUMMARY.json',result)
 print('quality/transfer/application tables generated; primary timing complete:', len(result.get('long_records',[]))>=6, '; thirty-minute run complete:', len(result.get('long_records',[]))==7)
if __name__=='__main__':main()
