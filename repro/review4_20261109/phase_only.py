from run import *
def main():
 out=[];specs=grid()
 for ui,(ds,en,tr,va,te) in enumerate(units()):
  tab=Tables(np.concatenate([tr,va,te]));var=float(np.var(tr.astype(float),axis=0).mean())
  for seed in range(3):
   anchors=np.unique(sched(len(tr)+len(va),len(tab.rows),20261109+ui*101+seed*10007)[:,0]);rng=np.random.default_rng(9900+seed*101+ui);qs=[]
   for t in anchors:
    for j in range(8):
     a=int(rng.integers(144,513));w=int(rng.choice([x for x in [16,32,64,128] if a-x>=128]));qs.append([t,1,0,0,a,w])
   q=np.array(qs)
   for B in BUDGETS:
    for R in RS:
     for h in HS:
      c=max([c for c in specs if c['B']==B and c['R']==R and c['b']==128 and c['h']==h],key=lambda c:c['k'])
      p,s,y,_=tab.eval(q,c);out.append(dict(unit=ui,dataset=ds,entity=en,seed=seed,**c,nrmse=float(np.sqrt(np.mean((p-y)**2)/var)),exact=float(np.mean(s==2))))
 write('phase_only.json',out)
if __name__=='__main__':main()
