"""Predeclared fixed-query reach/exactness/error grid. No test tuning."""
from pathlib import Path
from collections import defaultdict
from io import BytesIO
import csv,hashlib,importlib.util,json,math,platform,sys,time
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'src'))
sp=importlib.util.spec_from_file_location('closure_original',ROOT/'repro/round78_rq_closure/run.py');old=importlib.util.module_from_spec(sp);sp.loader.exec_module(old)
from mtmemory_icde.core.history import Config,TieredOverlayStore
from mtmemory_icde.core.baselines import ExactTail
OUT=ROOT/'results/rq2_tradeoff_20261107';REPRO=ROOT/'repro/rq2_tradeoff_20261107'
BUDGETS=(65536,131072,262144);REACHES=(512,1024,2048,4096,8192,16384);METHODS=('h1','h4','h8','h16','coarse','tail');EDGES=(128,256,512,1024,2048,4096,8192,16384)
M=6144;W=8192

def write(p,x):p.write_text(json.dumps(x,indent=2,allow_nan=False)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def ledger(s):
    a=s.account()['resident_array_bytes'];return dict(array_bytes=int(a),metadata_bytes=M,workspace_bytes=W,snapshot_slot_bytes=int(a+M),charged_bytes=int(3*(a+M)+W))
class Native(TieredOverlayStore):
    def observe(self,row):
        super().observe(row);self.actions.clear()
class Tail(ExactTail):
    def __init__(self,budget,reach):
        cap=min(reach,(budget-3*M-W)//72);super().__init__(3*4096+2048+72*cap,4,reach);self.budget=budget
    def dumps(self):
        f=BytesIO();np.savez(f,rows=self.rows,ids=self.ids,meta=np.array([self.budget,self.max_reach,self.n],np.int64));return f.getvalue()
    @classmethod
    def loads(cls,data):
        z=np.load(BytesIO(data));b,r,n=map(int,z['meta']);s=cls(b,r);s.n=n;s.rows[:]=z['rows'];s.ids[:]=z['ids'];return s

def native(r,h,k,budget):return Native(Config(budget=budget,base_width=128,fine_width=h,max_reach=r,overlay_capacity=k,policy='recent' if k else 'none',query_history=128))
def grid():
    out=[]
    for B in BUDGETS:
        for R in REACHES:
            for method in METHODS:
                if method=='tail':s=Tail(B,R);h=None;k=None;key=('tail',R,s.capacity)
                else:
                    h=128 if method=='coarse' else int(method[1:]);k=0
                    if method!='coarse':
                        for kk in range(math.ceil(R/128)+2):
                            probe=native(R,h,kk,10000000)
                            if ledger(probe)['charged_bytes']<=B:k=kk
                    s=native(R,h,k,B);key=('native',R,h,k)
                a=ledger(s);assert a['charged_bytes']<=B
                out.append(dict(index=len(out),budget=B,reach=R,method=method,h=h,k=k,key=list(key),**a,tail_capacity=s.capacity if method=='tail' else None))
    return out

def make(spec):return Tail(spec['budget'],spec['reach']) if spec['method']=='tail' else native(spec['reach'],spec['h'],spec['k'],spec['budget'])
def answer(s,q,R):
    t,fam,bi,a,d,w=map(int,q)
    if a>R:return 0,None
    ans=s.query(d,w,record=False)
    if ans['value'] is None:return 0,None
    if isinstance(s,Tail):return 2,ans['value']
    lo=t-a;hi=t-d;exact=True
    for bid in range(lo//128,(hi-1)//128+1):
        assert s.base_ids[bid%s.base_slots]==bid # all primary cells are sealed
        left=max(lo,bid*128);right=min(hi,(bid+1)*128)
        h=s.cfg.fine_width if np.any(s.overlay_ids==bid) else 128
        exact &= left%h==0 and right%h==0
    assert (ans['resolution']=='EXACT')==exact
    return 2 if exact else 1,ans['value']
def schedule(train,val,test,ui):
    start=len(train)+len(val);end=start+len(test);eligible=max(start+1,16384);anchors=list(range(eligible,end+1,128));assert anchors
    rng=np.random.default_rng(20261107+17*ui);qs=[]
    def add(t,fam,bi,low,high):
        a=int(rng.integers(max(low+1,144),high+1));opts=[w for w in (16,32,64,128) if a-w>=128];w=int(rng.choice(opts));qs.append([t,fam,bi,a,a-w,w])
    for t in anchors:
        for bi,(l,h) in enumerate(zip(EDGES[:-1],EDGES[1:])):add(t,0,bi,l,h)
        for j in range(8):add(t,1,-1,143,512)
    return np.asarray(qs,np.int64),dict(train_rows=len(train),validation_rows=len(val),test_rows=len(test),eligible_test_prefix_start=eligible,excluded_test_prefix_count=eligible-(start+1),eligible_prefix_count=end-eligible+1,anchors=len(anchors),global_queries=len(anchors)*7,common_queries=len(anchors)*8)

def controls():
    # Actual b=128 controls, exhaustive selected sealed-boundary intervals.
    rng=np.random.default_rng(97);rows=rng.normal(size=(2049,4)).astype(np.float32);cases=0;approx_zero=0;restores=0
    for h,k in ((1,0),(1,2),(4,2),(8,2),(16,2),(128,0)):
        for constant in (False,True):
            rr=np.ones_like(rows) if constant else rows;s=native(512,h,k,131072)
            for row in rr:s.observe(row)
            for a in (144,255,256,257,383,384,511,512,513,600):
                for w in (1,4,16,32,64,128):
                    if a-w<128:continue
                    q=[len(rr),0,0,a,a-w,w];state,pred=answer(s,q,512);cases+=1
                    if a>512:assert state==0;continue
                    truth=rr[len(rr)-a:len(rr)-a+w].astype(np.float64).mean(0)
                    if state==2:assert np.allclose(pred,truth,rtol=1e-12,atol=1e-12)
                    if constant and state==1:assert np.array_equal(pred,truth);approx_zero+=1
                    z=Native.loads(s.dumps());state2,pred2=answer(z,q,512);assert state2==state and np.array_equal(pred,pred2);restores+=1
            assert len(s.dumps())<=ledger(s)['snapshot_slot_bytes'] and len(s.actions)==0
    tail=Tail(65536,16384)
    for row in rows:tail.observe(row)
    restored=Tail.loads(tail.dumps());assert np.array_equal(restored.rows,tail.rows)
    assert tail.capacity>=512 and ledger(tail)['charged_bytes']<=65536
    assert approx_zero>0
    return dict(cases=cases,approximate_zero_error_cases=approx_zero,restore_queries=restores,tail_restore_pass=True,outside_declared_R_rejected=True,exact_not_defined_by_zero_error=True)

def summarize(specs):
    entity=[];bins=[];qa=dict(configurations=len(specs),entities=13,ledger_checks=True,within_R_all_native_answered=True,common_all_answered=True,exact_numeric_checks=0,snapshot_checks=0,minimum_snapshot_margin=10**9,unique_query_method_cases=0,budget_expanded_cases=0)
    for ui in range(13):
        u=json.loads((OUT/'units'/f'{ui:02d}.json').read_text());z=np.load(OUT/'units'/f'{ui:02d}.npz');qs=z['queries'];st=z['state'];pred=z['prediction'];truth=z['truth'];qa['unique_query_method_cases']+=u['unique_query_method_cases'];qa['budget_expanded_cases']+=int(st.size);qa['exact_numeric_checks']+=u['exact_numeric_checks'];qa['snapshot_checks']+=len(u['snapshot_checks']);qa['minimum_snapshot_margin']=min(qa['minimum_snapshot_margin'],min(a['margin'] for a in u['snapshot_checks']))
        for ci,c in enumerate(specs):
            global_mask=qs[:,1]==0;common=~global_mask;state=st[ci];err=np.mean((pred[ci]-truth)**2,axis=1);variance=u['training_variance']
            assert np.all(state[common]>0)
            if c['method']!='tail':assert np.all(state[global_mask&(qs[:,3]<=c['reach'])]>0)
            exact=state==2
            base=dict(dataset=u['dataset'],entity=u['entity'],config=ci,budget=c['budget'],reach=c['reach'],method=c['method'],h=c['h'],k=c['k'],charged_bytes=c['charged_bytes'],tail_capacity=c['tail_capacity'])
            entity.append(dict(**base,global_queries=int(global_mask.sum()),answered=float(np.mean(state[global_mask]>0)),exact=float(np.mean(exact[global_mask])),approximate=float(np.mean(state[global_mask]==1)),unavailable=float(np.mean(state[global_mask]==0)),common_queries=int(common.sum()),common_exact=float(np.mean(exact[common])),common_nrmse=float(np.sqrt(err[common].mean()/variance)),observed_zero_approx_queries=int(np.sum((state==1)&(err==0)))))
            for bi in range(7):
                mask=global_mask&(qs[:,2]==bi);ok=mask&(state>0)
                bins.append(dict(**base,age_bin=bi,age_low=EDGES[bi],age_high=EDGES[bi+1],queries=int(mask.sum()),answered=int(ok.sum()),exact=float(np.mean(state[mask]==2)),approximate=float(np.mean(state[mask]==1)),unavailable=float(np.mean(state[mask]==0)),conditional_nrmse=float(np.sqrt(err[ok].mean()/variance)) if np.any(ok) else None))
    write(OUT/'entity_results.json',entity);write(OUT/'distance_entity_results.json',bins)
    summary=[];distance=[]
    for c in specs:
        values=[v for v in entity if v['config']==c['index']];row=dict(c)
        for metric in ('answered','exact','approximate','unavailable','common_exact','common_nrmse'):
            ys=[v[metric] for v in values];row[metric]=float(np.mean(ys));row[metric+'_ci95']=old.bootstrap_ci(ys,seed=20261107)
        summary.append(row)
        for bi in range(7):
            vv=[v for v in bins if v['config']==c['index'] and v['age_bin']==bi];rr=dict(config=c['index'],budget=c['budget'],reach=c['reach'],method=c['method'],age_bin=bi,age_low=EDGES[bi],age_high=EDGES[bi+1],entities=13)
            for metric in ('exact','approximate','unavailable'):rr[metric]=float(np.mean([v[metric] for v in vv]))
            rr['answered_queries']=sum(v['answered'] for v in vv);rr['queries']=sum(v['queries'] for v in vv);rr['conditional_nrmse_mean']=float(np.mean([v['conditional_nrmse'] for v in vv if v['conditional_nrmse'] is not None])) if any(v['conditional_nrmse'] is not None for v in vv) else None
            assert abs(rr['exact']+rr['approximate']+rr['unavailable']-1)<1e-12;distance.append(rr)
    write(OUT/'summary.json',summary);write(OUT/'distance_summary.json',distance)
    contrasts=[]
    for B in BUDGETS:
        for method in METHODS:
            for lo,hi in zip(REACHES[:-1],REACHES[1:]):
                l={(v['dataset'],v['entity']):v for v in entity if v['budget']==B and v['method']==method and v['reach']==lo};r=[v for v in entity if v['budget']==B and v['method']==method and v['reach']==hi];row=dict(budget=B,method=method,from_reach=lo,to_reach=hi)
                for metric in ('answered','exact','common_exact','common_nrmse'):
                    ys=[v[metric]-l[v['dataset'],v['entity']][metric] for v in r];row[metric+'_delta']=float(np.mean(ys));row[metric+'_delta_ci95']=old.bootstrap_ci(ys,seed=20261107);row[metric+'_entities_up']=sum(x>1e-12 for x in ys);row[metric+'_entities_down']=sum(x< -1e-12 for x in ys)
                contrasts.append(row)
    write(OUT/'neighbor_contrasts.json',contrasts)
    for name,rows in [('source_data',summary),('distance_source_data',distance),('entity_source_data',entity),('neighbor_contrasts',contrasts)]:
        with (OUT/f'{name}.csv').open('w',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    write(OUT/'QA.json',qa);print(json.dumps(qa,indent=2),flush=True)

def main():
    OUT.mkdir(exist_ok=True);(OUT/'units').mkdir(exist_ok=True);specs=grid();write(OUT/'grid.json',specs)
    sources=[Path(__file__),REPRO/'PROTOCOL.txt',ROOT/'src/mtmemory_icde/core/history.py',ROOT/'src/mtmemory_icde/core/baselines.py',ROOT/'data/real/bike.npz',ROOT/'data/real/beijing.npz']
    hashes={str(p.relative_to(ROOT)):sha(p) for p in sources};signature=hashlib.sha256(json.dumps(hashes,sort_keys=True).encode()).hexdigest();protocol=OUT/'frozen.json'
    if protocol.exists():assert json.loads(protocol.read_text())['signature']==signature,'Frozen source/data changed: use a new output directory'
    else:write(protocol,dict(signature=signature,hashes=hashes,python=sys.version,numpy=np.__version__,platform=platform.platform(),machine=platform.machine(),b=128,metadata=M,workspace=W,budgets=BUDGETS,reaches=REACHES,methods=METHODS,selection='none; predeclared capacity rule',query_seed=20261107))
    write(OUT/'controls.json',controls())
    poolkeys=list(dict.fromkeys(tuple(c['key']) for c in specs));poolmap=np.array([poolkeys.index(tuple(c['key'])) for c in specs]);pool_specs=[next(c for c in specs if tuple(c['key'])==k) for k in poolkeys]
    for ui,(dataset,ent,train,val,test) in enumerate(old.all_split_units()):
        dest=OUT/'units'/f'{ui:02d}.json'
        if dest.exists():assert json.loads(dest.read_text())['signature']==signature;print(f'resume {ui}',flush=True);continue
        started=time.perf_counter();rows=np.concatenate([train,val,test]);qs,counts=schedule(train,val,test,ui);bytime=defaultdict(list)
        for qi,q in enumerate(qs):bytime[int(q[0])].append(qi)
        stores=[make(c) for c in pool_specs];states=np.zeros((len(stores),len(qs)),np.int8);pred=np.full((len(stores),len(qs),4),np.nan);truth=np.zeros((len(qs),4));exact_checks=0
        for t,row in enumerate(rows,1):
            for store in stores:store.observe(row)
            for qi in bytime.get(t,()):
                q=qs[qi];a,d,w=map(int,q[3:]);truth[qi]=rows[t-a:t-d].astype(np.float64).mean(0)
                for si,(store,c) in enumerate(zip(stores,pool_specs)):
                    state,value=answer(store,q,c['reach']);states[si,qi]=state
                    if state:
                        pred[si,qi]=value
                        if state==2:
                            # Explicit conservative arithmetic check against direct input mean.
                            magnitude=float(np.max(np.abs(rows[t-a:t-d].astype(np.float64))));allowance=256*np.finfo(np.float64).eps*max(1.,magnitude)
                            assert np.max(np.abs(value-truth[qi]))<=allowance;exact_checks+=1
        snaps=[];reachchecks=[]
        for store,c in zip(stores,pool_specs):
            a=ledger(store);payload=store.dumps();assert len(payload)<=a['snapshot_slot_bytes'];assert not getattr(store,'actions',[])
            restored=Tail.loads(payload) if isinstance(store,Tail) else Native.loads(payload)
            for original_q in qs[-15:]:
                q=original_q.copy();q[0]=len(rows)
                x,p=answer(store,q,c['reach']);y,v=answer(restored,q,c['reach']);assert x==y and (p is None or np.array_equal(p,v))
            if isinstance(store,Tail):verified=min(c['reach'],store.capacity);assert all(store.ids[j%store.capacity]==j for j in range(len(rows)-verified,len(rows)))
            else:
                low=len(rows)-c['reach'];hi=((len(rows)-1)//128)-1
                assert all(store.base_ids[b%store.base_slots]==b for b in range(low//128,hi+1));verified=c['reach']
            reachchecks.append(dict(key=c['key'],verified_continuous_reach=verified))
            snaps.append(dict(key=c['key'],bytes=len(payload),reserve=a['snapshot_slot_bytes'],margin=a['snapshot_slot_bytes']-len(payload)))
        np.savez_compressed(OUT/'units'/f'{ui:02d}.npz',queries=qs,state=states[poolmap],prediction=pred[poolmap],truth=truth)
        write(dest,dict(dataset=dataset,entity=ent,signature=signature,training_variance=float(np.var(train.astype(np.float64),axis=0).mean()),counts=counts,pool_configurations=len(stores),unique_query_method_cases=int(states.size),exact_numeric_checks=exact_checks,snapshot_checks=snaps,reach_checks=reachchecks,elapsed_seconds=time.perf_counter()-started))
        print(f'{ui+1}/13 {dataset}/{ent}: {len(qs)} queries x {len(stores)} unique states, {time.perf_counter()-started:.1f}s',flush=True)
    summarize(specs)
if __name__=='__main__':main()
