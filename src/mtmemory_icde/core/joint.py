"""One image for current facts, certified history, retention state and prefix.

The fixed payload ledger includes resident arrays/scalars, two durable slots and
one pending envelope, plus numerical workspace and an optional derived cache.
It is not a peak-RAM bound. Query/controller diagnostics are not persisted;
query-shape and demand-history buffers required by policy are persisted.
"""
from dataclasses import asdict
import json,struct,threading
import numpy as np
from .history import Config
from .service import IntegratedService,ControlledOverlayStore
from .joint_history import JointCertifiedHistory
from .histogram import VOptimalHistory
MAGIC=b'MTJOINT1';HEADER=struct.Struct('<8sI');METADATA=8192
class JointService(IntegratedService):
    def __init__(self,engine='certified',base_width=128,fine_width=16,overlay_capacity=4,max_reach=4096,bins=2,policy='recent',cache_capacity=0,fused=True,budget=131072):
        if engine not in ['native','certified','histogram']:raise ValueError('history engine')
        if not 1<=base_width<=2**20 or not 1<=max_reach<=2**20:raise ValueError('supported length domain')
        self.options=dict(engine=engine,base_width=int(base_width),fine_width=int(fine_width),overlay_capacity=int(overlay_capacity),max_reach=int(max_reach),bins=int(bins),policy=policy,cache_capacity=int(cache_capacity),fused=bool(fused),budget=int(budget))
        if engine=='histogram':self.history=VOptimalHistory(base_width,bins,max_reach,self.CHANNELS)
        else:
            cfg=Config(budget=2**30,channels=self.CHANNELS,base_width=base_width,fine_width=fine_width,max_reach=max_reach,overlay_capacity=overlay_capacity,policy=policy,query_history=128)
            if engine=='certified':self.history=JointCertifiedHistory(cfg,overlay_capacity,fused,cache_capacity)
            else:self.history=ControlledOverlayStore(cfg,overlay_capacity)
        self.fact_values=np.zeros((self.KEYSPACE,self.CHANNELS),np.float32);self.fact_versions=np.zeros(self.KEYSPACE,np.int64);self.fact_live=np.zeros(self.KEYSPACE,np.bool_)
        self.shape_ring=np.zeros((128,2),np.int64);self.shape_pos=0;self.version=self.ack_seq=self.request_seq=0;self._lock=threading.RLock()
        if not self.account()['within_budget']:raise MemoryError('joint payload reservations exceed budget')
    def _arrays(self):
        h=self.history.state_arrays()
        if self.options['engine']=='native':h={n:getattr(self.history,n) for n in h}
        return {**{'h/'+k:v for k,v in h.items()},'facts/values':self.fact_values,'facts/versions':self.fact_versions,'facts/live':self.fact_live,'control/shapes':self.shape_ring}
    def _history_meta(self):
        if self.options['engine']!='native':return self.history.export_meta()
        return {n:int(getattr(self.history,n)) for n in ['active_id','event_count','q_pos','replay_pos','active_capacity']}
    def account(self,snapshot_bytes=None):
        arrays=self._arrays();A=sum(x.nbytes for x in arrays.values())
        workspace=getattr(self.history,'workspace_bytes',8192);cache=getattr(self.history,'derived_payload_bytes',0);E=A+METADATA+88;V=A+METADATA+cache;charged=V+3*E+workspace
        out=dict(array_bytes=A,metadata_reserve_bytes=METADATA,cache_payload_bytes=cache,resident_reservation_bytes=V,envelope_reservation_bytes=E,workspace_bytes=workspace,charged_bytes=charged,budget_bytes=self.options['budget'],within_budget=charged<=self.options['budget'],physical_RAM_bound=False)
        if snapshot_bytes is not None:
            out.update(snapshot_bytes=int(snapshot_bytes),snapshot_metadata_bytes=int(snapshot_bytes)-A,snapshot_fits=int(snapshot_bytes)+88<=E,actual_envelope_bytes=int(snapshot_bytes)+88)
        return out
    def observe(self,row,count_ack=True):
        row=np.asarray(row,np.float32)
        if row.shape!=(self.CHANNELS,) or not np.all(np.isfinite(row)):raise ValueError('finite channel vector')
        with self._lock:
            self._check_counters();self.history.observe(row);self.history._trim_actions();self.history.actions.clear();self.request_seq+=1
            if count_ack:self.ack_seq+=1
            return self.ack_seq
    def _check_counters(self):
        if max(self.ack_seq,self.request_seq,self.version,self.event_count,self.shape_pos)>=2**63-1:raise OverflowError('64-bit counter domain exhausted')
    def put_fact(self,key,value,delete=False,count_ack=True):
        key=int(key);value=np.zeros(self.CHANNELS,np.float32) if delete else np.asarray(value,np.float32)
        if not 0<=key<self.KEYSPACE or value.shape!=(self.CHANNELS,) or not np.all(np.isfinite(value)):raise ValueError('bounded finite fact')
        with self._lock:self._check_counters();return super().put_fact(key,value,delete,count_ack)
    def get_fact(self,key):
        key=int(key)
        if not 0<=key<self.KEYSPACE:raise ValueError('bounded fact key')
        return super().get_fact(key)
    def query(self,key,delay,window,record=True,certificate=True):
        key=int(key);delay=int(delay);window=int(window)
        if not 0<=key<self.KEYSPACE:raise ValueError('bounded fact key')
        if self.options['engine']=='native' and certificate:raise ValueError('native cost reference has no certificate')
        with self._lock:
            self._check_counters();answer=self.history.query(delay,window,record)
            end=self.event_count-delay;start=end-window
            if record:self.shape_ring[self.shape_pos%128]=(int(start%self.options['base_width']!=0 or end%self.options['base_width']!=0),delay+window);self.shape_pos+=1
            self.request_seq+=1
            fact=dict(key=key,version=int(self.fact_versions[key]),live=bool(self.fact_live[key]),value=self.fact_values[key].copy() if self.fact_live[key] else None)
            return dict(history=answer,fact=fact,lo=start,hi=end,prefix=int(self.ack_seq),event_count=int(self.event_count),certificate_requested=bool(certificate))
    def set_active_capacity(self,capacity):
        if self.options['engine']=='histogram':raise NotImplementedError('histogram has fixed bin allocation')
        with self._lock:return self.history.set_active_capacity(int(capacity))
    def drop_overlay(self,bid):
        if self.options['engine']=='histogram':raise NotImplementedError('histogram has fixed bin allocation')
        with self._lock:return self.history.drop_overlay(int(bid))
    def controller_tick(self):
        if self.options['engine']=='histogram':return None
        with self._lock:
            n=min(self.shape_pos,128)
            if not n:return None
            q=self.shape_ring[:n];shifted=float(q[:,0].mean());far=float((q[:,1]>768).mean());maximum=self.options['overlay_capacity'];target=min(maximum,16 if shifted>=.55 or far>=.65 else 4 if shifted<=.15 and far<=.25 else 8)
            before=self.history.active_capacity;changed=self.history.set_active_capacity(target)
            return dict(before=before,after=target,changed=changed)
    def dumps(self):
        with self._lock:
            meta=dict(schema=1,options=self.options,history=self._history_meta(),version=int(self.version),ack_seq=int(self.ack_seq),request_seq=int(self.request_seq),shape_pos=int(self.shape_pos))
            meta['array_schema']=[(k,v.dtype.str,list(v.shape)) for k,v in self._arrays().items()]
            encoded=json.dumps(meta,separators=(',',':'),sort_keys=True,allow_nan=False).encode()
            if len(encoded)+HEADER.size>METADATA:raise MemoryError('bounded metadata reserve')
            blob=HEADER.pack(MAGIC,len(encoded))+encoded+b''.join(x.tobytes(order='C') for x in self._arrays().values())
            account=self.account(len(blob))
            if not account['snapshot_fits'] or not account['within_budget']:raise MemoryError('snapshot reservation exceeded')
            return blob
    @classmethod
    def loads(cls,blob):
        view=memoryview(blob)
        if len(view)<HEADER.size:raise ValueError('truncated joint image')
        magic,n=HEADER.unpack(view[:HEADER.size])
        if magic!=MAGIC or n+HEADER.size>METADATA or n+HEADER.size>len(view):raise ValueError('joint image header')
        meta=json.loads(bytes(view[HEADER.size:HEADER.size+n]));
        if meta.get('schema')!=1:raise ValueError('joint image schema')
        obj=cls(**meta['options']);pos=HEADER.size+n
        expected=[[k,v.dtype.str,list(v.shape)] for k,v in obj._arrays().items()]
        if meta.get('array_schema')!=expected:raise ValueError('joint array schema')
        for name,array in obj._arrays().items():
            end=pos+array.nbytes
            if end>len(view):raise ValueError('truncated joint arrays')
            array[:]=np.frombuffer(view[pos:end],dtype=array.dtype).reshape(array.shape);pos=end
        if pos!=len(view):raise ValueError('unexpected joint trailing bytes')
        if obj.options['engine']=='native':
            for k,v in meta['history'].items():setattr(obj.history,k,int(v))
        else:obj.history.restore_meta(meta['history'])
        for k in ['version','ack_seq','request_seq','shape_pos']:setattr(obj,k,int(meta[k]))
        obj._check_counters();return obj
