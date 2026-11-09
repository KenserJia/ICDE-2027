"""Symmetric validation of unchanged native recent/online policies, no test tuning."""
from pathlib import Path
from collections import defaultdict
import csv,datetime,hashlib,importlib.util,json,platform,sys,time
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'src'))
sp=importlib.util.spec_from_file_location('original_closure',ROOT/'repro/round78_rq_closure/run.py');old=importlib.util.module_from_spec(sp);sp.loader.exec_module(old)
from mtmemory_icde.core.history import Config
from mtmemory_icde.core.service import ControlledOverlayStore
OUT=ROOT/'results/rq3_symmetric_20261107';REPRO=ROOT/'repro/rq3_symmetric_20261107';POLICIES=('recent','online');DEFAULT='b64-f8-k16'
PROFILES={'legacy44780':dict(cap=44780,metadata=4096,verified=False),'verified50924':dict(cap=50924,metadata=6144,verified=True),'verified44780':dict(cap=44780,metadata=6144,verified=True)}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):p.write_text(json.dumps(v,indent=2,allow_nan=False)+'\n')
def account(s,M=6144):
    a=s.account();return dict(array_bytes=a['resident_array_bytes'],metadata_bytes=M,workspace_bytes=a['workspace_bytes'],snapshot_slot_bytes=a['resident_array_bytes']+M,charged_bytes=3*(a['resident_array_bytes']+M)+a['workspace_bytes'])
def make(c,policy):return ControlledOverlayStore(Config(budget=50924,channels=4,base_width=c['b'],fine_width=c['f'],max_reach=4096,overlay_capacity=c['k'],policy=policy,query_history=128),c['k'])
def layouts():
    out=[]
    for b in (32,64,128):
        for f in (4,8,16):
            for k in (0,8,16):
                if k==0 and f!=8:continue
                c=dict(name=f'b{b}-f{f}-k{k}',b=b,f=f,k=k)
                try:s=make(c,'recent')
                except MemoryError:continue
                legacy=account(s,4096)
                if legacy['charged_bytes']<=44780:out.append(dict(**c,legacy_charge=legacy['charged_bytes'],verified_charge=account(s)['charged_bytes']))
    assert len(out)==13;return out

def workloads():
    d={k:v['spec'] for k,v in json.loads((ROOT/'results/frozen/rq_closure/rq3_boundary/RQ3_FREEZE.json').read_text())['workloads'].items()}
    d.update(held12={'shift_buckets':12,'dwell_queries':32,'width_buckets':2},held24={'shift_buckets':24,'dwell_queries':64,'width_buckets':2},held28={'shift_buckets':28,'dwell_queries':8,'width_buckets':2})
    return d

def summarize(raw,selection,cs,specs,signature):
    selected=[];summary=[];same=[];factorial=[]
    index={(x['dataset'],x['entity'],x['workload'],x['policy'],x['layout']):x for x in raw}
    units=sorted({(x['dataset'],x['entity']) for x in raw})
    for sel in selection:
        x=index[sel['dataset'],sel['entity'],sel['workload'],sel['policy'],sel['selected']];prof=PROFILES[sel['profile']];charge=x['verified_charge'] if prof['verified'] else x['legacy_charge'];assert charge<=prof['cap']
        selected.append(dict(**x,profile=sel['profile'],budget=prof['cap'],charged_bytes=charge,validation_mse=sel['validation_mse']))
    for profile in PROFILES:
        for label in specs:
            rr=[x for x in selected if x['profile']==profile and x['workload']==label];ix={(x['dataset'],x['entity'],x['policy']):x for x in rr};a=[ix[d,e,'recent'] for d,e in units];b=[ix[d,e,'online'] for d,e in units];delta=[y['mse']-x['mse'] for x,y in zip(a,b)];tol=1e-12
            summary.append(dict(profile=profile,budget=PROFILES[profile]['cap'],workload=label,entities=13,candidates_per_policy=next(x['candidates'] for x in selection if x['profile']==profile),recent_mse=float(np.mean([x['mse'] for x in a])),online_mse=float(np.mean([x['mse'] for x in b])),online_minus_recent=float(np.mean(delta)),bootstrap95=old.bootstrap_ci(delta),online_wins=sum(d< -tol for d in delta),recent_wins=sum(d>tol for d in delta),ties=sum(abs(d)<=tol for d in delta),strict_online_wins=sum(d<0 for d in delta),strict_recent_wins=sum(d>0 for d in delta),minimum_coverage=min(x['coverage'] for x in rr),max_charged_bytes=max(x['charged_bytes'] for x in rr),zero_overlay_recent=sum(x['k']==0 for x in a),zero_overlay_online=sum(x['k']==0 for x in b)))
    for label in specs:
        for c in cs:
            d=[index[ds,en,label,'online',c['name']]['mse']-index[ds,en,label,'recent',c['name']]['mse'] for ds,en in units]
            same.append(dict(workload=label,layout=c['name'],legacy_charge=c['legacy_charge'],verified_charge=c['verified_charge'],mean_online_minus_recent=float(np.mean(d)),bootstrap95=old.bootstrap_ci(d),online_wins=sum(v< -1e-12 for v in d),recent_wins=sum(v>1e-12 for v in d),ties=sum(abs(v)<=1e-12 for v in d)))
    for label in specs:
        for ds,en in units:
            selected_ix={x['policy']:x for x in selection if x['profile']=='verified50924' and x['dataset']==ds and x['entity']==en and x['workload']==label}
            for rp,rn in [('default',DEFAULT),('tuned',selected_ix['recent']['selected'])]:
                for op,on in [('default',DEFAULT),('tuned',selected_ix['online']['selected'])]:
                    a=index[ds,en,label,'recent',rn];b=index[ds,en,label,'online',on];factorial.append(dict(dataset=ds,entity=en,workload=label,recent_tuning=rp,online_tuning=op,recent_layout=rn,online_layout=on,recent_mse=a['mse'],online_mse=b['mse'],online_minus_recent=b['mse']-a['mse']))
    # Exact reproduction of old one-sided comparison and all unchanged default outputs.
    archived=json.loads((ROOT/'results/review_revision_20261104/strong_fixed_raw.json').read_text());fixed_selection=json.loads((ROOT/'results/review_revision_20261104/fixed_selection.json').read_text());repro=[]
    for x in archived:
        pol='online' if x['method']=='dynamic' else 'recent';name=DEFAULT if x['method'] in ('dynamic','original_fixed') else x['layout'];new=index[x['dataset'],x['entity'],x['workload'],pol,name];diff=new['mse']-x['mse'];assert np.isclose(new['mse'],x['mse'],rtol=1e-12,atol=1e-15);assert new['queries']==x['queries'] and new['answered']==x['answered'];repro.append(dict(dataset=x['dataset'],entity=x['entity'],workload=x['workload'],method=x['method'],mse_difference=diff))
    for x in fixed_selection:
        y=next(y for y in selection if y['profile']=='legacy44780' and y['policy']=='recent' and all(y[k]==x[k] for k in ('dataset','entity','workload')));assert x['selected']==y['selected'];assert np.isclose(x['validation_mse'],y['validation_mse'],rtol=1e-12,atol=1e-15)
    write(OUT/'selected_results.json',selected);write(OUT/'summary.json',summary);write(OUT/'same_layout_summary.json',same);write(OUT/'factorial_results.json',factorial);write(OUT/'legacy_reproduction.json',repro)
    for name,rows in [('source_data',summary),('selected_entity_data',selected),('same_layout_data',same),('factorial_data',factorial)]:
        with (OUT/f'{name}.csv').open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    snapshots=[]
    for ui in range(13):
        for stage in ('validation','test'):snapshots.extend(json.loads((OUT/stage/f'{ui:02d}.json').read_text())['snapshot_checks'])
    assert all(x['margin']>=0 for x in snapshots)
    qa=dict(entities=13,workloads=6,policies=POLICIES,shared_grid13=True,candidates={p:sum((c['verified_charge'] if pr['verified'] else c['legacy_charge'])<=pr['cap'] for c in cs) for p,pr in PROFILES.items()},validation_selections=len(selection),all_selections_frozen_before_test=True,freeze_signature=signature,archived_rows_reproduced=len(repro),archived_selected_fixed_choices_reproduced=len(fixed_selection),maximum_archived_mse_difference=max(abs(x['mse_difference']) for x in repro),test_candidate_cases=sum(x['queries'] for x in raw),all_coverage_one=all(x['coverage']==1 for x in raw),snapshot_checks=len(snapshots),minimum_verified_snapshot_margin=min(x['margin'] for x in snapshots),production_source_unchanged=True,policy_hyperparameters_tuned=False,layout_hyperparameters_tuned=['b','f','k'],win_tolerance=1e-12,profile_reuse='legacy44780 and verified50924 use identical13-layout predictions; not independent replication',limits=['single macOS/arm64','12correlated stations','controlled ingestion-order schedules','entity/workload-specific validation warm-start','legacy44780 is nominal, not serialization-verified','verified ledger not an RSS cap','native active-cell semantics retained, no new certificate'])
    write(OUT/'QA.json',qa);print(json.dumps(summary,indent=2),flush=True);print(json.dumps(qa,indent=2),flush=True)

def main():
    OUT.mkdir(exist_ok=True)
    for sub in ('validation','test','validation_states'):(OUT/sub).mkdir(exist_ok=True)
    cs=layouts();specs=workloads();store_specs=[dict(workload=label,policy=pol,layout=c['name'],b=c['b'],f=c['f'],k=c['k'],legacy_charge=c['legacy_charge'],verified_charge=c['verified_charge']) for label in specs for pol in POLICIES for c in cs]
    write(OUT/'layouts.json',cs);write(OUT/'workloads.json',specs);write(OUT/'store_order.json',store_specs)
    paths=[Path(__file__),REPRO/'PROTOCOL.txt',ROOT/'src/mtmemory_icde/core/history.py',ROOT/'src/mtmemory_icde/core/service.py',ROOT/'repro/round78_rq_closure/run.py',ROOT/'data/real/bike.npz',ROOT/'data/real/beijing.npz',ROOT/'results/review_revision_20261104/strong_fixed_raw.json',ROOT/'results/review_revision_20261104/fixed_selection.json']
    hashes={str(p.relative_to(ROOT)):sha(p) for p in paths};signature=hashlib.sha256(json.dumps(hashes,sort_keys=True).encode()).hexdigest();env=OUT/'PROTOCOL_FREEZE.json'
    if env.exists():assert json.loads(env.read_text())['signature']==signature,'Frozen source/data changed'
    else:write(env,dict(signature=signature,hashes=hashes,profiles=PROFILES,python=sys.version,numpy=np.__version__,platform=platform.platform(),machine=platform.machine(),timestamp_utc=datetime.datetime.now(datetime.timezone.utc).isoformat()))
    units=old.all_split_units();allval=[];selection=[]
    for ui,(ds,en,train,val,test) in enumerate(units):
        dest=OUT/'validation'/f'{ui:02d}.json'
        if dest.exists():packet=json.loads(dest.read_text());assert packet['signature']==signature;allval.extend(packet['rows']);print(f'validation resume {ui}',flush=True);continue
        started=time.perf_counter();prefix=np.concatenate([train[-4096:],val]);by_t=defaultdict(list)
        for label,spec in specs.items():
            for q in old.workload_queries(len(val),spec,old.SEED+ui*31,warmup=2432,offset=4096):by_t[q['t']].append((label,q))
        stores=[make(c,c['policy']) for c in store_specs];indices={label:[i for i,c in enumerate(store_specs) if c['workload']==label] for label in specs};errors=[[] for s in stores];queries=defaultdict(int)
        for t,row in enumerate(prefix,1):
            for store in stores:store.observe(row);store.actions.clear()
            for label,q in by_t.get(t,()):
                truth=prefix[t-q['delay']-q['window']:t-q['delay']].astype(np.float64).mean(0);queries[label]+=1
                for i in indices[label]:
                    a=stores[i].query(q['delay'],q['window']);assert a['value'] is not None and np.all(np.isfinite(a['value']));errors[i].append(float(np.mean((a['value']-truth)**2)))
        rows=[];snap=[]
        for i,(store,c) in enumerate(zip(stores,store_specs)):
            assert len(errors[i])==queries[c['workload']]>0;rows.append(dict(dataset=ds,entity=en,**c,validation_mse=float(np.mean(errors[i])),queries=len(errors[i]),coverage=1.))
            blob=store.dumps();a=account(store);assert len(blob)<=a['snapshot_slot_bytes'];fn=OUT/'validation_states'/f'{ui:02d}_{i:03d}.npz';fn.write_bytes(blob);clone=ControlledOverlayStore.from_blob(blob,c['k']);assert all(np.array_equal(a,b) for a,b in zip(store.state_arrays().values(),clone.state_arrays().values()));snap.append(dict(store=i,bytes=len(blob),reserve=a['snapshot_slot_bytes'],margin=a['snapshot_slot_bytes']-len(blob),sha256=sha(fn)))
        packet=dict(dataset=ds,entity=en,signature=signature,rows=rows,snapshot_checks=snap,elapsed_seconds=time.perf_counter()-started);write(dest,packet);allval.extend(rows);print(f'validation {ui+1}/13 {ds}/{en}: {len(stores)} states in {time.perf_counter()-started:.1f}s',flush=True)
    for profile,prof in PROFILES.items():
        for ui,(ds,en,*_) in enumerate(units):
            for label in specs:
                for policy in POLICIES:
                    feasible=[x for x in allval if x['dataset']==ds and x['entity']==en and x['workload']==label and x['policy']==policy and x['coverage']==1 and (x['verified_charge'] if prof['verified'] else x['legacy_charge'])<=prof['cap']];chosen=min(feasible,key=lambda x:(x['validation_mse'],x['verified_charge'] if prof['verified'] else x['legacy_charge'],x['layout']));selection.append(dict(profile=profile,dataset=ds,entity=en,workload=label,policy=policy,selected=chosen['layout'],validation_mse=chosen['validation_mse'],candidates=len(feasible),selection_split='validation'))
    frozen=OUT/'SELECTION.json';serialized=json.dumps(selection,indent=2,allow_nan=False)+'\n';selection_hash=hashlib.sha256(serialized.encode()).hexdigest()
    if frozen.exists():assert frozen.read_text()==serialized;assert json.loads((OUT/'FREEZE.json').read_text())['selection_sha256']==selection_hash
    else:
        frozen.write_text(serialized);write(OUT/'FREEZE.json',dict(signature=signature,selection_sha256=selection_hash,test_queries_executed=0,timestamp_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),all_entity_workload_policy_selections=len(selection),selection_split='validation',state_snapshot_sha256={str(p.relative_to(OUT)):sha(p) for p in (OUT/'validation_states').glob('*.npz')}))
    print('ALL VALIDATION SELECTIONS FROZEN; commencing new test queries',flush=True)
    raw=[]
    for ui,(ds,en,train,val,test) in enumerate(units):
        dest=OUT/'test'/f'{ui:02d}.json'
        if dest.exists():packet=json.loads(dest.read_text());assert packet['signature']==signature and packet['selection_sha256']==selection_hash;raw.extend(packet['rows']);print(f'test resume {ui}',flush=True);continue
        started=time.perf_counter();prefix=np.concatenate([train[-4096:],val]);rows=np.concatenate([prefix,test]);offset=len(prefix);stores=[]
        freeze=json.loads((OUT/'FREEZE.json').read_text())
        for i,c in enumerate(store_specs):
            fn=OUT/'validation_states'/f'{ui:02d}_{i:03d}.npz';assert sha(fn)==freeze['state_snapshot_sha256'][str(fn.relative_to(OUT))];stores.append(ControlledOverlayStore.from_blob(fn.read_bytes(),c['k']))
        queries={label:old.workload_queries(len(test),spec,old.SEED+ui*31,warmup=2432,offset=offset) for label,spec in specs.items()};nq=len(next(iter(queries.values())));assert all(len(q)==nq for q in queries.values());by_t=defaultdict(list);indices={label:[i for i,c in enumerate(store_specs) if c['workload']==label] for label in specs};li={label:i for i,label in enumerate(specs)}
        for label,qs in queries.items():
            for qi,q in enumerate(qs):by_t[q['t']].append((label,qi,q))
        pred=np.full((len(stores),nq,4),np.nan);truth=np.empty((len(specs),nq,4));resolution=np.zeros((len(stores),nq),np.int8);meta=np.empty((len(specs),nq,4),np.int64)
        for t,row in enumerate(test,offset+1):
            for store in stores:store.observe(row);store.actions.clear()
            for label,qi,q in by_t.get(t,()):
                v=rows[t-q['delay']-q['window']:t-q['delay']].astype(np.float64).mean(0);truth[li[label],qi]=v;meta[li[label],qi]=[t,q['delay'],q['window'],0 if q['phase']=='near' else 1]
                for i in indices[label]:
                    a=stores[i].query(q['delay'],q['window']);assert a['value'] is not None and np.all(np.isfinite(a['value']));pred[i,qi]=a['value'];resolution[i,qi]=2 if a['resolution']=='EXACT' else 1
        assert np.all(np.isfinite(pred));result=[];snap=[];variance=float(np.var(train.astype(np.float64),axis=0).mean())
        for i,(store,c) in enumerate(zip(stores,store_specs)):
            err=np.mean((pred[i]-truth[li[c['workload']]])**2,axis=1);mse=float(np.mean(err));result.append(dict(dataset=ds,entity=en,**c,mse=mse,nrmse=float(np.sqrt(mse/variance)),queries=nq,answered=nq,coverage=1.,exact_fraction=float(np.mean(resolution[i]==2))))
            blob=store.dumps();a=account(store);assert len(blob)<=a['snapshot_slot_bytes'];clone=ControlledOverlayStore.from_blob(blob,c['k']);q=queries[c['workload']][-1];x=store.query(q['delay'],q['window'],record=False);y=clone.query(q['delay'],q['window'],record=False);assert np.array_equal(x['value'],y['value']);snap.append(dict(store=i,bytes=len(blob),reserve=a['snapshot_slot_bytes'],margin=a['snapshot_slot_bytes']-len(blob)))
        np.savez_compressed(OUT/'test'/f'{ui:02d}_queries.npz',query=meta,prediction=pred,truth=truth,resolution=resolution)
        packet=dict(dataset=ds,entity=en,signature=signature,selection_sha256=selection_hash,rows=result,snapshot_checks=snap,elapsed_seconds=time.perf_counter()-started);write(dest,packet);raw.extend(result);print(f'test {ui+1}/13 {ds}/{en}: {nq} queries/workload in {time.perf_counter()-started:.1f}s',flush=True)
    assert sha(frozen)==selection_hash and all(sha(ROOT/p)==h for p,h in hashes.items());write(OUT/'candidate_test_results.json',raw);summarize(raw,selection,cs,specs,signature)
if __name__=='__main__':main()
