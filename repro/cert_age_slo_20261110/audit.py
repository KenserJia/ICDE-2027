from pathlib import Path
import sys,json,importlib.util
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(Path(__file__).parent));sys.path.insert(0,str(ROOT/'src'));sys.path.insert(0,str(ROOT/'repro/review7_20261109'))
from common import OUT,write,units,selected,service_at
from exact import ExactPrefix
from mtmemory_icde.core.evidence_service import EvidenceService
spec=importlib.util.spec_from_file_location('newquality',Path(__file__).with_name('quality.py'));quality=importlib.util.module_from_spec(spec);spec.loader.exec_module(quality)

def main():
    U=list(units());sampled=0;files=0
    for p in sorted((OUT/'queries').glob('*.npz')):
        ui=int(p.name.split('-')[0]);ds,e,tr,va,te=U[ui];rows=np.concatenate([tr,va,te])
        with np.load(p) as z:
            assert np.all(z['sum_bound']<=z['span_bound'])
            for i in np.linspace(0,len(z['queries'])-1,32,dtype=int):
                t,d,w,*_=z['queries'][i];oracle=ExactPrefix(rows[t-d-w:t-d])
                for key in ['span_bound','sum_bound']:
                    assert oracle.contains(0,int(w),z['prediction'][i],z[key][i]),(p,i,key)
                sampled+=1
        files+=1
    sel=selected();live=[];max_prediction=max_bound=0.;matched=[]
    for ui in [0,1,13]:
        ds,e,tr,va,te=U[ui];rows=np.concatenate([tr,va,te]);var=float(np.var(tr.astype(float),axis=0).mean());tab=quality.Offline(rows,ui,'test')
        for B in [131072,262144]:
            group=[x for x in sel if x['unit']==ui and x['B']==B and x['prior']=='panels' and x['mode']=='sum' and x['objective']=='g01']
            for chosen in group:
                c=chosen['config'];R=chosen['R']
                for fraction in [.1,.5,.9]:
                    t=len(tr)+len(va)+int(len(te)*fraction);s=service_at(c,rows,t,'span');z=EvidenceService.loads(s.dumps())
                    z.options['certificate_mode']='sum';z.history.certificate_mode='sum'
                    assert s._arrays().keys()==z._arrays().keys()
                    assert all(np.array_equal(s._arrays()[k],z._arrays()[k]) for k in s._arrays())
                    assert s.account()['charged_bytes']==z.account()['charged_bytes']
                    qs=[]
                    for w in [17,60,127]:
                        for d in [0,1,60,256,R-w]:
                            if d+w<=min(R,t):qs.append((t,d,w,0,0))
                    q=np.asarray(qs,np.int64);pred,bd,truth,ex=tab.evaluate(q,c)
                    for i,(_,d,w,*_) in enumerate(qs):
                        a=s.query(0,d,w)['history'];b=z.query(0,d,w)['history']
                        assert np.array_equal(a['value'],b['value'])
                        assert np.all(b['total_bound']<=a['total_bound'])
                        oracle=ExactPrefix(rows[t-d-w:t-d])
                        assert oracle.contains(0,w,a['value'],a['total_bound']) and oracle.contains(0,w,b['value'],b['total_bound'])
                        for mode,h in [('span',a),('sum',b)]:
                            ep=float(np.max(np.abs(h['value']-pred[i])));eb=float(np.max(np.abs(h['total_bound']-bd[mode][i])))
                            max_prediction=max(max_prediction,ep);max_bound=max(max_bound,eb)
                            assert ep<1e-11 and eb<1e-10
                            for eps in [.01,.05,.1,.2]:
                                assert (np.sqrt(np.mean(h['total_bound']**2)/var)<=eps)==(np.sqrt(np.mean(bd[mode][i]**2)/var)<=eps)
                    # Test continuation after a coherent image including active state.
                    for row in rows[t:t+17]:z.observe(row)
                    zz=EvidenceService.loads(z.dumps())
                    assert all(np.array_equal(z._arrays()[k],zz._arrays()[k]) for k in z._arrays())
                    assert zz.account(len(zz.dumps()))['snapshot_fits']
                    live.append(dict(unit=ui,B=B,id=c['id'],t=t,queries=len(qs),restored=True))
            # At matched recent geometry, the independent ring exposes the same
            # populated supports. Record live numerical agreement separately.
            rec=next(x for x in group if x['variant']=='recent');c=rec['config'];o=c['options'];t=len(tr)+len(va)+len(te)//2
            age=dict(id=c['id'].replace('recent-','age-'),options=dict(engine='histogram',bins=1,age_rollup=True,**{k:o[k] for k in ['base_width','fine_width','overlay_capacity','max_reach','budget']}))
            a=service_at(c,rows,t);b=service_at(age,rows,t)
            valid=0
            for d,w in [(0,17),(1,60),(384-127,127),(2048-60,60),(o['max_reach']-127,127)]:
                aa=a.query(0,d,w)['history'];bb=b.query(0,d,w)['history']
                if d+w>t:
                    assert aa['status']==bb['status']=='UNKNOWN';continue
                valid+=1
                assert np.allclose(aa['value'],bb['value'],rtol=0,atol=1e-11)
                assert np.allclose(aa['total_bound'],bb['total_bound'],rtol=0,atol=1e-10)
            matched.append(dict(unit=ui,B=B,recent_id=c['id'],age_id=age['id'],queries=valid,recent_charge=a.account()['charged_bytes'],age_charge=b.account()['charged_bytes']))
        print('LIVE AUDIT',ui,ds,flush=True)
    write(OUT/'AUDIT.json',dict(passed=True,reconstructed_files=files,sampled_queries=sampled,certificates_checked_per_sample=2,live_queries=sum(x['queries'] for x in live),live_certificate_checks=2*sum(x['queries'] for x in live),live_cases=live,matched_age_cases=matched,max_live_offline_prediction_difference=max_prediction,max_live_offline_bound_difference=max_bound,scope='sampled exact rational reconstruction audit; live active/sealed/wrapped states and continued restored observations; not all reconstructed queries exact-checked'))
    print('AUDIT COMPLETE',sampled,'live',sum(x['queries'] for x in live),max_prediction,max_bound,flush=True)
if __name__=='__main__':main()
