"""Three paired offered-load points; quality selection never uses latency results."""
from pathlib import Path
import sys,json,time,threading,random,subprocess,hashlib
from concurrent.futures import ThreadPoolExecutor
import numpy as np,psutil
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(Path(__file__).parent));sys.path.insert(0,str(ROOT/'src'));sys.path.insert(0,str(ROOT/'repro/review7_20261109'))
from common import OUT,write,selected,service_at
from exact import ExactPrefix
from mtmemory_icde.core.evidence_service import EvidenceService
from mtmemory_icde.core.rpo import CheckpointCoordinator
from mtmemory_icde.core.checkpoint import TwoSlotStore

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def data():
    with np.load(ROOT/'data/real/household.npz') as z:
        tr,va,te=[z[f'{name}_0'] for name in ['train','validation','test']]
    return np.concatenate([tr,va,te]),len(tr)+len(va),len(tr),float(np.var(tr.astype(float),axis=0).mean())
def due_times(base,duration=60):
    cuts=[0,20,25,45,50,duration]
    return np.concatenate([a+np.arange(int((z-a)*base*(4 if j in [1,3] else 1)))/(base*(4 if j in [1,3] else 1)) for j,(a,z) in enumerate(zip(cuts,cuts[1:]))])
def requests(N,rep):
    seed=40100+rep*1000
    r=np.random.default_rng(seed).random(N);kind=np.where(r<.95,0,np.where(r<.99,1,2)).astype(np.int8)
    widths=np.random.default_rng(seed+1).integers(16,129,N,dtype=np.int16)
    panels=np.random.default_rng(seed+2).integers(0,3,N,dtype=np.int8)
    u=np.random.default_rng(seed+3).random(N);delays=np.empty(N,np.int32)
    for j,(a,z) in enumerate([(384,512),(1536,2048),(6144,8192)]):
        take=panels==j;delays[take]=a+np.floor(u[take]*(z-a+1)).astype(np.int32)-widths[take]
    return kind,widths,delays

def child(job):
    import os
    protocol=json.loads((OUT/'LOAD_PROTOCOL.json').read_text());method=job['method'];rows,t0,train_n,var=data()
    s=EvidenceService.loads((OUT/'load_initial'/f'{method}.bin').read_bytes())
    case=OUT/'load_runs'/job['name'];case.mkdir(parents=True,exist_ok=True);write(case/'PROCESS.json',dict(pid=os.getpid()))
    co=CheckpointCoordinator(s,TwoSlotStore(case/'checkpoint'),500,verify_capture=False)
    proc=psutil.Process();rss_before_trace=proc.memory_info().rss/2**20
    due=due_times(job['base']);N=len(due);kinds,widths,delays=requests(N,job['rep'])
    assert np.count_nonzero(kinds==1)<=len(rows)-t0
    latency=np.full(N,np.nan);execution=np.full(N,np.nan);cert=np.zeros(N,bool);served=np.zeros(N,bool)
    fact_capacity=int(np.count_nonzero(kinds==2));fp=np.zeros(fact_capacity,np.int64);fk=np.zeros(fact_capacity,np.int16);fv=np.zeros(fact_capacity,np.int64);fd=np.zeros(fact_capacity,bool)
    raw_n=t0;fact_n=0;index=0;ticket=threading.Lock();barrier=threading.Barrier(9);start=[0.];counts=[0]*8;stop=threading.Event();telemetry=[]
    def worker(wid):
        nonlocal index,raw_n,fact_n
        audit=[];barrier.wait()
        while True:
            with ticket:i=index;index+=1
            if i>=N:break
            pause=start[0]+due[i]-time.perf_counter()
            if pause>0:time.sleep(pause)
            tick=time.perf_counter()
            if kinds[i]==0:
                answer=s.query(i%256,int(delays[i]),int(widths[i]));h=answer['history'];assert h['status']=='ANSWERED'
                good=np.sqrt(np.mean(h['total_bound']**2)/var)<=.1
                if i%5003==0:audit.append(answer)
            else:
                def mutate():
                    nonlocal raw_n,fact_n
                    if kinds[i]==1:
                        out=s.observe(rows[raw_n]);raw_n+=1;return out
                    deleted=i%7==0;out=s.put_fact(i%256,rows[i%train_n],delete=deleted)
                    fp[fact_n]=s.ack_seq;fk[fact_n]=i%256;fv[fact_n]=s.version;fd[fact_n]=deleted;fact_n+=1;return out
                co.mutate(mutate);good=False
            done=time.perf_counter();latency[i]=(done-start[0]-due[i])*1000;execution[i]=(done-tick)*1000
            cert[i]=good;served[i]=True;counts[wid]+=1
        return audit
    def monitor():
        block=0
        while not stop.wait(1):
            elapsed=time.perf_counter()-start[0];done=sum(counts);arrived=int(np.searchsorted(due,elapsed,side='right'))
            telemetry.append(dict(seconds=elapsed,completed=done,arrived=arrived,sampled_backlog=max(0,arrived-done),rss=proc.memory_info().rss,checkpoint_count=co.checkpoint_count_total))
            if int(elapsed//20)>block:
                block=int(elapsed//20);q=served&(kinds==0)
                msg=dict(elapsed=round(elapsed,2),completed=done,backlog=max(0,arrived-done),query_p99_ms=float(np.percentile(latency[q],99)) if np.any(q) else None,max_gap=co.maximum_gap)
                with (case/'progress.jsonl').open('a') as f:f.write(json.dumps(msg)+'\n')
                print('PROGRESS',job['name'],json.dumps(msg),flush=True)
    with ThreadPoolExecutor(max_workers=8) as pool:
        tasks=[pool.submit(worker,w) for w in range(8)];start[0]=time.perf_counter();thread=threading.Thread(target=monitor,daemon=True);thread.start();barrier.wait()
        audits=[a for f in tasks for a in f.result()];elapsed=time.perf_counter()-start[0]
    stop.set();thread.join();cp_start=time.perf_counter();co.close();drain=time.perf_counter()-cp_start
    _,blob,_=co.store.recover();restored=EvidenceService.loads(blob)
    assert served.all() and co.maximum_gap<=500 and s.ack_seq==restored.ack_seq==co.durable_seq
    assert s._arrays().keys()==restored._arrays().keys()
    assert all(np.array_equal(s._arrays()[k],restored._arrays()[k]) for k in s._arrays())
    assert co.checkpoint_count_total==len(co.records),'all short-run checkpoint records must fit bounded telemetry'
    for a in audits:
        lo,hi=a['lo'],a['hi'];h=a['history'];oracle=ExactPrefix(rows[lo:hi]);assert oracle.contains(0,hi-lo,h['value'],h['total_bound'])
        f=a['fact'];ids=np.flatnonzero((fp[:fact_n]<=a['prefix'])&(fk[:fact_n]==f['key']))
        if len(ids):j=ids[-1];assert f['version']==fv[j] and f['live']==(not fd[j])
        else:assert f['version']==(f['key']+1 if f['key']<128 else 0)
    q=kinds==0;good=cert&q;account=s.account(len(blob));assert account['within_budget'] and account['snapshot_fits']
    result=dict(**job,requests=N,queries=int(q.sum()),observations=raw_n-t0,source_cycles=0,seconds_including_request_drain=elapsed,offered_horizon_seconds=60,
                G01=float(cert[q].mean()),certified_goodput=float(good.sum()/elapsed),timely_goodput_20ms=float(np.count_nonzero(good&(latency<=20))/elapsed),
                scheduled_query_p99_ms=float(np.percentile(latency[q],99)),scheduled_query_p999_ms=float(np.percentile(latency[q],99.9)),execution_query_p99_ms=float(np.percentile(execution[q],99)),
                max_gap=co.maximum_gap,max_sampled_backlog=max(x['sampled_backlog'] for x in telemetry),sampled_peak_rss_mib=max(x['rss'] for x in telemetry)/2**20,rss_before_trace_mib=rss_before_trace,
                final_checkpoint_drain_seconds=drain,final_image_restored=True,exact_oracle_checks=len(audits),checkpoint_count=co.checkpoint_count_total,account=account,
                measurement_scope='whole process includes source generator and preallocated finite-run request/latency buffers outside logical ledger; sampled RSS/backlog can miss peaks')
    write(case/'result.json',result);write(case/'telemetry.json',telemetry);write(case/'checkpoints.json',list(co.records));(case/'final_image.bin').write_bytes(blob)
    np.savez_compressed(case/'requests.npz',kind=kinds,scheduled_latency_ms=latency,execution_latency_ms=execution,certified=cert)
    print('COMPLETE',job['name'],json.dumps(result),flush=True)

def kernel_diagnostic(choices,rows,t0):
    records=[];rng=np.random.default_rng(17700);queries=[]
    for _ in range(3000):
        w=int(rng.integers(16,129));a,z=[(384,512),(1536,2048),(6144,8192)][int(rng.integers(3))];queries.append((int(rng.integers(a,z+1))-w,w))
    for method,c in choices.items():
        for rep in range(3):
            order=['span','sum'] if rep%2==0 else ['sum','span']
            for mode in order:
                s=service_at(c,rows,t0-2048,mode)
                for d,w in queries[:200]:s.query(0,d,w)
                latency=[];tick=time.perf_counter()
                for d,w in queries:
                    begin=time.perf_counter_ns();s.query(0,d,w);latency.append((time.perf_counter_ns()-begin)/1e6)
                elapsed=time.perf_counter()-tick
                records.append(dict(method=method,rep=rep,mode=mode,queries=len(queries),seconds=elapsed,query_p50_ms=float(np.median(latency)),query_p99_ms=float(np.percentile(latency,99)),scope='separate serial fixed-state validation-data certificate-cost diagnostic; not paced service latency'))
    write(OUT/'KERNEL_DIAGNOSTIC.json',records)

def main():
    assert json.loads((OUT/'AUDIT.json').read_text())['passed']
    pool=[x for x in selected() if x['unit']==13 and x['B']==262144 and x['prior']=='panels' and x['mode']=='sum' and x['objective']=='g01']
    strong=max([x for x in pool if x['variant'] in ['sse','bound','fixed']],key=lambda x:(x['metrics']['all']['G']['0.1'],-x['config']['ledger']['charged_bytes'],x['id']))
    chosen={'recent':next(x for x in pool if x['variant']=='recent'),'age':next(x for x in pool if x['variant']=='age'),'hist':strong}
    choices={k:x['config'] for k,x in chosen.items()};rows,t0,train_n,var=data()
    sources=[Path(__file__),Path(__file__).with_name('common.py'),*sorted((ROOT/'src/mtmemory_icde/core').glob('*.py'))]
    pilot_protocol=dict(choices=choices,selection_sha256=sha(OUT/'SELECTIONS.json'),certificate_mode='sum',quality_selection='Household validation G(.1), family independent; strongest histogram also selected only by validation',pilot_requests=10000,relative_rates=[.05,.15,.35],base_cap=8000,base_floor=100,rate_step=100,burst_multiplier=4,duration=60,bursts=[[20,25],[45,50]],clients=8,K=500,request_fractions=[.95,.04,.01],technical_repeats=3,source={str(p.relative_to(ROOT)):sha(p) for p in sources})
    pp=OUT/'PILOT_PROTOCOL.json'
    if pp.exists():assert json.loads(pp.read_text())==pilot_protocol
    else:write(pp,pilot_protocol)
    if not (OUT/'PILOT.json').exists():
        pilot=[]
        for method,c in choices.items():
            s=service_at(c,rows,t0-2048);case=OUT/'pilot'/method;co=CheckpointCoordinator(s,TwoSlotStore(case),500,verify_capture=False)
            kinds,widths,delays=requests(10000,100);observed=0;tick=time.perf_counter()
            for i in range(10000):
                if kinds[i]==0:s.query(i%256,int(delays[i]),int(widths[i]))
                elif kinds[i]==1:co.mutate(lambda:s.observe(rows[t0-2048+observed]));observed+=1
                else:co.mutate(lambda:s.put_fact(i%256,rows[i%train_n]))
            elapsed=time.perf_counter()-tick;co.close();pilot.append(dict(method=method,requests=10000,seconds=elapsed,rps=10000/elapsed,validation_observations=observed))
        slow=min(x['rps'] for x in pilot);rates=[]
        for i,fraction in enumerate([.05,.15,.35]):
            rate=max(100,min(8000-(2-i)*100,int(slow*fraction/100)*100))
            if rates:rate=max(rate,rates[-1]+100)
            rates.append(rate)
        write(OUT/'PILOT.json',dict(records=pilot,base_rates=rates,scope='validation-only serial throughput calibration; offered-load points, not capacity guarantees'))
    pilot=json.loads((OUT/'PILOT.json').read_text());rates=pilot['base_rates']
    if not (OUT/'KERNEL_DIAGNOSTIC.json').exists():kernel_diagnostic(choices,rows,t0)
    initial=OUT/'load_initial';initial.mkdir(exist_ok=True)
    for method,c in choices.items():
        p=initial/f'{method}.bin'
        if not p.exists():p.write_bytes(service_at(c,rows,t0).dumps())
    jobs=[dict(method=m,rep=r,base=rate,burst=4*rate,name=f'{m}-b{rate}-r{r}') for m in choices for rate in rates for r in range(3)]
    random.Random(20261110).shuffle(jobs)
    protocol=dict(**pilot_protocol,base_rates=rates,jobs=jobs,histogram_variant=strong['variant'],audit_sha256=sha(OUT/'AUDIT.json'),
                  metrics='G(.1), certified/s, per-completion20ms certified/s, all-query scheduled p99; goodput elapsed includes request drain, final forced checkpoint drain separate',
                  feasibility='for requirement alpha, observed feasible iff every technical repeat has G(.1)>=alpha and scheduled p99<=20ms; report min-repeat G as alpha_max only if all3 tails pass; descriptive finite-horizon result, no productionSLO guarantee',
                  scope='three shared60s offered-load points x3methods x3technical repeats, fixed two5s fourfold bursts; no production trace or sustained-capacity optimum claim')
    p=OUT/'LOAD_PROTOCOL.json'
    if p.exists():assert json.loads(p.read_text())==protocol
    else:write(p,protocol)
    print('FROZEN LOADS',rates,'comparator',strong['id'],flush=True)
    for i,job in enumerate(jobs):
        case=OUT/'load_runs'/job['name'];case.mkdir(parents=True,exist_ok=True)
        if not (case/'result.json').exists():
            assert not (case/'checkpoint').exists(),'preserve interrupted run before retrying'
            print('START',i+1,len(jobs),job['name'],flush=True)
            with (case/'stdout.txt').open('w') as out,(case/'stderr.txt').open('w') as err:
                result=subprocess.run([sys.executable,str(Path(__file__)),json.dumps(job)],stdout=out,stderr=err,timeout=660)
                assert result.returncode==0,(job,(case/'stderr.txt').read_text())
        print('CASE',i+1,len(jobs),job['name'],flush=True)
    write(OUT/'load_records.json',[json.loads((OUT/'load_runs'/j['name']/'result.json').read_text()) for j in jobs]);print('ALL LOAD RUNS COMPLETE',flush=True)

if __name__=='__main__':
    if len(sys.argv)>1:child(json.loads(sys.argv[1]))
    else:main()
