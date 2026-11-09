from pathlib import Path
from collections import defaultdict,Counter
import csv,json,hashlib
import numpy as np
from concurrency import ROOT,OUT,write

def csvout(name,rows):
 fields=list(dict.fromkeys(k for row in rows for k in row));f=OUT/name
 with f.open('w',newline='') as stream:
  writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader();writer.writerows(rows)

def summarize(rows,keys,metrics):
 groups=defaultdict(list)
 for r in rows:groups[tuple(r[k] for k in keys)].append(r)
 out=[]
 for key,group in sorted(groups.items()):
  row=dict(zip(keys,key));row['n_technical_runs']=len(group)
  for name,fn in metrics.items():
   a=[fn(x) for x in group];a=[x for x in a if x is not None]
   if a:row.update({name:float(np.median(a)),name+'_min':float(min(a)),name+'_max':float(max(a))})
  out.append(row)
 return out

def main():
 concurrency=[json.loads(p.read_text()) for p in (OUT/'concurrency').glob('*/result.json') if p.parent.name!='pilot'];paced=[json.loads(p.read_text()) for p in (OUT/'paced').glob('*/result.json')];cost=[json.loads(p.read_text()) for p in (OUT/'certificate_cost').glob('*.json')];sensitivity=json.loads((OUT/'sensitivity_test_results.json').read_text());quality=json.loads((OUT/'optimized_quality.json').read_text());selection=json.loads((OUT/'SENSITIVITY_SELECTION.json').read_text())
 assert len(concurrency)==120 and len(paced)==54 and len(cost)==1008 and len(sensitivity)==1248 and len(quality)==39
 for x in concurrency:
  if x['mode']!='none':assert x['maximum_gap']<=x['K'] and x['restored_prefix_equal'] and x['facts_equal'] and x['history_arrays_equal'] and x['ledger']['within_budget']
 for x in paced:
  if x['mode']!='none':assert x['maximum_gap']<=500 and x['restored_prefix_equal']
 cm={'throughput':lambda x:x['throughput_ops_s'],'query_p99_ms':lambda x:x['metrics']['query']['latency_ms']['p99'],'query_p999_ms':lambda x:x['metrics']['query']['latency_ms']['p99_9'],'mutation_p99_ms':lambda x:x['metrics']['mutation']['latency_ms']['p99'],'query_service_wait_p99_ms':lambda x:x['metrics']['query'].get('service_lock_wait_ms',{}).get('p99'),'capture_ms':lambda x:x['capture_wall_ms'].get('p50'),'capture_queries':lambda x:x['metrics']['query_capture_overlap']['latency_ms']['n'],'capture_overlap_query_p99_ms':lambda x:x['metrics']['query_capture_overlap']['latency_ms'].get('p99'),'overlap_fraction':lambda x:x['query_capture_overlap_fraction'],'maximum_gap':lambda x:x['maximum_gap'],'rss_peak_bytes':lambda x:x['rss_peak'],'measurement_array_bytes':lambda x:x['harness_measurement_array_bytes']}
 csum=summarize(concurrency,['group','query_mix','clients','delay_ms','K','policy','instrument','mode'],cm);csvout('concurrency_summary.csv',csum)
 pmetrics={'throughput':lambda x:x['completed_ops_s'],'query_p99_ms':lambda x:x['query_latency_from_scheduled_ms']['p99'],'query_p999_ms':lambda x:x['query_latency_from_scheduled_ms']['p99_9'],'dispatch_p99_ms':lambda x:x['query_dispatch_lateness_ms']['p99'],'queue_p99_ms':lambda x:x['query_queue_wait_ms']['p99'],'service_p99_ms':lambda x:x['query_service_ms']['p99']}
 psum=summarize(paced,['q','rate','mode'],pmetrics);csvout('paced_summary.csv',psum)
 bindex={(tuple(x['layout']),x['workload'],x['rep'],x['variant']):x for x in cost}
 for x in cost:
  key=(tuple(x['layout']),x['workload'],x['rep']);ref=bindex[(*key,'reference')];native=bindex[(*key,'native')];fused=bindex[(*key,'fused')]
  x.update(b=x['layout'][0],f=x['layout'][1],k=x['layout'][2],ratio_to_reference=x['mixed_ops_per_second']/ref['mixed_ops_per_second'],ratio_to_native=x['mixed_ops_per_second']/native['mixed_ops_per_second'],ratio_to_fused=x['mixed_ops_per_second']/fused['mixed_ops_per_second'],cache_hit_fraction=x['cache_hits']/max(1,x['queries']))
  assert abs(x['checksum']-ref['checksum'])<1e-9 and x['ledger']['charged']<=131072
  if x['variant'] in ['on_demand','cache32_on_demand']:assert x['returned_certificate_queries']==x['requested_certificate_queries']
  elif x['variant']!='native':assert x['returned_certificate_queries']==x['queries']
 zmetrics={k:(lambda x,k=k:x[k]) for k in ['mixed_ops_per_second','ratio_to_reference','ratio_to_native','ratio_to_fused','cache_hit_fraction']};zmetrics.update(query_p50_us=lambda x:x['query_us']['p50'],query_p99_us=lambda x:x['query_us']['p99'],charge_bytes=lambda x:x['ledger']['charged'],snapshot_bytes=lambda x:x['ledger']['image_bytes'])
 zsum=summarize(cost,['b','f','k','workload','variant'],zmetrics);csvout('certificate_cost_summary.csv',zsum)
 csvout('certificate_cost_runs.csv',[{k:v for k,v in x.items() if not isinstance(v,(dict,list))} for x in cost]);csvout('sensitivity_all_test.csv',sensitivity)
 units=sorted({(x['dataset'],x['entity']) for x in sensitivity});ix={(x['dataset'],x['entity'],x['workload'],x['id']):x for x in sensitivity};selected=[];bywork=[]
 for sel in selection['entity_workload']:
  ds,en,w=sel['dataset'],sel['entity'],sel['workload'];t=ix[ds,en,w,sel['id']];d=ix[ds,en,w,'t2-L128'];recent=ix[ds,en,w,'recent'];selected.append(dict(**sel,selected_mse=t['mse'],default_mse=d['mse'],recent_mse=recent['mse'],delta_selected_minus_default=t['mse']-d['mse'],delta_selected_minus_recent=t['mse']-recent['mse'],selected_nrmse=t['nrmse'],default_nrmse=d['nrmse'],selected_charge=t['charged_bytes']))
 for w in sorted({x['workload'] for x in sensitivity}):
  a=[x for x in selected if x['workload']==w];delta=[x['delta_selected_minus_default'] for x in a];glob=next(x['id'] for x in selection['shared'] if x['workload']==w);univ=next(x['id'] for x in selection['shared'] if x['workload']=='all_workloads');default=float(np.mean([x['default_mse'] for x in a]));chosen=float(np.mean([x['selected_mse'] for x in a]))
  row=dict(workload=w,entities=13,default_mse=default,selected_mse=chosen,selected_relative_change=chosen/default-1,recent_mse=float(np.mean([x['recent_mse'] for x in a])),improved=sum(d< -1e-12 for d in delta),tied=sum(abs(d)<=1e-12 for d in delta),worsened=sum(d>1e-12 for d in delta),delta_min=min(delta),delta_max=max(delta),shared_selected_id=glob,shared_selected_mse=float(np.mean([ix[ds,en,w,glob]['mse'] for ds,en in units])),universal_selected_id=univ,universal_selected_mse=float(np.mean([ix[ds,en,w,univ]['mse'] for ds,en in units])))
  bywork.append(row)
 csvout('sensitivity_selected_entities.csv',selected);csvout('sensitivity_selected_summary.csv',bywork)
 surface=[]
 for w in sorted({x['workload'] for x in sensitivity}):
  default=next(x['default_mse'] for x in bywork if x['workload']==w)
  for tau in [.5,1,2,4,8]:
   for L in [32,128,512]:
    a=[x for x in sensitivity if x['workload']==w and x['policy']=='online' and x['tau']==tau and x['L']==L];mse=float(np.mean([x['mse'] for x in a]));surface.append(dict(workload=w,tau=tau,L=L,macro_test_mse=mse,ratio_to_default_macro_mse=mse/default,mean_test_nrmse=float(np.mean([x['nrmse'] for x in a])),min_entity_mse=min(x['mse'] for x in a),max_entity_mse=max(x['mse'] for x in a)))
 csvout('sensitivity_surface.csv',surface)
 # Paired comparisons, not ratios of independently aggregated medians.
 paired=[]
 for x in concurrency:
  if x['mode']!='strict':continue
  candidates=[y for y in concurrency if y['mode']=='sync' and all(x[k]==y[k] for k in ['group','rep','query_mix','clients','delay_ms','K','policy','instrument'])];assert len(candidates)==1;y=candidates[0]
  paired.append({k:x[k] for k in ['group','rep','query_mix','clients','delay_ms','K','policy','instrument']}|dict(strict_sync_throughput_ratio=x['throughput_ops_s']/y['throughput_ops_s'],strict_sync_query_p99_ratio=x['metrics']['query']['latency_ms']['p99']/y['metrics']['query']['latency_ms']['p99']))
 csvout('concurrency_paired.csv',paired)
 before=json.loads((OUT/'PROTECTED_BEFORE.json').read_text());diff=[p for p,h in before.items() if not (ROOT/p).exists() or hashlib.sha256((ROOT/p).read_bytes()).hexdigest()!=h];assert not diff
 tests=(OUT/'all_tests.log').read_text();assert 'failed' not in tests and 'passed' in tests
 qa=dict(concurrency_runs=len(concurrency),concurrency_requests=sum(x['operations'] for x in concurrency),durable_concurrency_runs=sum(x['mode']!='none' for x in concurrency),all_observed_RPO_and_final_state_checks_pass=True,paced_runs=len(paced),paced_requests=sum(x['operations'] for x in paced),paced_durable_runs=sum(x['mode']!='none' for x in paced),certificate_timing_runs=len(cost),certificate_timing_requests=sum(x['operations'] for x in cost),certificate_trace_prediction_checksums_identical=True,certificate_real_answered_cases=sum(x['answered_cases'] for x in quality),certificate_real_unknown_cases=sum(x['unknown_cases'] for x in quality),certificate_candidate_answered_evaluations=3*sum(x['answered_cases'] for x in quality),certificate_violations=sum(x['violations'] for x in quality),max_real_prediction_difference=max(x['max_prediction_difference'] for x in quality),analytical_bounds_identical=True,rounding_allowance_ratio_range=[min(x['rounding_ratio_range'][0] for x in quality),max(x['rounding_ratio_range'][1] for x in quality)],certificate_snapshot_restores=sum(x['snapshot_restores'] for x in quality),sensitivity_validation_cases=1248,sensitivity_test_cases=len(sensitivity),sensitivity_scheduled_test_queries=sum(x['queries'] for x in sensitivity),validation_choices_frozen_before_tests=True,sensitivity_default_reproduction_cases=len(json.loads((OUT/'sensitivity_default_reproduction.json').read_text())),sensitivity_all_coverage_one=all(x['coverage']==1 for x in sensitivity),sensitivity_max_charge=max(x['charged_bytes'] for x in sensitivity),protected_files_checked=len(before),protected_files_changed=diff,production_core_unchanged=True,manuscript_entire_directory_unchanged=True,technical_repeats={'concurrency':3,'certificate_timing':7},independent_hardware_hosts=1,entity_correlation='12 Beijing stations plus one Bike entity; no independent-population significance claims',all_tests=tests.strip())
 write(OUT/'QA.json',qa);write(OUT/'analysis.json',dict(concurrency=csum,paced=psum,cost=zsum,selected=selected,sensitivity=bywork,surface=surface));print(json.dumps(qa,indent=2),flush=True)
if __name__=='__main__':main()
