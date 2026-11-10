"""Paired certificate and age-allocation controls; selection freezes before test."""
from pathlib import Path
import sys,json,hashlib,importlib.util,itertools,time
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'src'))
spec=importlib.util.spec_from_file_location('prior_quality',ROOT/'repro/w1w4_20261110/quality.py')
prior=importlib.util.module_from_spec(spec);spec.loader.exec_module(prior)
from mtmemory_icde.core.evidence_service import EvidenceService
from mtmemory_icde.core.sum_aware import cell_bounds
from mtmemory_icde.core.numerics import gamma_upper
OUT=ROOT/'results/cert_age_slo_20261110'
OLD=ROOT/'results/w1w4_20261110'
EPS=[.01,.05,.1,.2]
FAMILIES=['recent','sse','bound','fixed','age']
def write(p,x):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(x,indent=2,allow_nan=False)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def configs(B,R):
    out=prior.configs(B,R)
    for c in out:
        s=EvidenceService(**c['options']);c['ledger']=s.account()
    for b,f,k in itertools.product([128,256],[8,16],[0,4,8,16]):
        o=dict(engine='histogram',bins=1,base_width=b,fine_width=f,overlay_capacity=k,max_reach=R,budget=B,age_rollup=True)
        try:s=EvidenceService(**o)
        except MemoryError:continue
        out.append(dict(id=f'age-b{b}-f{f}-k{k}',family='rollup',variant='age',options=o,ledger=s.account()))
    return out

def schedule(start,end,R,seed,kind):
    if kind=='panels':return prior.w2.schedule(start,end,R,seed,'random_uniform')
    rng=np.random.default_rng(seed);rows=[]
    low=max(start+1,8192,R if kind=='uniform_reach' else 8192)
    if low>end:return None
    for phase in range(256):
        eligible=np.arange(low+(phase-low)%256,end+1,256)
        if not len(eligible):return None
        t=int(rng.choice(eligible))
        for _ in range(6):
            w=int(rng.integers(16,129))
            if kind=='far_heavy':
                panel=int(rng.choice(3,p=[.1,.1,.8]));a,z=[(384,512),(1536,2048),(3072,4096) if R==4096 else (6144,8192)][panel]
                age=int(rng.integers(a,z+1))
            else:
                age=int(rng.integers(w,R+1));panel=0 if age<=512 else 1 if age<=2048 else 2
            rows.append((t,age-w,w,panel,0))
    return np.asarray(rows,np.int64)

class Offline:
    def __init__(self,rows,ui,stage):
        self.x=rows.astype(np.float64);self.p=np.vstack([np.zeros(4),np.cumsum(self.x,axis=0)])
        self.ui=ui;self.stage=stage;self.fixed={};self.hist={}
    def fixed_cells(self,width):
        if width not in self.fixed:
            n=len(self.x)//width;z=self.x[:n*width].reshape(n,width,4)
            self.fixed[width]=z.sum(1),z.min(1),z.max(1)
        return self.fixed[width]
    def histogram(self,b,variant):
        key=b,variant
        if key not in self.hist:
            name=f'hist-{b}.npz' if variant=='sse' else f'{variant}-b{b}.npz'
            path=OLD/'cache'/f'{self.stage}{self.ui}-{variant}'/name
            local=OUT/'partition_cache'/f'{self.stage}{self.ui}-{variant}'/name
            if not path.exists() and local.exists():path=local
            if path.exists():
                with np.load(path) as z:
                    self.hist[key]={q:{k:z[f'{q}/{k}'] for k in ['ends','sums','mins','maxs']} for q in [1,2,4]}
            else:
                n=len(self.x)//b
                if variant=='fixed':
                    blocks=self.x[:n*b].reshape(n,b,4);out={}
                    for q in [1,2,4]:
                        z=blocks.reshape(n,q,b//q,4)
                        out[q]=dict(ends=np.tile(np.arange(1,q+1,dtype=np.int32)*(b//q),(n,1)),sums=z.sum(2),mins=z.min(2),maxs=z.max(2))
                else:
                    # Prior validation cuts are causal block-local summaries.
                    # Reuse that prefix, then solve only the new test suffix.
                    val=OLD/'cache'/f'val{self.ui}-{variant}'/name
                    with np.load(val) as z:
                        prefix={q:{k:z[f'{q}/{k}'] for k in ['ends','sums','mins','maxs']} for q in [1,2,4]}
                    n0=len(prefix[1]['ends']);assert n0<=n
                    out={q:dict(ends=np.zeros((n,q),np.int32),sums=np.zeros((n,q,4)),mins=np.zeros((n,q,4)),maxs=np.zeros((n,q,4))) for q in [1,2,4]}
                    for q in out:
                        for k in out[q]:out[q][k][:n0]=prefix[q][k]
                    solver=prior.BoundWorkspace(b,4,4,prior.WIDTHS) if variant=='bound' else prior.HistogramWorkspace(b,4,4)
                    for bid in range(n0,n):
                        block=self.x[bid*b:(bid+1)*b];cuts=solver.solve(block)
                        for q in out:
                            out[q]['ends'][bid]=cuts[q][1:]
                            for j,(a,z) in enumerate(zip(cuts[q],cuts[q][1:])):
                                x=block[a:z];out[q]['sums'][bid,j]=x.sum(0);out[q]['mins'][bid,j]=x.min(0);out[q]['maxs'][bid,j]=x.max(0)
                local.parent.mkdir(parents=True,exist_ok=True)
                np.savez_compressed(local,**{f'{q}/{k}':v for q,d in out.items() for k,v in d.items()})
                self.hist[key]=out
        return self.hist[key]
    def evaluate(self,queries,c):
        o=c['options'];b=o['base_width'];t,d,w=queries[:,:3].T;hi=t-d;lo=hi-w
        cursor=lo.copy();N=len(lo);total=np.zeros((N,4));oldraw=total.copy();oldup=total.copy()
        raw=total.copy();upper=total.copy();mag=total.copy();terms=np.zeros(N,np.int64);partial=np.zeros(N,bool)
        is_tier=c['variant'] in ['recent','age']
        if not is_tier:item=self.histogram(b,c['variant'])[o['bins']]
        sum_gamma=gamma_upper(b)
        while np.any(cursor<hi):
            ix=np.flatnonzero(cursor<hi);pos=cursor[ix];bid=pos//b;base=bid*b
            active=bid==(t[ix]-1)//b
            full=(pos==base)&(hi[ix]>=base+b)&(~active)
            S=np.zeros((len(ix),4));mn=S.copy();mx=S.copy()
            if is_tier:
                cut=((t[ix]-1)//b-o['overlay_capacity'])*b
                h=np.where(((pos>=cut)|active)&(~full),o['fine_width'],b)
                left=pos//h*h;m=np.minimum(h,t[ix]-left)
                for width in np.unique(h):
                    a,z,y=self.fixed_cells(int(width));take=np.flatnonzero((h==width)&(m==width));j=left[take]//width
                    S[take]=a[j];mn[take]=z[j];mx[take]=y[j]
                for j in np.flatnonzero(m<h):
                    xx=self.x[left[j]:left[j]+m[j]];S[j]=xx.sum(0);mn[j]=xx.min(0);mx[j]=xx.max(0)
            else:
                left=np.empty(len(ix),np.int64);m=left.copy();sealed=np.flatnonzero(~active)
                local=pos[sealed]%b;j=(item['ends'][bid[sealed]]<=local[:,None]).sum(1)
                right=item['ends'][bid[sealed],j];l=np.where(j==0,0,item['ends'][bid[sealed],np.maximum(j-1,0)])
                left[sealed]=base[sealed]+l;m[sealed]=right-l
                S[sealed]=item['sums'][bid[sealed],j];mn[sealed]=item['mins'][bid[sealed],j];mx[sealed]=item['maxs'][bid[sealed],j]
                aa=np.flatnonzero(active);left[aa]=pos[aa];m[aa]=1;S[aa]=self.x[pos[aa]];mn[aa]=S[aa];mx[aa]=S[aa]
                if np.any(full):
                    a,z,y=self.fixed_cells(b);j=np.flatnonzero(full)
                    left[j]=base[j];m[j]=b;S[j]=a[bid[j]];mn[j]=z[bid[j]];mx[j]=y[bid[j]]
            r=np.minimum(hi[ix],left+m)-pos;assert np.all(r>0)
            total[ix]+=(r/m)[:,None]*S;terms[ix]+=1
            mag[ix]=np.nextafter(mag[ix]+np.nextafter(r[:,None]*np.maximum(np.abs(mn),np.abs(mx)),np.inf),np.inf)
            hit=r!=m;ii=ix[hit]
            if len(ii):
                a,au,z,zu=cell_bounds(S[hit],mn[hit],mx[hit],m[hit,None],r[hit,None],sum_gamma)
                oldraw[ii]+=a;oldup[ii]=np.nextafter(oldup[ii]+au,np.inf)
                raw[ii]+=z;upper[ii]=np.nextafter(upper[ii]+zu,np.inf)
            partial[ii]=True;cursor[ix]+=r
        pred=total/w[:,None]
        g=np.asarray([gamma_upper(b+int(v)+4) for v in terms])
        numerical=np.nextafter(g[:,None]*np.nextafter(mag/w[:,None],np.inf),np.inf)
        def finish(a,u):
            ana=a/w[:,None];bu=np.nextafter(u/w[:,None],np.inf)
            return np.nextafter(ana+np.nextafter(numerical+np.nextafter(np.maximum(0.,bu-ana),np.inf),np.inf),np.inf)
        span=finish(oldraw,oldup);tight=np.minimum(span,finish(raw,upper))
        truth=(self.p[hi]-self.p[lo])/w[:,None]
        return pred,{'span':span,'sum':tight},truth,~partial

def metric(q,p,bounds,truth,exact,var):
    groups={'all':np.ones(len(q),bool),**{name:q[:,3]==j for j,name in enumerate(['near','middle','far'])}}
    return {g:prior.w2.metrics(q,p,bounds,truth,exact,var,mask) for g,mask in groups.items() if np.any(mask)}

def main():
    OUT.mkdir(parents=True,exist_ok=True);units=list(prior.units())
    grids={(B,R):configs(B,R) for B,R in [(131072,4096),(262144,16384)]}
    packet=dict(cases=list(grids),families=FAMILIES,certificate_modes=['span','sum'],objectives=['mse','g01'],eps=EPS,
                primary='all14 original units; original equal-age-panel requests, paired with prior study',
                secondary='far-heavy(.1,.1,.8) and uniform full reach on prespecified bike0/beijing0/household0; skip Bike/R16384 uniform validation because insufficient prefix',
                geometry='b128/256,f8/16,k0/4/8/16; q1/2/4; retain all feasible candidates; no test-driven grid changes',
                selection='all validation choices globally freeze before test; independently by family/mode/objective/prior',
                source={str(p.relative_to(ROOT)):sha(p) for p in [Path(__file__),ROOT/'src/mtmemory_icde/core/sum_aware.py',ROOT/'src/mtmemory_icde/core/age_rollup.py',ROOT/'src/mtmemory_icde/core/evidence_service.py']})
    pp=OUT/'QUALITY_PROTOCOL.json'
    if pp.exists():assert json.loads(pp.read_text())==packet
    else:write(pp,packet)
    selected=[];skips=[]
    for ui,(ds,e,tr,va,te) in enumerate(units):
        dest=OUT/'validation'/f'{ui:02d}.json'
        if dest.exists():z=json.loads(dest.read_text());selected+=z['selected'];skips+=z['skipped'];continue
        tick=time.perf_counter();rows=np.concatenate([tr,va]);tab=Offline(rows,ui,'val');var=float(np.var(tr.astype(float),axis=0).mean())
        local=[];choices=[];skip=[]
        for (B,R),grid in grids.items():
            for prior_i,kind in enumerate(['panels','far_heavy','uniform_reach'] if ui in [0,1,13] else ['panels']):
                q=schedule(len(tr),len(rows),R,9100+ui*31+prior_i*100000,kind)
                if q is None:skip.append(dict(unit=ui,B=B,R=R,prior=kind,reason='insufficient validation prefix for complete reach'));continue
                for c in grid:
                    p,bd,truth,ex=tab.evaluate(q,c)
                    for mode in ['span','sum']:
                        local.append(dict(unit=ui,dataset=ds,entity=e,B=B,R=R,prior=kind,id=c['id'],variant=c['variant'],mode=mode,config=c,metrics=metric(q,p,bd[mode],truth,ex,var)))
                for variant,mode in itertools.product(FAMILIES,['span','sum']):
                    pool=[x for x in local if (x['B'],x['R'],x['prior'],x['variant'],x['mode'])==(B,R,kind,variant,mode)]
                    for objective in ['mse','g01']:
                        best=min(pool,key=lambda x:(x['metrics']['all']['mse'] if objective=='mse' else -x['metrics']['all']['G']['0.1'],x['config']['ledger']['charged_bytes'],x['id']))
                        choices.append({**best,'objective':objective})
        write(dest,dict(selected=choices,candidates=local,skipped=skip));selected+=choices;skips+=skip
        print('VALIDATION',ui,ds,round(time.perf_counter()-tick,2),flush=True)
    gate=OUT/'SELECTIONS.json'
    if gate.exists():assert json.loads(gate.read_text())==selected
    else:write(gate,selected)
    write(OUT/'SKIPPED.json',skips);signature=sha(gate);print('ALL FROZEN',len(selected),signature,flush=True)
    old=json.loads((OLD/'quality_records.json').read_text());records=[];control=[];matched=[]
    for ui,(ds,e,tr,va,te) in enumerate(units):
        dest=OUT/'test'/f'{ui:02d}.json'
        if dest.exists():z=json.loads(dest.read_text());records+=z['records'];control+=z['fixed_control'];matched+=z['matched_age'];continue
        tick=time.perf_counter();rows=np.concatenate([tr,va,te]);tab=Offline(rows,ui,'test');var=float(np.var(tr.astype(float),axis=0).mean());cache={};local=[];ctrl=[];match=[]
        def evaluate(c,B,R,kind):
            key=B,R,kind,c['id']
            if key not in cache:
                prior_i=['panels','far_heavy','uniform_reach'].index(kind)
                q=np.concatenate([schedule(len(tr)+len(va),len(rows),R,9200+ui*31+seed*1001+prior_i*100000,kind) for seed in range(3)])
                p,bd,truth,ex=tab.evaluate(q,c);m={mode:metric(q,p,bd[mode],truth,ex,var) for mode in ['span','sum']}
                cache[key]=m
                path=OUT/'queries'/f'{ui}-{B}-{R}-{kind}-{c["id"]}.npz';path.parent.mkdir(exist_ok=True)
                np.savez_compressed(path,queries=q,prediction=p,span_bound=bd['span'],sum_bound=bd['sum'],truth=truth,exact=ex)
            return cache[key]
        for chosen in [x for x in selected if x['unit']==ui]:
            m=evaluate(chosen['config'],chosen['B'],chosen['R'],chosen['prior'])
            local.append({k:v for k,v in chosen.items() if k!='metrics'}|dict(validation_metrics=chosen['metrics'],test=m[chosen['mode']],selection_sha256=signature))
            if chosen['variant']=='recent' and chosen['objective']=='g01':
                age_id=chosen['id'].replace('recent-','age-');pool=[c for c in grids[chosen['B'],chosen['R']] if c['id']==age_id]
                if pool:
                    age=pool[0];am=evaluate(age,chosen['B'],chosen['R'],chosen['prior'])
                    match.append(dict(unit=ui,dataset=ds,B=chosen['B'],R=chosen['R'],prior=chosen['prior'],mode=chosen['mode'],recent_id=chosen['id'],age_id=age_id,recent_charge=chosen['config']['ledger']['charged_bytes'],age_charge=age['ledger']['charged_bytes'],recent=m[chosen['mode']],age=am[chosen['mode']]))
        for chosen in [x for x in old if x['unit']==ui]:
            c=chosen['config'];m=evaluate(c,chosen['B'],chosen['R'],'panels')
            assert abs(m['span']['all']['G']['0.1']-chosen['test']['G']['0.1'])<1e-12
            ctrl.append({k:chosen[k] for k in ['unit','dataset','B','R','id','variant','objective']}|dict(metrics=m,prior_test=chosen['test']))
        write(dest,dict(records=local,fixed_control=ctrl,matched_age=match));records+=local;control+=ctrl;matched+=match
        print('TEST',ui,ds,round(time.perf_counter()-tick,2),flush=True)
    write(OUT/'quality_records.json',records);write(OUT/'FIXED_CONTROL.json',control);write(OUT/'MATCHED_AGE.json',matched)
    print('QUALITY COMPLETE',len(records),'fixed',len(control),'matched',len(matched),flush=True)

if __name__=='__main__':main()
