from pathlib import Path
import sys,json,argparse,subprocess,resource,tracemalloc,time,hashlib,importlib.util
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'results/review3_20261104'
PROBE={'measured':False,'phases':{},'payload_max':0,'checkpoints':0}

def observe_phase(phase):
    if not PROBE['measured']:return
    import psutil
    current,peak=tracemalloc.get_traced_memory();rss=psutil.Process().memory_info().rss
    r=PROBE['phases'].setdefault(phase,dict(samples=0,max_traced_current_bytes=0,max_traced_peak_bytes=0,max_rss_bytes=0))
    r['samples']+=1;r['max_traced_current_bytes']=max(r['max_traced_current_bytes'],current);r['max_traced_peak_bytes']=max(r['max_traced_peak_bytes'],peak);r['max_rss_bytes']=max(r['max_rss_bytes'],rss)

def child(variant,clients):
    sys.modules['memory']=sys.modules[__name__]
    # Keep the primary harness unchanged. The diagnostic copy adds probes only.
    source=(ROOT/'repro/review_revision/performance.py').read_text()
    source=source.replace('done.wait(.2)','done.wait(.001)')
    source=source.replace('rss_start=psutil.Process().memory_info().rss',"rss_start=psutil.Process().memory_info().rss\n tracemalloc.reset_peak();PROBE['measured']=True")
    source=source.replace('import numpy as np,psutil','import numpy as np,psutil,tracemalloc\nfrom memory import PROBE')
    path=ROOT/'repro/review3/memory_harness.py'
    assert path.read_text()==source,'diagnostic harness must match its declared transformation'
    spec=importlib.util.spec_from_file_location('review3_memory_harness',path);h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
    original_build=h.old.build_service;OriginalStore=h.old.TwoSlotStore
    def build(*args):
        s=original_build(*args);dumps=s.dumps
        def capture():
            observe_phase('before_capture');b=dumps();observe_phase('after_capture');return b
        s.dumps=capture;return s
    class ProbeStore(OriginalStore):
        def commit(self,payload,*args,**kwargs):
            observe_phase('before_commit');r=super().commit(payload,*args,**kwargs);observe_phase('after_commit')
            if PROBE['measured']:
                PROBE['payload_max']=max(PROBE['payload_max'],len(payload));PROBE['checkpoints']+=1
            return r
    h.old.build_service=build;h.old.TwoSlotStore=ProbeStore
    workloads=json.loads((ROOT/'results/frozen/rq_closure/rq3_boundary/RQ3_FREEZE.json').read_text())['workloads']
    rows=h.old.all_split_units(5)[-1][-1];tracemalloc.start(1)
    case=OUT/'memory'/f'{variant}-c{clients}'
    r=h.one(case,rows,workloads['dynamic_dominant']['spec'],'dynamic','sync' if variant=='sync' else 'strict',20261104,clients,100000,False,variant!='optimized')
    current,peak=tracemalloc.get_traced_memory()
    r.update(variant=variant,diagnostic_memory=True,trace_current_bytes=current,trace_peak_bytes=peak,ru_maxrss_bytes=int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss),phase_observations=PROBE['phases'],largest_measured_payload_bytes=PROBE['payload_max'],observed_measured_checkpoints=PROBE['checkpoints'],rss_sampling_interval_ms=1,trace_start='after imports, data load; before service allocation; peak reset after warmup',timing_use='excluded from primary performance comparisons')
    (case/'result.json').write_text(json.dumps(r,indent=2)+'\n')

def main():
    p=argparse.ArgumentParser();p.add_argument('--child',choices=['sync','original','optimized']);p.add_argument('--clients',type=int);args=p.parse_args()
    if args.child:child(args.child,args.clients);return
    source=(ROOT/'repro/review_revision/performance.py').read_text().replace('done.wait(.2)','done.wait(.001)').replace('rss_start=psutil.Process().memory_info().rss',"rss_start=psutil.Process().memory_info().rss\n tracemalloc.reset_peak();PROBE['measured']=True").replace('import numpy as np,psutil','import numpy as np,psutil,tracemalloc\nfrom memory import PROBE')
    (ROOT/'repro/review3/memory_harness.py').write_text(source)
    (OUT/'MEMORY_FREEZE.json').write_text(json.dumps(dict(variants=['sync','original','optimized'],clients=[1,8,16],operations_requested=100000,seed=20261104,harness_sha256=hashlib.sha256(source.encode()).hexdigest()),indent=2))
    raw=[]
    for c in (1,8,16):
        for v in ('sync','original','optimized'):
            case=OUT/'memory'/f'{v}-c{c}'
            if not (case/'result.json').exists():
                subprocess.run([sys.executable,__file__,'--child',v,'--clients',str(c)],check=True)
            r=json.loads((case/'result.json').read_text());raw.append(r)
            (OUT/'memory_raw.json').write_text(json.dumps(raw,indent=2)+'\n')
            print('memory',v,c,'rss',r['rss_peak_bytes'],'trace',r['trace_peak_bytes'],flush=True)
if __name__=='__main__':main()
