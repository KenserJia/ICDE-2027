"""Append-only extrema histories with controlled overlays and derived caching."""
from collections import OrderedDict
import numpy as np
from .certified import CertifiedHistory
from .service import ControlledOverlayStore
from .numerics import MissingHistory,certified_mean

class JointCertifiedHistory(CertifiedHistory):
    def __init__(self,cfg,active_capacity=None,fused=True,cache_capacity=0):
        if not 0<cfg.base_width<=2**20 or not 0<cfg.max_reach<=2**20:
            raise ValueError('supported length domain')
        self.active_capacity=cfg.overlay_capacity if active_capacity is None else int(active_capacity)
        if not 0<=self.active_capacity<=cfg.overlay_capacity:raise ValueError('active capacity')
        self.fused=bool(fused);self.cache_capacity=int(cache_capacity)
        if not 0<=self.cache_capacity<=32:raise ValueError('cache capacity')
        self.cache=OrderedDict();self.cache_hits=self.cache_misses=0
        super().__init__(cfg)
    def _overlay_slot(self,bid):
        hits=np.flatnonzero(self.overlay_ids[:self.active_capacity]==bid)
        return None if not len(hits) else int(hits[0])
    def _active_indices(self):return range(self.active_capacity)
    def _install_overlay(self,*args):return ControlledOverlayStore._install_overlay(self,*args)
    def _trim_actions(self):self.actions.clear()
    def observe(self,row):
        with self._lock:
            super().observe(row);self.cache.clear();self._trim_actions()
    def set_active_capacity(self,capacity):
        capacity=int(capacity)
        if not 0<=capacity<=len(self.overlay_ids):raise ValueError('active capacity')
        with self._lock:
            # Reorder in place. Only one row scratch array is live at a time.
            ranked=sorted([(self._score(int(bid)),int(bid)) for bid in self.overlay_ids if bid>=0],reverse=True)[:capacity]
            before=self.active_capacity
            for dest,(score,bid) in enumerate(ranked):
                source=int(np.flatnonzero(self.overlay_ids==bid)[0])
                if source!=dest:
                    for array in [self.overlay_sums,self.overlay_counts,self.fine_min,self.fine_max]:
                        scratch=array[dest].copy();array[dest]=array[source];array[source]=scratch
                        del scratch
                    for array in [self.overlay_ids,self.overlay_scores]:
                        scratch=array[dest].item();array[dest]=array[source];array[source]=scratch
                self.overlay_scores[dest]=score
            self.active_capacity=capacity
            self.overlay_ids[capacity:]=-1;self.overlay_sums[capacity:]=0;self.overlay_counts[capacity:]=0;self.overlay_scores[capacity:]=0
            self.fine_min[capacity:]=np.inf;self.fine_max[capacity:]=-np.inf
            self.cache.clear();return before!=capacity
    def drop_overlay(self,bid):
        with self._lock:
            j=self._overlay_slot(int(bid));self.cache.clear();result=super().drop_overlay(int(bid))
            if j is not None:self.fine_min[j].fill(np.inf);self.fine_max[j].fill(-np.inf)
            self._trim_actions();return result
    def _cells(self,lo,hi):
        b=self.cfg.base_width;f=self.cfg.fine_width
        for bid in range(lo//b,(hi-1)//b+1):
            base=bid*b;slot=self._base_slot(bid)
            if bid==self.active_id:
                sums,counts,mn,mx=self.active_sums,self.active_counts,self.active_min,self.active_max
            elif self.base_ids[slot]!=bid:raise MissingHistory('segment identity')
            elif self.fused and lo<=base and hi>=base+b:
                yield base,int(self.base_counts[slot]),self.base_sums[slot],self.base_min[slot],self.base_max[slot];continue
            else:
                j=self._overlay_slot(bid)
                if j is None:
                    yield base,int(self.base_counts[slot]),self.base_sums[slot],self.base_min[slot],self.base_max[slot];continue
                sums,counts,mn,mx=self.overlay_sums[j],self.overlay_counts[j],self.fine_min[j],self.fine_max[j]
            for j in range(max(0,(lo-base)//f),min(self.sub-1,(hi-1-base)//f)+1):
                if counts[j]:yield base+j*f,int(counts[j]),sums[j],mn[j],mx[j]
    @staticmethod
    def _copy(a):return {k:v.copy() if isinstance(v,np.ndarray) else v for k,v in a.items()}
    def query(self,delay,window,record=True):
        delay=int(delay);window=int(window)
        with self._lock:
            end=self.event_count-delay;start=end-window
            if delay<0 or window<=0 or delay+window>self.cfg.max_reach or start<0:
                return dict(status='UNKNOWN',value=None,resolution='UNKNOWN',bound=None)
            if record:
                p=self.q_pos%len(self.q_delays);self.q_delays[p]=delay;self.q_windows[p]=window;self.q_pos+=1
            key=(delay,window)
            if key in self.cache:
                self.cache_hits+=1;value=self.cache.pop(key);self.cache[key]=value;return self._copy(value)
            self.cache_misses+=1
            try:answer=certified_mean(self._cells(start,end),start,end,self.cfg.channels,self.cfg.base_width)
            except MissingHistory:return dict(status='UNKNOWN',value=None,resolution='UNKNOWN',bound=None)
            if self.cache_capacity:
                if len(self.cache)>=self.cache_capacity:self.cache.popitem(last=False)
                self.cache[key]=self._copy(answer)
            return answer
    def state_arrays(self):
        # Views are read only by the service serializer under its enclosing lock.
        return {n:getattr(self,n) for n in ['base_ids','base_sums','base_counts','overlay_ids','overlay_sums','overlay_counts','overlay_scores','active_sums','active_counts','q_delays','q_windows','replay_ids','replay_rows','replay_live','base_min','base_max','fine_min','fine_max','active_min','active_max']}
    def export_meta(self):return dict(active_id=self.active_id,event_count=self.event_count,q_pos=self.q_pos,replay_pos=self.replay_pos,active_capacity=self.active_capacity)
    def restore_meta(self,meta):
        for k,v in meta.items():setattr(self,k,int(v))
        self.cache.clear();self.actions.clear()
    @property
    def workspace_bytes(self):return max(8192,self.sub*self.cfg.channels*8)
    @property
    def derived_payload_bytes(self):return 256*self.cache_capacity
