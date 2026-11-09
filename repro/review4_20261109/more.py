import run as r
from run import *
# Certified npz metadata exceeds6144: verified common reserve8192.
M=8192
r.M=8192
import importlib.util,statistics,random

def active():
 spec=importlib.util.spec_from_file_location('legacy_history',REPRO/'history_before.py');mod=importlib.util.module_from_spec(spec);sys.modules[spec.name]=mod;spec.loader.exec_module(mod)
 rng=np.random.default_rng(912);stats=[]
 for name in ['flat','ramp','spike','noise','cancellation']:
  x=np.ones((1025,4),np.float32)*7 if name=='flat' else np.repeat((np.arange(1025)/17 if name=='ramp' else np.where(np.arange(1025)%19==0,100,0) if name=='spike' else np.resize([2**50,1,-2**50,1],1025) if name=='cancellation' else rng.normal(size=1025))[:,None],4,1).astype(np.float32)
  for b,h,k in [(64,8,0),(64,8,2),(128,16,2)]:
   s=TieredOverlayStore(cfg(b,h,k,512));old=mod.TieredOverlayStore(mod.Config(**s.cfg.__dict__));cert=CertifiedHistory(s.cfg);rec=dict(signal=name,b=b,h=h,k=k,cases=0,legacy_changes=0,oracle_failures=0,exact_checks=0,certificate_violations=0,restores=0,max_legacy_difference=0.)
   for t,row in enumerate(x,1):
    for st in [s,old,cert]:st.observe(row);st.actions.clear()
    if t<129 or t%h not in [0,1,h-1]:continue
    for d in [0,1,3,15]:
     for w in [1,3,8,17,65,127]:
      if d+w>min(t,512):continue
      lo=t-d-w;hi=t-d;a=s.query(d,w,False);o=old.query(d,w,False);c=cert.query(d,w,False)
      # Independent support-aware reconstruction, using retained sealed/fine cells.
      total=np.zeros(4);den=0;exact=True
      for bid in range(lo//b,(hi-1)//b+1):
       fine=bid==s.active_id or np.any(s.overlay_ids==bid);hh=h if fine else b
       for left in range(bid*b,min((bid+1)*b,t),hh):
        right=min(left+hh,t);over=max(0,min(hi,right)-max(lo,left))
        if over:
         vals=x[left:right].astype(float);total+=vals.sum(0)*over/(right-left);den+=over;exact &= over==right-left
      oracle=total/den;scale=max(1,float(np.abs(x[:t]).max()));tol=256*np.finfo(float).eps*scale
      rec['oracle_failures']+=int(np.max(np.abs(a['value']-oracle))>tol)
      assert (a['resolution']=='EXACT')==exact
      if exact:
       rec['exact_checks']+=1;assert np.max(np.abs(a['value']-x[lo:hi].astype(float).mean(0)))<=tol
      err=np.abs(c['value']-x[lo:hi].astype(float).mean(0));rec['certificate_violations']+=int(np.any(err>c['total_bound']+tol))
      diff=float(np.max(np.abs(a['value']-o['value'])));rec['legacy_changes']+=int(diff>tol);rec['max_legacy_difference']=max(rec['max_legacy_difference'],diff);rec['cases']+=1
    if t in [257,513,1025]:
     z=TieredOverlayStore.loads(s.dumps());assert np.array_equal(z.query(0,65,False)['value'],s.query(0,65,False)['value']);rec['restores']+=1
   assert rec['oracle_failures']==rec['certificate_violations']==0;stats.append(rec)
 write('active_boundary.json',stats)
 print('active complete',sum(x['cases'] for x in stats),flush=True)

def model_eval(tab,q,width,degree,R):
 n=len(tab.rows)//width;x=tab.rows[:n*width].reshape(n,width,4);t=np.arange(width)-(width-1)/2;c0=x.mean(1);c1=np.einsum('i,nic->nc',t,x)/(t@t) if degree else np.zeros_like(c0)
 residual=x-c0[:,None]-t[None,:,None]*c1[:,None];norm=np.sqrt((residual**2).sum(1));lo=q[:,0]-q[:,4];hi=lo+q[:,5];w=q[:,5];pred=np.zeros((len(q),4));bd=pred.copy()
 # Primitive polynomial sum with exact full-cell prefix, rounded fitting independently audited.
 def F(pos):
  j=pos//width;u=pos%width
  return tab.p[j*width]+u[:,None]*c0[j]+(u*(u-width)/2)[:,None]*c1[j]
 pred=(F(hi)-F(lo))/w[:,None]
 for pos,right in [(lo,False),(hi-1,True)]:
  j=pos//width;left=j*width;ov=np.minimum(hi,left+width)-np.maximum(lo,left);use=np.ones(len(q),bool) if not right else j!=lo//width
  bd[use]+=(np.sqrt(ov[use]*(width-ov[use])/width)/w[use])[:,None]*norm[j[use]]
 s=np.where(q[:,4]>R,0,np.where((lo%width==0)&(hi%width==0),2,1));return pred,s,bd

def cost():
 # Serial paired measurements, alternating order; no concurrent/RPO claim.
 rng=np.random.default_rng(61);x=rng.normal(size=(12000,4)).astype(np.float32);out=[]
 for b,h,k in [(64,8,8),(128,8,8),(128,16,16)]:
  for rep in range(7):
   for cls in ([TieredOverlayStore,CertifiedHistory] if rep%2 else [CertifiedHistory,TieredOverlayStore]):
    st=cls(cfg(b,h,k,4096));update=[];query=[];begin=time.perf_counter_ns()
    for t,row in enumerate(x,1):
     z=time.perf_counter_ns();st.observe(row);st.actions.clear();update.append(time.perf_counter_ns()-z)
     if t>=4096 and t%4==0:
      z=time.perf_counter_ns();st.query((t*17)%3000,63,False);query.append(time.perf_counter_ns()-z)
    elapsed=(time.perf_counter_ns()-begin)/1e9;z=time.perf_counter_ns();blob=st.dumps();dump=(time.perf_counter_ns()-z)/1e6;assert len(blob)<=st.account()['resident_array_bytes']+M
    out.append(dict(b=b,h=h,k=k,rep=rep,method=cls.__name__,mixed_ops_per_second=(12000+len(query))/elapsed,update_p50_us=float(np.median(update)/1e3),query_p50_us=float(np.median(query)/1e3),query_p99_us=float(np.quantile(query,.99)/1e3),serialize_ms=dump,image_bytes=len(blob),ledger=ledger(st),certificate_bytes=st.account().get('certificate_array_bytes',0)))
 write('certificate_cost.json',out);print('cost complete',flush=True)

def studies():
 records=[];selection=[];meta=[];ablations=[];specs=grid(cert=True);native=grid();reserves={z:grid(reserve=z) for z in [32768,65536]};allcandidates=[]
 for ui,(ds,en,tr,va,te) in enumerate(units()):
  tab=Tables(np.concatenate([tr,va,te]));var=float(np.var(tr.astype(float),axis=0).mean());vq=sched(len(tr),len(tr)+len(va),900+ui,True);q=sched(len(tr)+len(va),len(tab.rows),1900+ui)
  # Reuse near/mid/far strata, add4096 far so bothreach regimes have remote demand.
  def profile(qq,R):
   qq=qq[qq[:,1]==1].copy()
   if R==4096:
    ix=qq[:,2]==2;qq[ix,4]-=4096
   return qq
  for R in [4096,16384]:
   v=profile(vq,R);tq=profile(q,R)
   models=[]
   for width in [32,64,128,256]:
    for d in [0,1]:
     st=PlatoRange(10000000,width,d,R);charge=3*(st.account()['resident_array_bytes']+M)+max(W,192*width+1024)
     models.append(dict(width=width,degree=d,charge=charge))
   for B in BUDGETS:
    feasible=[c for c in specs if c['B']==B and c['R']==R];model=[c for c in models if c['charge']<=B]
    for method,candidates in [('certified',feasible),('polynomial',model)]:
     if not candidates:meta.append(dict(unit=ui,B=B,R=R,method=method,infeasible=True));continue
     def evaluate(qq,c):
      if method=='certified':
       pp,ss,yy,bb=tab.eval(qq,c,True);return pp,ss,bb
      return model_eval(tab,qq,c['width'],c['degree'],R)
     losses=[]
     for c in candidates:
      p,s,bd=evaluate(v,c);lo=v[:,0]-v[:,4];truth=(tab.p[lo+v[:,5]]-tab.p[lo])/v[:,5,None];losses.append(float(np.mean((p-truth)**2)))
     ix=min(range(len(candidates)),key=lambda i:(losses[i],candidates[i]['charge']));c=candidates[ix];selection.append(dict(unit=ui,B=B,R=R,method=method,validation_mse=losses[ix],config=c))
     # Explicit freeze before test for each comparison, never select on test.
     write(f'baseline_freeze_{ui:02d}_{B}_{R}_{method}.json',selection[-1])
     p,s,bd=evaluate(tq,c);lo=tq[:,0]-tq[:,4];truth=(tab.p[lo+tq[:,5]]-tab.p[lo])/tq[:,5,None];ae=np.abs(p-truth);tol=1e-9
     assert np.all(ae<=bd+tol)
     if method=='certified':
      st=CertifiedHistory(cfg(c['b'],c['h'],c['k'],R));certbytes=st.account()['certificate_array_bytes']
     else:st=PlatoRange(10000000,c['width'],c['degree'],R);certbytes=None
     records.append(dict(unit=ui,dataset=ds,entity=en,B=B,R=R,method=method,config=c,metrics=metrics(tq,p,s,truth,var,bd),certificate_bytes=certbytes,positive_bound_utilization_median=float(np.median((ae/np.maximum(bd,1e-300))[bd>1e-12])) if np.any(bd>1e-12) else None,violations=int(np.sum(np.any(ae>bd+tol,axis=1)))))
     # Live model check, independent of offline endpoint primitive.
     if B==131072 and R==4096:
      live=CertifiedHistory(cfg(c['b'],c['h'],c['k'],R)) if method=='certified' else PlatoRange(10000000,c['width'],c['degree'],R)
      by={int(t):[] for t in tq[:,0]}
      for qi in range(0,len(tq),6):by[int(tq[qi,0])].append(qi)
      mx=0.;checks=0
      for t,row in enumerate(tab.rows,1):
       live.observe(row)
       if hasattr(live,'actions'):live.actions.clear()
       for qi in by.get(t,[]):
        z=live.query(int(tq[qi,4]-tq[qi,5]),int(tq[qi,5]),False);mx=max(mx,float(np.max(np.abs(z['value']-p[qi]))));assert mx<1e-9;assert np.all(np.abs(z['value']-truth[qi])<=z['total_bound']+1e-10);checks+=1
      assert len(live.dumps())<=live.account()['resident_array_bytes']+M
      meta.append(dict(unit=ui,method=method,live_checks=checks,max_difference=mx,snapshot_bytes=len(live.dumps())))
   # Joint reserve ablation and coarse/overlay ablations at all ordinarybudgets.
   for B in BUDGETS:
    for reserve in [0,32768,65536]:
     cand=[c for c in (native if reserve==0 else reserves[reserve]) if c['B']==B and c['R']==R]
     if not cand:
      ablations.append(dict(unit=ui,B=B,R=R,reserve=reserve,infeasible=True));continue
     def loss(c):
      p,s,y,_=tab.eval(v,c);return float(np.mean((p-y)**2))
     c=min(cand,key=lambda c:(loss(c),c['charge']));p,s,y,_=tab.eval(tq,c)
     ablations.append(dict(unit=ui,B=B,R=R,reserve=reserve,config=c,variant='full',metrics=metrics(tq,p,s,y,var)))
     if reserve==0:
      cut=((tq[:,0]-1)//c['b']-c['k'])*c['b'];ss=np.where(tq[:,0]-tq[:,4]>=cut,s,0)
      ablations.append(dict(unit=ui,B=B,R=R,reserve=0,config=c,variant='no_coarse',metrics=metrics(tq,p,ss,y,var)))
      cc=dict(c,k=0);pp,ss,yy,_=tab.eval(tq,cc);ablations.append(dict(unit=ui,B=B,R=R,reserve=0,config=cc,variant='no_overlay',metrics=metrics(tq,pp,ss,yy,var)))
  print('baseline/ablation unit',ui,flush=True)
  write('baseline_records.json',records);write('baseline_selections.json',selection);write('baseline_qa.json',meta);write('ablations.json',ablations)
 # Synthetic stress: actual certificate kernel, not offlinebound approximations.
 stress=[];rng=np.random.default_rng(44);n=8192;t=np.arange(n)
 for name,x in [('noise',rng.normal(size=n)),('trend',t/1000),('step',np.where(t<n//2,-1.,5.)),('spike',np.where(t%127==0,100.,0.)),('heavy_tail',rng.standard_t(2,size=n))]:
  st=CertifiedHistory(cfg(128,8,8,4096));rows=np.repeat(x[:,None],4,1).astype(np.float32);es=[];bounds=[]
  for ti,row in enumerate(rows,1):
   st.observe(row);st.actions.clear()
   if ti>=4096 and ti%17==0:
    for d in [0,7,383,2047,3500]:
     ans=st.query(d,63,False);truth=rows[ti-d-63:ti-d].astype(float).mean(0);err=np.abs(ans['value']-truth);assert np.all(err<=ans['total_bound']+1e-10);es.append(float(err.mean()));bounds.append(float(ans['bound'].mean()))
  stress.append(dict(signal=name,queries=len(es),mae=float(np.mean(es)),mean_bound=float(np.mean(bounds)),median_utilization=float(np.median(np.array(es)/np.maximum(bounds,1e-300))),violations=0))
 write('stress.json',stress)
if __name__=='__main__':
 
 if not (OUT/"active_boundary.json").exists():active()
 if not (OUT/"certificate_cost.json").exists():cost()
 studies()
