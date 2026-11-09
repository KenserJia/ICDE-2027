"""Append-only native summaries with per-query deterministic range certificates.

Deletion is deliberately outside this augmented representation. All min/max arrays
are charged and serialized. Certificates refer to input float32 values, excluding
floating-point rounding in summation. The additional rounding_bound is a
conservative binary64 allowance under round-to-nearest, without overflow.
"""
import numpy as np
from .history import TieredOverlayStore

class CertifiedHistory(TieredOverlayStore):
    def __init__(self,cfg):
        self._initializing=True
        super().__init__(cfg)
        c=cfg.channels;k=cfg.overlay_capacity
        self.base_min=np.full((self.base_slots,c),np.inf);self.base_max=np.full((self.base_slots,c),-np.inf)
        self.fine_min=np.full((k,self.sub,c),np.inf);self.fine_max=np.full((k,self.sub,c),-np.inf)
        self.active_min=np.full((self.sub,c),np.inf);self.active_max=np.full((self.sub,c),-np.inf)
        self._initializing=False
        if self.account()['charged_bytes']>cfg.budget:raise MemoryError('certificate arrays exceed budget')
    def account(self):
        out=super().account()
        extra=0 if getattr(self,'_initializing',True) else sum(getattr(self,n).nbytes for n in ['base_min','base_max','fine_min','fine_max','active_min','active_max'])
        out['certificate_array_bytes']=extra;out['resident_array_bytes']+=extra;out['snapshot_slot_bytes']+=extra;out['charged_bytes']+=3*extra
        return out
    def state_arrays(self):
        out=super().state_arrays();out.update({n:getattr(self,n).copy() for n in ['base_min','base_max','fine_min','fine_max','active_min','active_max']});return out
    def _seal_active(self):
        bid=self.active_id
        if bid<0:return
        mn=self.active_min.copy();mx=self.active_max.copy()
        super()._seal_active()
        slot=self._base_slot(bid);self.base_min[slot]=mn.min(0);self.base_max[slot]=mx.max(0)
        oi=self._overlay_slot(bid)
        if oi is not None:self.fine_min[oi]=mn;self.fine_max[oi]=mx
        self.active_min.fill(np.inf);self.active_max.fill(-np.inf)
    def observe(self,row):
        row=np.asarray(row,np.float32)
        if row.shape!=(self.cfg.channels,) or not np.all(np.isfinite(row)):raise ValueError('finite channel vector required')
        with self._lock:
            super().observe(row);sid=((self.event_count-1)%self.cfg.base_width)//self.cfg.fine_width
            self.active_min[sid]=np.minimum(self.active_min[sid],row);self.active_max[sid]=np.maximum(self.active_max[sid],row)
            if len(self.actions)>256:self.actions[:]=self.actions[-256:]
    def _score(self,bid):
        if self.cfg.policy!='error':return super()._score(bid)
        hist=self.q_delays[self.q_delays>=0];target=hist if len(hist) else np.asarray(self.cfg.catalog_delays)
        age=max(0,self.event_count//self.cfg.base_width-bid)
        demand=float(np.exp(-np.abs(target/self.cfg.base_width-age)/2).sum())
        oi=self._overlay_slot(bid)
        if bid==self.active_id:mn,mx=self.active_min,self.active_max
        elif oi is not None:mn,mx=self.fine_min[oi],self.fine_max[oi]
        else:return 0.
        valid=np.all(np.isfinite(mn)&np.isfinite(mx),axis=1)
        if not np.any(valid):return 0.
        gain=np.maximum(0,(mx[valid].max(0)-mn[valid].min(0))-np.mean(mx[valid]-mn[valid],axis=0)).mean()
        return demand*float(gain)
    def promote_from_replay(self,bid):raise NotImplementedError('certified replay promotion is not implemented')
    def delete_event(self,eid):raise NotImplementedError('certified variant is append-only')
    def query(self,delay,window,record=True):
        delay=int(delay);window=int(window)
        with self._lock:
            end=self.event_count-delay;start=end-window
            if delay<0 or window<=0 or delay+window>self.cfg.max_reach or start<0:return {'status':'UNKNOWN','value':None,'resolution':'UNKNOWN','bound':None}
            if record:
                p=self.q_pos%len(self.q_delays);self.q_delays[p]=delay;self.q_windows[p]=window;self.q_pos+=1
            total=np.zeros(self.cfg.channels);bound=np.zeros(self.cfg.channels);magnitude=np.zeros(self.cfg.channels);covered=0;partial=False;terms=0
            for bid in range(start//self.cfg.base_width,(end-1)//self.cfg.base_width+1):
                base=bid*self.cfg.base_width;slot=self._base_slot(bid);oi=self._overlay_slot(bid)
                if bid==self.active_id:cells=[(base+j*self.cfg.fine_width,int(n),self.active_sums[j],self.active_min[j],self.active_max[j]) for j,n in enumerate(self.active_counts) if n]
                elif self.base_ids[slot]!=bid:return {'status':'UNKNOWN','value':None,'resolution':'UNKNOWN','bound':None}
                elif oi is not None:cells=[(base+j*self.cfg.fine_width,int(n),self.overlay_sums[oi,j],self.fine_min[oi,j],self.fine_max[oi,j]) for j,n in enumerate(self.overlay_counts[oi]) if n]
                else:cells=[(base,int(self.base_counts[slot]),self.base_sums[slot],self.base_min[slot],self.base_max[slot])]
                for left,m,s,mn,mx in cells:
                    r=max(0,min(end,left+m)-max(start,left))
                    if r:
                        total+=r/m*s;covered+=r;terms+=1
                        magnitude+=r*np.maximum(np.abs(mn),np.abs(mx))
                        if r!=m:bound+=r*(m-r)/m*(mx-mn);partial=True
            if covered!=window:return {'status':'UNKNOWN','value':None,'resolution':'UNKNOWN','bound':None}
            # A cell sum has at most b additions; query arithmetic adds at most
            # terms+8 dependent operations. Bound and magnitude accumulation
            # are inflated separately. This does not cover input conversion.
            u=np.finfo(np.float64).eps/2
            gamma=lambda n:n*u/(1-n*u)
            analytical=bound/window
            g=gamma(self.cfg.base_width+terms+8)
            rounding=np.nextafter((g*magnitude/window+gamma(terms+8)*analytical)/(1-g),np.inf)
            total_bound=np.nextafter(analytical+rounding,np.inf)
            return {'status':'ANSWERED','value':total/window,'resolution':'APPROX' if partial else 'EXACT','bound':analytical,'rounding_bound':rounding,'total_bound':total_bound}
