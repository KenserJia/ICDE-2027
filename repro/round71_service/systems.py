"""Contract-compliant bounded baselines for Round 7.1/7.2."""
from __future__ import annotations

from collections import Counter, OrderedDict
from dataclasses import dataclass
import math
import threading
import time

import numpy as np

from overlay import Config as OverlayConfig, TieredOverlayStore


STATUS = ("EXACT", "APPROX", "UNKNOWN")


def contract(status, reason, prefix, lo, hi, coverage, representation, value=None,
             fact_version=None):
    if status not in STATUS:
        raise ValueError(status)
    out = {"status": status, "reason": reason, "fact_version": fact_version,
           "prefix": int(prefix), "lo": int(lo), "hi": int(hi),
           "coverage": float(coverage), "representation": representation,
           "value": None if value is None else np.asarray(value, np.float64)}
    return out


class ExactTail:
    def __init__(self, budget=65536, channels=4, max_reach=2314):
        self.budget=budget;self.channels=channels;self.max_reach=max_reach
        per=channels*4+8
        self.capacity=max(1,min(max_reach,(budget-3*4096-2048)//(3*per)))
        self.rows=np.zeros((self.capacity,channels),np.float32)
        self.ids=np.full(self.capacity,-1,np.int64);self.n=0
        if self.account()['charged_bytes']>budget:raise MemoryError
    def observe(self,row):
        p=self.n%self.capacity;self.rows[p]=row;self.ids[p]=self.n;self.n+=1
    def query(self,delay,window,record=True):
        hi=self.n-int(delay);lo=hi-int(window)
        if lo<0:return contract('UNKNOWN','prehistory',self.n,lo,hi,0,'exact_tail')
        ids=np.arange(lo,hi,dtype=np.int64);slots=ids%self.capacity
        ok=self.ids[slots]==ids
        if not np.all(ok):return contract('UNKNOWN','history_gap',self.n,lo,hi,float(ok.mean()),'exact_tail')
        return contract('EXACT','answer',self.n,lo,hi,1,'exact_tail',self.rows[slots].astype(np.float64).mean(0))
    def account(self):
        a=self.rows.nbytes+self.ids.nbytes;slot=a+4096
        return {'resident_array_bytes':a,'snapshot_slots':2,'snapshot_slot_bytes':slot,
                'workspace_bytes':2048,'charged_bytes':a+4096+2*slot+2048,
                'budget_bytes':self.budget,'capacity_events':self.capacity}


class EHSum:
    """Bounded exponential-histogram-style SUM/COUNT reference.

    It keeps at most two adjacent blocks per level and prorates boundary blocks.
    This is a local reference implementation, not an external library result.
    """
    def __init__(self,budget=65536,channels=4,max_reach=2314,max_buckets=32):
        self.budget=budget;self.channels=channels;self.max_reach=max_reach;self.max_buckets=max_buckets
        self.blocks=[];self.n=0
        if self.account()['charged_bytes']>budget:raise MemoryError
    def observe(self,row):
        self.blocks.append({'lo':self.n,'hi':self.n+1,'sum':np.asarray(row,np.float64).copy(),'count':1,'level':0})
        self.n+=1;self._merge();self.blocks=[b for b in self.blocks if b['hi']>self.n-self.max_reach]
    def _merge(self):
        changed=True
        while changed:
            changed=False
            levels=sorted(set(b['level'] for b in self.blocks))
            for level in levels:
                ix=[i for i,b in enumerate(self.blocks) if b['level']==level]
                if len(ix)>2:
                    i,j=ix[0],ix[1];a,b=self.blocks[i],self.blocks[j]
                    merged={'lo':a['lo'],'hi':b['hi'],'sum':a['sum']+b['sum'],
                            'count':a['count']+b['count'],'level':level+1}
                    self.blocks[i:j+1]=[merged];changed=True;break
        while len(self.blocks)>self.max_buckets:
            a,b=self.blocks[0],self.blocks[1]
            self.blocks[:2]=[{'lo':a['lo'],'hi':b['hi'],'sum':a['sum']+b['sum'],
                             'count':a['count']+b['count'],'level':max(a['level'],b['level'])+1}]
    def query(self,delay,window,record=True):
        hi=self.n-int(delay);lo=hi-int(window)
        if lo<0:return contract('UNKNOWN','prehistory',self.n,lo,hi,0,'eh_sum')
        total=np.zeros(self.channels);count=0.;covered=0;approx=False;cursor=lo
        for b in self.blocks:
            left=max(lo,b['lo']);right=min(hi,b['hi'])
            if right<=left:continue
            if left>cursor:return contract('UNKNOWN','history_gap',self.n,lo,hi,covered/window,'eh_sum')
            frac=(right-left)/(b['hi']-b['lo']);total+=b['sum']*frac;count+=b['count']*frac
            covered+=right-left;cursor=right;approx |= frac<1
        if cursor<hi or count==0:return contract('UNKNOWN','history_gap',self.n,lo,hi,covered/window,'eh_sum')
        return contract('APPROX' if approx else 'EXACT','answer',self.n,lo,hi,1,'eh_sum',total/count)
    def account(self):
        per=8+8+self.channels*8+8+4+20;a=self.max_buckets*per;slot=a+4096
        return {'resident_reserved_bytes':a,'snapshot_slots':2,'snapshot_slot_bytes':slot,
                'workspace_bytes':2048,'charged_bytes':a+4096+2*slot+2048,
                'budget_bytes':self.budget,'max_buckets':self.max_buckets}


class OverlayHistory:
    def __init__(self,method,budget=65536):
        spec={
          'fixed_fine32':dict(base_width=32,overlay_capacity=0,policy='none'),
          'fixed_coarse64':dict(base_width=64,overlay_capacity=0,policy='none'),
          'base_only':dict(base_width=64,overlay_capacity=0,policy='none'),
          'fixed_multires':dict(base_width=64,overlay_capacity=16,policy='recent'),
          'online_overlay':dict(base_width=64,overlay_capacity=16,policy='online'),
        }[method]
        self.method=method;self.store=TieredOverlayStore(OverlayConfig(budget=budget,**spec))
    @property
    def n(self):return self.store.event_count
    def observe(self,row):self.store.observe(row)
    def query(self,delay,window,record=True):
        ans=self.store.query(delay,window,record);hi=self.n-delay;lo=hi-window
        if ans['status']=='UNKNOWN':return contract('UNKNOWN','history_gap',self.n,lo,hi,0,self.method)
        mode=ans['resolution'];status='EXACT' if mode=='EXACT' else 'APPROX'
        return contract(status,'answer',self.n,lo,hi,1,self.method,ans['value'])
    def account(self):return self.store.account()


def make_history(method,budget):
    if method=='exact_tail':return ExactTail(budget)
    if method=='eh_sum':return EHSum(budget)
    return OverlayHistory(method,budget)


@dataclass
class Fact:
    version:int
    live:bool
    value:np.ndarray


class FactCache:
    def __init__(self,capacity=64,policy='lru',channels=4):
        self.capacity=int(capacity);self.policy=policy;self.channels=channels
        self.data={};self.clock=0;self.freq=Counter();self.recency={};self.evictions=0;self.rejections=0
    def _touch(self,key):
        self.clock+=1;self.freq[int(key)]+=1;self.recency[int(key)]=self.clock
        if self.clock%4096==0:
            self.freq=Counter({k:max(1,v//2) for k,v in self.freq.items()})
    def put(self,key,value,version,live=True):
        key=int(key);self._touch(key);rec=Fact(int(version),bool(live),np.asarray(value,np.float32).copy())
        if key in self.data:self.data[key]=rec;return {'admitted':True,'evicted':None}
        if len(self.data)<self.capacity:self.data[key]=rec;return {'admitted':True,'evicted':None}
        if self.policy=='lru':victim=min(self.data,key=lambda k:self.recency.get(k,0))
        else:victim=min(self.data,key=lambda k:(self.freq[k],self.recency.get(k,0)))
        if self.policy=='tinylfu' and self.freq[key]<=self.freq[victim]:
            self.rejections+=1;return {'admitted':False,'evicted':None}
        del self.data[victim];self.recency.pop(victim,None);self.evictions+=1;self.data[key]=rec
        return {'admitted':True,'evicted':int(victim)}
    def get(self,key):
        key=int(key);self._touch(key)
        rec=self.data.get(key)
        if rec is None:return None
        return Fact(rec.version,rec.live,rec.value.copy())
    def delete(self,key,version):
        key=int(key);self._touch(key)
        if key in self.data:self.data[key]=Fact(int(version),False,np.zeros(self.channels,np.float32));return True
        return False
    def account(self):
        per=8+8+1+self.channels*4+8+8+23
        return {'capacity':self.capacity,'entries':len(self.data),'resident_reserved_bytes':self.capacity*per,
                'evictions':self.evictions,'admission_rejections':self.rejections,'policy':self.policy}


class UnifiedService:
    def __init__(self,history_method='online_overlay',budget=65536,fact_capacity=64,fact_policy='lru'):
        self.history=make_history(history_method,budget);self.facts=FactCache(fact_capacity,fact_policy)
        self.version=0;self._lock=threading.RLock()
    def observe(self,row):
        with self._lock:self.history.observe(row)
    def put_fact(self,key,value,delete=False):
        with self._lock:
            self.version+=1
            if delete:self.facts.delete(key,self.version)
            else:self.facts.put(key,value,self.version,True)
            return self.version
    def query(self,key,delay,window,record=True):
        with self._lock:
            fact=self.facts.get(key);n=self.history.n
            if fact is None:return contract('UNKNOWN','fact_not_resident',n,n-delay-window,n-delay,0,'none',fact_version=None)
            if not fact.live:return contract('UNKNOWN','fact_deleted',n,n-delay-window,n-delay,0,'none',fact_version=fact.version)
            out=self.history.query(delay,window,record);out['fact_version']=fact.version;return out
    def account(self):
        h=self.history.account();f=self.facts.account()
        return {'history':h,'facts':f,'combined_reserved_bytes':h['charged_bytes']+f['resident_reserved_bytes']}
