"""Independent two-tier circular rollup with the same recent-age fine span."""
import threading
import numpy as np
from .numerics import MissingHistory, certified_mean
from .sum_aware import sum_aware_mean

class AgeRollupHistory:
    def __init__(self,b,f,k,R,c=4):
        self.b,self.f,self.k,self.R,self.channels=map(int,(b,f,k,R,c))
        if not 1<=f<=b<=2**20 or b%f or k<0 or not 1<=R<=2**20:
            raise ValueError('supported rollup geometry')
        self.slots=(R+b-1)//b+3;self.fine_slots=(k+1)*(b//f)
        for prefix,n in [('base',self.slots),('fine',self.fine_slots)]:
            setattr(self,prefix+'_ids',np.full(n,-1,np.int64))
            setattr(self,prefix+'_counts',np.zeros(n,np.int32))
            setattr(self,prefix+'_sums',np.zeros((n,c)))
            setattr(self,prefix+'_min',np.full((n,c),np.inf))
            setattr(self,prefix+'_max',np.full((n,c),-np.inf))
        self.active_id=-1;self.event_count=0;self.actions=[]
        self.certificate_mode='span';self._lock=threading.RLock()
    def _trim_actions(self):self.actions.clear()
    def observe(self,row):
        row=np.asarray(row,np.float32)
        if row.shape!=(self.channels,) or not np.all(np.isfinite(row)):
            raise ValueError('finite channel vector')
        with self._lock:
            t=self.event_count;self.active_id=t//self.b
            for prefix,width,n in [('base',self.b,self.slots),('fine',self.f,self.fine_slots)]:
                identity=t//width;j=identity%n
                ids=getattr(self,prefix+'_ids');sums=getattr(self,prefix+'_sums')
                counts=getattr(self,prefix+'_counts');mn=getattr(self,prefix+'_min');mx=getattr(self,prefix+'_max')
                if ids[j]!=identity:
                    ids[j]=identity;sums[j]=0;counts[j]=0;mn[j]=np.inf;mx[j]=-np.inf
                sums[j]+=row;counts[j]+=1
                np.minimum(mn[j],row,out=mn[j]);np.maximum(mx[j],row,out=mx[j])
            self.event_count+=1
    def _cells(self,lo,hi):
        for bid in range(lo//self.b,(hi-1)//self.b+1):
            base=bid*self.b;j=bid%self.slots
            if self.base_ids[j]!=bid:raise MissingHistory('coarse rollup identity')
            if bid!=self.active_id and lo<=base and hi>=base+self.b:
                yield base,int(self.base_counts[j]),self.base_sums[j],self.base_min[j],self.base_max[j]
            elif bid<self.active_id-self.k:
                yield base,int(self.base_counts[j]),self.base_sums[j],self.base_min[j],self.base_max[j]
            else:
                for fid in range(max(lo,base)//self.f,(min(hi,base+self.b)-1)//self.f+1):
                    q=fid%self.fine_slots
                    if self.fine_ids[q]!=fid:raise MissingHistory('fine rollup identity')
                    yield fid*self.f,int(self.fine_counts[q]),self.fine_sums[q],self.fine_min[q],self.fine_max[q]
    def query(self,delay,window,record=True):
        delay=int(delay);window=int(window)
        with self._lock:
            hi=self.event_count-delay;lo=hi-window
            if delay<0 or window<=0 or delay+window>self.R or lo<0:
                return dict(status='UNKNOWN',value=None,resolution='UNKNOWN',bound=None)
            fn=certified_mean if self.certificate_mode=='span' else sum_aware_mean
            try:return fn(self._cells(lo,hi),lo,hi,self.channels,self.b)
            except MissingHistory:return dict(status='UNKNOWN',value=None,resolution='UNKNOWN',bound=None)
    def state_arrays(self):
        return {p+'_'+s:getattr(self,p+'_'+s) for p in ['base','fine'] for s in ['ids','counts','sums','min','max']}
    def export_meta(self):return dict(active_id=self.active_id,event_count=self.event_count)
    def restore_meta(self,meta):
        for k,v in meta.items():setattr(self,k,int(v))
    @property
    def workspace_bytes(self):return 8192
    @property
    def derived_payload_bytes(self):return 0
