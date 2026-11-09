from run import *
from fractions import Fraction

def main():
 stats=[];raw=[]
 for ui,(ds,en,tr,va,te) in enumerate(units()):
  rows=np.concatenate([tr,va,te]);anchors=set(sched(len(tr)+len(va),len(rows),1900+ui)[:,0]);st=CertifiedHistory(cfg(128,8,8,4096));rec=dict(unit=ui,cases=0,violations=0,oracle_rounding_allowance=True)
  for t,row in enumerate(rows,1):
   st.observe(row);st.actions.clear()
   if t not in anchors:continue
   for d in [0,1,7]:
    for w in [17,63,127]:
     a=st.query(d,w,False);part=rows[t-d-w:t-d].astype(float);truth=part.mean(0);err=np.abs(a['value']-truth)
     allowance=256*np.finfo(float).eps*np.maximum(1,np.abs(part).max(0));rec['violations']+=int(np.any(err>a['total_bound']+allowance));rec['cases']+=1
     raw.append(np.concatenate(([ui,t,d,w],err,a['bound'],a['rounding_bound'])))
  blob=st.dumps();rec['image_overhead']=len(blob)-st.account()['resident_array_bytes'];assert rec['image_overhead']<8192;assert rec['violations']==0
  restored=CertifiedHistory.loads(blob);assert np.array_equal(st.query(0,63,False)['total_bound'],restored.query(0,63,False)['total_bound']);stats.append(rec)
 write('real_active_certificates.json',stats);np.savez_compressed(OUT/'real_active_certificate_queries.npz',values=np.asarray(raw))
 # Nonaligned step diagnostic, complementing preserved perfectlyalignedzeroerrorstep.
 rows=np.repeat(np.where(np.arange(8192)<4103,-1.,5.)[:,None],4,1).astype(np.float32);st=CertifiedHistory(cfg(128,8,8,4096));errs=[];bounds=[]
 for t,row in enumerate(rows,1):
  st.observe(row);st.actions.clear()
  if t>=4096 and t%17==0:
   for d in [0,7,383,2047,3500]:
    a=st.query(d,63,False);truth=rows[t-d-63:t-d].astype(float).mean(0);err=np.abs(a['value']-truth);assert np.all(err<=a['total_bound']+1e-10);errs.append(float(err.mean()));bounds.append(float(a['bound'].mean()))
 write('stress_unaligned_step.json',dict(queries=len(errs),mae=float(np.mean(errs)),mean_bound=float(np.mean(bounds)),violations=0))
 # Exact rational verification of native and certificate boundary cases.
 out=[]
 for name,pattern in [('cancellation',[2**90,1,-2**90,2**-90]),('extrema',[np.finfo(np.float32).max,-np.finfo(np.float32).max]),('tiny',[2**-140,-2**-140,2**-145]),('constant',[7])]:
  x=np.repeat(np.resize(np.array(pattern,np.float32),353)[:,None],4,1);s=CertifiedHistory(cfg(64,8,2,256));cases=0
  for t,row in enumerate(x,1):
   s.observe(row);s.actions.clear()
   if t not in [63,64,65,127,128,129,255,256,257,353]:continue
   for d in [0,1,7,35]:
    for w in [1,3,8,31,64,127]:
     if d+w>min(t,256):continue
     a=s.query(d,w,False);truth=sum([Fraction(float(z)) for z in x[t-d-w:t-d,0]],Fraction(0))/w
     assert abs(Fraction(float(a['value'][0]))-truth)<=Fraction(float(a['total_bound'][0]));cases+=1
  out.append(dict(signal=name,cases=cases,violations=0,oracle='exact rational float32 inputs'))
 write('rational_boundaries.json',out)
if __name__=='__main__':main()
