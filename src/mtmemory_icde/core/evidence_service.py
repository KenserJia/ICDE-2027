"""Certificate and recent-age allocation controls under the existing joint codec."""
from .strong_baselines import ComparisonService
from .joint_history import JointCertifiedHistory
from .histogram import VOptimalHistory
from .numerics import MissingHistory
from .sum_aware import sum_aware_mean
from .age_rollup import AgeRollupHistory

class SumAwareNative(JointCertifiedHistory):
    def query(self,delay,window,record=True):
        if self.certificate_mode=='span':return super().query(delay,window,record)
        delay=int(delay);window=int(window)
        with self._lock:
            hi=self.event_count-delay;lo=hi-window
            if delay<0 or window<=0 or delay+window>self.cfg.max_reach or lo<0:
                return dict(status='UNKNOWN',value=None,resolution='UNKNOWN',bound=None)
            if record:
                p=self.q_pos%len(self.q_delays);self.q_delays[p]=delay;self.q_windows[p]=window;self.q_pos+=1
            key=(delay,window)
            if key in self.cache:
                self.cache_hits+=1;a=self.cache.pop(key);self.cache[key]=a;return self._copy(a)
            self.cache_misses+=1
            try:a=sum_aware_mean(self._cells(lo,hi),lo,hi,self.cfg.channels,self.cfg.base_width)
            except MissingHistory:return dict(status='UNKNOWN',value=None,resolution='UNKNOWN',bound=None)
            if self.cache_capacity:
                if len(self.cache)>=self.cache_capacity:self.cache.popitem(last=False)
                self.cache[key]=self._copy(a)
            return a

class SumAwareHistogram(VOptimalHistory):
    def query(self,delay,window,record=True):
        if self.certificate_mode=='span':return super().query(delay,window,record)
        delay=int(delay);window=int(window)
        with self._lock:
            hi=self.event_count-delay;lo=hi-window
            if delay<0 or window<=0 or delay+window>self.R or lo<0:
                return dict(status='UNKNOWN',value=None,resolution='UNKNOWN',bound=None)
            try:return sum_aware_mean(self._cells(lo,hi),lo,hi,self.channels,self.b)
            except MissingHistory:return dict(status='UNKNOWN',value=None,resolution='UNKNOWN',bound=None)

class EvidenceService(ComparisonService):
    def __init__(self,*args,certificate_mode='span',age_rollup=False,**kwargs):
        if certificate_mode not in ['span','sum']:raise ValueError('certificate mode')
        super().__init__(*args,**kwargs)
        if self.options['engine']=='native':raise ValueError('certified engines only')
        if age_rollup:
            if self.options['engine']!='histogram':raise ValueError('rollup uses histogram codec branch')
            o=self.options
            self.history=AgeRollupHistory(o['base_width'],o['fine_width'],o['overlay_capacity'],o['max_reach'],self.CHANNELS)
        else:
            self.history.__class__=SumAwareNative if self.options['engine']=='certified' else SumAwareHistogram
        self.history.certificate_mode=certificate_mode
        self.options.update(certificate_mode=certificate_mode,age_rollup=bool(age_rollup))
        if not self.account()['within_budget']:raise MemoryError('evidence control exceeds budget')
