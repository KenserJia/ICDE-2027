"""Experimental certificate execution paths; no change to production classes.

The fused path uses coarse sums for fully covered sealed segments and visits
only intersected fine cells. Min/max spans only contribute analytical error for
partial cells; magnitude still bounds rounding for every contributing chunk.
The bounded response cache is derived state, cleared on every observation or
explicit overlay drop and on restore. Its payload reservation is separate.
"""
from collections import OrderedDict
import numpy as np
from mtmemory_icde.core.certified import CertifiedHistory
class FusedCertified(CertifiedHistory):
 def query(self,delay,window,record=True,certificate=True):
  delay=int(delay);window=int(window)
  with self._lock:
   end=self.event_count-delay;start=end-window
   if delay<0 or window<=0 or delay+window>self.cfg.max_reach or start<0:return {'status':'UNKNOWN','value':None,'resolution':'UNKNOWN','bound':None}
   if record:
    p=self.q_pos%len(self.q_delays);self.q_delays[p]=delay;self.q_windows[p]=window;self.q_pos+=1
   total=np.zeros(self.cfg.channels);bound=np.zeros(self.cfg.channels);magnitude=np.zeros(self.cfg.channels);covered=0;partial=False;terms=0;b=self.cfg.base_width;f=self.cfg.fine_width
   for bid in range(start//b,(end-1)//b+1):
    base=bid*b;slot=self._base_slot(bid)
    if bid==self.active_id:
     sums,counts,mn,mx=self.active_sums,self.active_counts,self.active_min,self.active_max
    elif self.base_ids[slot]!=bid:return {'status':'UNKNOWN','value':None,'resolution':'UNKNOWN','bound':None}
    elif start<=base and end>=base+int(self.base_counts[slot]):
     # Full sealed segments use the mandatory coarse sum, even with an overlay.
     m=int(self.base_counts[slot]);total+=self.base_sums[slot];covered+=m;terms+=1
     if certificate:magnitude+=m*np.maximum(np.abs(self.base_min[slot]),np.abs(self.base_max[slot]))
     continue
    else:
     oi=self._overlay_slot(bid)
     if oi is None:
      m=int(self.base_counts[slot]);r=max(0,min(end,base+m)-max(start,base))
      if r:
       total+=r/m*self.base_sums[slot];covered+=r;terms+=1
       if r!=m:
        partial=True
        if certificate:bound+=r*(m-r)/m*(self.base_max[slot]-self.base_min[slot])
       if certificate:magnitude+=r*np.maximum(np.abs(self.base_min[slot]),np.abs(self.base_max[slot]))
      continue
     sums,counts,mn,mx=self.overlay_sums[oi],self.overlay_counts[oi],self.fine_min[oi],self.fine_max[oi]
    lo=max(0,(start-base)//f);hi=min(self.sub-1,(end-1-base)//f)
    for j in range(lo,hi+1):
     m=int(counts[j])
     if not m:continue
     left=base+j*f;r=max(0,min(end,left+m)-max(start,left))
     if r:
      total+=r/m*sums[j];covered+=r;terms+=1
      if r!=m:
       partial=True
       if certificate:bound+=r*(m-r)/m*(mx[j]-mn[j])
      if certificate:magnitude+=r*np.maximum(np.abs(mn[j]),np.abs(mx[j]))
   if covered!=window:return {'status':'UNKNOWN','value':None,'resolution':'UNKNOWN','bound':None}
   answer={'status':'ANSWERED','value':total/window,'resolution':'APPROX' if partial else 'EXACT','bound':None}
   if certificate:
    u=np.finfo(np.float64).eps/2;gamma=lambda n:n*u/(1-n*u)
    analytical=bound/window;g=gamma(b+terms+8)
    rounding=np.nextafter((g*magnitude/window+gamma(terms+8)*analytical)/(1-g),np.inf)
    answer.update(bound=analytical,rounding_bound=rounding,total_bound=np.nextafter(analytical+rounding,np.inf))
   return answer
class CachedCertified(FusedCertified):
 CAPACITY=32
 # 16B key + 5 vectors of four float64s + 16B bounded scalar fields, rounded up.
 # Python object overhead is outside this payload ledger; no physical RAM claim.
 PAYLOAD_RESERVE=CAPACITY*256
 def __init__(self,cfg):
  self.cache=OrderedDict();self.cache_hits=0;self.cache_misses=0
  super().__init__(cfg)
 @staticmethod
 def copy_answer(a):return {k:v.copy() if isinstance(v,np.ndarray) else v for k,v in a.items()}
 def observe(self,row):
  with self._lock:self.cache.clear();return super().observe(row)
 def drop_overlay(self,bid):
  with self._lock:self.cache.clear();return super().drop_overlay(bid)
 def query(self,delay,window,record=True,certificate=True):
  with self._lock:
   key=(int(delay),int(window),bool(certificate))
   if key in self.cache:
    self.cache_hits+=1;answer=self.cache.pop(key);self.cache[key]=answer
    if record and answer['status']=='ANSWERED':
     p=self.q_pos%len(self.q_delays);self.q_delays[p]=delay;self.q_windows[p]=window;self.q_pos+=1
    return self.copy_answer(answer)
   self.cache_misses+=1;answer=super().query(delay,window,record,certificate)
   if len(self.cache)>=self.CAPACITY:self.cache.popitem(last=False)
   self.cache[key]=self.copy_answer(answer)
   return answer
