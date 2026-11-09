"""Single-writer bounded facts + independently initialized temporal segments.

Fixed catalog fact records are disk authoritative. H never receives fact changes.
Only a retained exact segment may support selective historical deletion; other
segments require retained raw replay or an explicitly lossy reset.
"""
from dataclasses import dataclass,asdict
import hashlib,io,json,os,struct,sys,time
from pathlib import Path
import numpy as np

LIMITS=np.array([-.5,-.25,0.,.25,.5])

def owned(obj,seen=None):
    seen=set() if seen is None else seen
    if id(obj) in seen:return 0
    seen.add(id(obj));n=sys.getsizeof(obj)
    if isinstance(obj,np.ndarray):
        if not obj.flags.owndata:raise ValueError('Persistent view')
        return n
    if isinstance(obj,dict):return n+sum(owned(k,seen)+owned(v,seen) for k,v in obj.items())
    if isinstance(obj,(list,tuple,set)):return n+sum(owned(v,seen) for v in obj)
    if hasattr(obj,'__dict__'):
        return n+sum(owned(k,seen)+owned(v,seen) for k,v in obj.__dict__.items() if k not in ('shared','fd'))
    return n

@dataclass(frozen=True)
class Config:
    channels:int=4
    segment_length:int=256
    budget:int=32768
    cache_capacity:int=16
    width:int=8
    backend:str='native'
    policy:str='fixed'
    max_segments:int=32
    keyspace:int=128
    with_f:bool=False
    workspace:int=2048
    disk_cap:int=1048576
    replay_capacity:int=0

class Segment:
    def __init__(self,epoch,start,cfg,width,shared):
        self.epoch=epoch;self.start=start;self.end=start;self.width=width
        self.backend=cfg.backend;self.sealed=False
        self.sums=np.zeros(((cfg.segment_length+width-1)//width,cfg.channels),np.float64) if cfg.backend=='native' else np.empty((0,cfg.channels))
        self.counts=np.zeros(len(self.sums),np.int32)
        self.h=shared.initial() if cfg.backend!='native' else np.empty(0,np.float32)
        self.f=np.zeros((100,5),np.float32) if cfg.with_f else np.empty((0,5),np.float32)

    def update(self,x,shared):
        if self.backend=='native':
            pos=0
            while pos<len(x):
                rel=self.end-self.start;i=rel//self.width;take=min(len(x)-pos,self.width-rel%self.width)
                self.sums[i]+=x[pos:pos+take].astype(np.float64).sum(0);self.counts[i]+=take
                self.end+=take;pos+=take
        else:self.h[:]=shared.update(self.h,x);self.end+=len(x)

    def read(self,lo,hi,j,shared):
        if self.backend!='native':
            return shared.read(self.h,self.end-self.start,lo-self.start,hi-self.start,j),'APPROX'
        total=0.;weight=0.
        for i in range((lo-self.start)//self.width,(hi-self.start-1)//self.width+1):
            a=self.start+i*self.width;b=min(a+self.width,self.end)
            overlap=max(0,min(hi,b)-max(lo,a));fraction=overlap/(b-a)
            total+=self.sums[i,j]*fraction;weight+=self.counts[i]*fraction
        return (None if weight==0 else total/weight),('EXACT' if self.width==1 or ((lo-self.start)%self.width==0 and (hi==self.end or (hi-self.start)%self.width==0)) else 'APPROX')

class Engine:
    def __init__(self,cfg,path,shared=None):
        self.cfg=cfg;self.shared=shared;self.path=str(path)
        Path(path).parent.mkdir(parents=True,exist_ok=True)
        self.fd=os.open(str(path),os.O_RDWR|os.O_CREAT|os.O_TRUNC,0o600)
        os.ftruncate(self.fd,cfg.keyspace*48)
        self.cache=np.full((cfg.cache_capacity,9),-1,np.int64)
        self.telemetry=np.full((128,4),-1,np.int64)
        self.replay=np.zeros((cfg.replay_capacity,cfg.channels),np.float32)
        self.replay_ids=np.full(cfg.replay_capacity,-1,np.int64)
        self.control=np.zeros(16,np.int64)
        # nobs, input-offset, access clock, queries, hit, miss, mutations,
        # evictions, layout switches, next epoch, telemetry pointer, replay ptr,
        # deleted observations, segment resets, controller actions, last switch Q.
        self.segments=[];self.next_width=cfg.width;self.events_since_account=0
        self.shared_id='native' if shared is None else shared.identity
        self._enforce()

    def close(self):
        if self.fd is not None:os.close(self.fd);self.fd=None

    def __del__(self):
        if getattr(self,'fd',None) is not None:self.close()

    def fact(self,key):
        if not 0<=int(key)<self.cfg.keyspace:raise ValueError('Bounded catalog')
        return np.frombuffer(os.pread(self.fd,48,int(key)*48),dtype='<i8').copy()

    def _sync_f(self):
        if not self.cfg.with_f:return
        for s in self.segments:s.f.fill(0)
        epochs={s.epoch:s for s in self.segments}
        for r in self.cache:
            if r[0]>=0 and r[2]==1 and int(r[8]) in epochs:
                epochs[int(r[8])].f[:,int(r[6])]+=self.shared.code(int(r[0]))

    def _cache_row(self,key,row):
        if not len(self.cache):return
        ix=np.flatnonzero(self.cache[:,0]==key);free=np.flatnonzero(self.cache[:,0]<0)
        i=int(ix[0]) if len(ix) else (int(free[0]) if len(free) else int(np.argmin(self.cache[:,7])))
        self.control[2]+=1
        self.cache[i]=[key,*row.tolist(),self.control[2],self.segments[-1].epoch if self.segments else -1]
        self._sync_f()

    def put(self,key,j,w,d,t,seq=None,delete=False):
        seq=int(self.control[1])+1 if seq is None else int(seq)
        if seq<=self.control[1]:return False
        if seq!=self.control[1]+1:raise ValueError('Offset gap')
        if not (0<=j<self.cfg.channels and w>0 and d>=0 and 0<=t<5):raise ValueError('Fact payload')
        old=self.fact(key);row=np.array([seq,0 if delete else 1,j,w,d,t],dtype='<i8')
        os.pwrite(self.fd,row.tobytes(),key*48)
        self.control[1]=seq;self.control[6]+=1
        ix=np.flatnonzero(self.cache[:,0]==key)
        if len(ix):self.cache[ix]=-1
        if not delete:self._cache_row(key,row)
        else:self._sync_f()
        return True

    def get(self,key):
        ix=np.flatnonzero(self.cache[:,0]==key)
        if len(ix):
            i=int(ix[0]);self.control[4]+=1;self.control[2]+=1;self.cache[i,7]=self.control[2]
            return self.cache[i,1:7].copy()
        self.control[5]+=1;row=self.fact(key)
        if row[1]:self._cache_row(key,row)
        return row

    def _new_segment(self):
        if self.cfg.policy=='fixed_mixed':
            for old in self.segments[:-1]:
                if old.backend=='native' and old.width<64 and old.sealed:
                    factor=64//old.width
                    old.sums=old.sums.reshape(-1,factor,self.cfg.channels).sum(1)
                    old.counts=old.counts.reshape(-1,factor).sum(1).astype(np.int32)
                    old.width=64
        self.control[9]+=1
        s=Segment(int(self.control[9]),int(self.control[0]),self.cfg,self.next_width,self.shared)
        self.segments.append(s)
        while len(self.segments)>self.cfg.max_segments:self.segments.pop(0);self.control[7]+=1
        self._enforce()

    def observe(self,x):
        x=np.asarray(x,np.float32)
        if x.ndim!=2 or x.shape[1]!=self.cfg.channels or not np.isfinite(x).all():raise ValueError('Input')
        pos=0
        while pos<len(x):
            if not self.segments or self.segments[-1].sealed:self._new_segment()
            s=self.segments[-1];take=min(len(x)-pos,self.cfg.segment_length-(s.end-s.start))
            s.update(x[pos:pos+take],self.shared)
            if len(self.replay):
                for k,row in enumerate(x[pos:pos+take]):
                    slot=int(self.control[11])%len(self.replay);self.replay[slot]=row;self.replay_ids[slot]=int(self.control[0])+k;self.control[11]+=1
            self.control[0]+=take;self.control[1]+=take;pos+=take
            if s.end-s.start==self.cfg.segment_length:s.sealed=True
        self.events_since_account+=len(x)

    def query(self,key,record=True):
        row=self.get(key);v,live,j,w,d,t=map(int,row)
        n=int(self.control[0]);lo=n-d-w;hi=n-d
        if record:
            k=int(self.control[10])%128;self.telemetry[k]=[key,w,d,int(self.control[6])]
            self.control[10]+=1;self.control[3]+=1
        base={'key':int(key),'version':v,'prefix':int(self.control[1]),'nobs':n,'lo':lo,'hi':hi,'channel':j,'threshold':float(LIMITS[t]),'source':self.cfg.backend}
        if not live:return {**base,'status':'UNKNOWN','reason':'deleted_or_absent_fact','coverage':0.}
        if lo<0:return {**base,'status':'UNKNOWN','reason':'prehistory','coverage':0.}
        cursor=lo;total=0.;count=0.;exact=True
        for s in self.segments:
            a=max(lo,s.start);b=min(hi,s.end)
            if b<=a:continue
            if a!=cursor:return {**base,'status':'UNKNOWN','reason':'history_gap','coverage':count/w}
            value,kind=s.read(a,b,j,self.shared)
            if value is None:return {**base,'status':'UNKNOWN','reason':'unsupported_readout_or_empty','coverage':count/w}
            # Count weighting is exact for non-deleted intervals. After selective
            # deletion, countable exact native rows determine actual live count.
            weight=b-a
            if s.backend=='native':
                weight=0.
                for bi in range((a-s.start)//s.width,(b-s.start-1)//s.width+1):
                    ba=s.start+bi*s.width;bb=min(ba+s.width,s.end)
                    weight+=s.counts[bi]*max(0,min(b,bb)-max(a,ba))/(bb-ba)
            total+=value*weight;count+=weight;cursor=b;exact &= kind=='EXACT'
        if cursor!=hi or count==0:return {**base,'status':'UNKNOWN','reason':'history_gap','coverage':min(1.,count/w)}
        value=float(total/count)
        if not np.isfinite(value):raise FloatingPointError('Prediction')
        return {**base,'status':'EXACT' if exact else 'APPROX','reason':'answer','coverage':1.,'mean':value,'alarm':bool(value>LIMITS[t])}

    def resize_cache(self,capacity):
        if capacity==len(self.cache):return
        new=np.full((capacity,9),-1,np.int64);rows=self.cache[self.cache[:,0]>=0]
        rows=rows[np.argsort(-rows[:,7])][:capacity];new[:len(rows)]=rows
        previous=self.cache;segments=self.segments.copy();old_evictions=int(self.control[7]);self.cache=new
        try:self._enforce()
        except MemoryError:
            self.cache=previous;self.segments=segments;self.control[7]=old_evictions;return False
        self.control[8]+=1;self._sync_f();return True

    def adapt(self):
        policy=self.cfg.policy;q=int(self.control[3]);last=int(self.control[15])
        if policy in ('fixed','fixed_mixed') or q%32 or q-last<64:return None
        a=self.telemetry[self.telemetry[:,0]>=0]
        if not len(a):return None
        ranges=a[:,1]+a[:,2];far=float(np.mean(ranges>512));unique=len(np.unique(a[:,0]))
        cache=4 if unique<=4 else (16 if unique<=16 else 64)
        width=64 if far>.5 else 8
        if policy=='cache_only':width=self.cfg.width
        if policy=='history_only':cache=self.cfg.cache_capacity
        if policy=='greedy':width=64 if ranges[-1]>512 else 8;cache=64 if unique>16 else 4
        if policy=='joint_cost':
            # Require sustained workload evidence. Two bands are a policy
            # setting, not an evaluation success gate.
            width=64 if far>=.65 else (8 if far<=.35 else self.next_width)
            if abs(cache-len(self.cache))<8:cache=len(self.cache)
        changed=cache!=len(self.cache) or width!=self.next_width
        if not changed:return None
        before=self.account();self.resize_cache(cache);self.next_width=width
        self.control[14]+=1;self.control[15]=q
        return {'queries':q,'cache':cache,'next_width':width,'far_fraction':far,'recent_unique_keys':unique,
                'before_resident':before['resident_bytes'],'after_resident':self.account()['resident_bytes'],'switch':'new_segments_only'}

    def delete_history(self,index,mode='replay'):
        for si,s in enumerate(self.segments):
            if not s.start<=index<s.end:continue
            if mode=='reset':
                lost=s.end-s.start;self.segments.pop(si);self.control[13]+=1
                return {'action':'reset','collateral_observations':lost-1,'removed':1}
            if s.backend=='native' and s.width==1:
                i=index-s.start;s.sums[i]=0;s.counts[i]=0;self.control[12]+=1
                return {'action':'exact_delete','collateral_observations':0,'removed':1}
            ids=self.replay_ids;wanted=np.arange(s.start,s.end)
            # Negative encoded IDs retain bounded deletion tombstones, distinct
            # from an overwritten/missing raw record (-1).
            lookup={int(k) if k>=0 else -int(k)-2:i for i,k in enumerate(ids) if k!=-1}
            if not all(int(k) in lookup for k in wanted):return {'action':'unsupported','collateral_observations':0,'removed':0}
            if ids[lookup[index]]<0:return {'action':'already_deleted','collateral_observations':0,'removed':0}
            if s.backend!='native':
                # Arbitrary deletion changes time geometry of neural readouts;
                # no false unlearning guarantee from simply omitting one row.
                return {'action':'unsupported_neural_time_geometry','collateral_observations':0,'removed':0}
            i=(index-s.start)//s.width;raw=[self.replay[lookup[int(k)]] for k in wanted if (int(k)-s.start)//s.width==i and int(k)!=index and ids[lookup[int(k)]]>=0]
            s.sums[i]=np.asarray(raw,dtype=np.float64).sum(0) if raw else 0;s.counts[i]=len(raw)
            self.replay_ids[lookup[index]]=-index-2;self.control[12]+=1
            return {'action':'replay_bucket_delete','collateral_observations':0,'removed':1}
        return {'action':'not_retained','collateral_observations':0,'removed':0}

    def _arrays(self):
        out={'cache':self.cache,'telemetry':self.telemetry,'replay':self.replay,'replay_ids':self.replay_ids,'control':self.control}
        for i,s in enumerate(self.segments):
            for k in ('sums','counts','h','f'):out[f's{i}_{k}']=getattr(s,k)
        return out

    def dumps(self):
        meta={'cfg':asdict(self.cfg),'shared':self.shared_id,'next_width':self.next_width,
              'segments':[{k:v for k,v in s.__dict__.items() if not isinstance(v,np.ndarray)} for s in self.segments]}
        arrays=self._arrays();desc={k:[v.dtype.str,list(v.shape),v.nbytes] for k,v in arrays.items()}
        meta['arrays']=desc;meta['array_order']=list(arrays);header=json.dumps(meta,sort_keys=True,separators=(',',':')).encode()
        fact=os.pread(self.fd,self.cfg.keyspace*48,0)
        body=b'MTJOINTX'+struct.pack('<I',len(header))+header+fact+b''.join(v.tobytes() for v in arrays.values())
        return body+hashlib.sha256(body).digest()

    @classmethod
    def loads(cls,blob,path,shared=None):
        body=blob[:-32]
        if body[:8]!=b'MTJOINTX' or hashlib.sha256(body).digest()!=blob[-32:]:raise ValueError('Snapshot integrity')
        size=struct.unpack('<I',body[8:12])[0];meta=json.loads(body[12:12+size]);cfg=Config(**meta['cfg'])
        e=cls(cfg,path,shared)
        if meta['shared']!=e.shared_id:raise ValueError('Model identity')
        e.next_width=meta['next_width'];e.segments=[];pos=12+size;nf=cfg.keyspace*48
        os.pwrite(e.fd,body[pos:pos+nf],0);pos+=nf
        loaded={}
        for k in meta['array_order']:
            dtype,shape,n=meta['arrays'][k]
            loaded[k]=np.frombuffer(body[pos:pos+n],dtype=np.dtype(dtype)).reshape(shape).copy();pos+=n
        if pos!=len(body):raise ValueError('Snapshot size')
        for k in ('cache','telemetry','replay','replay_ids','control'):setattr(e,k,loaded[k])
        for i,m in enumerate(meta['segments']):
            s=object.__new__(Segment);s.__dict__.update(m)
            for k in ('sums','counts','h','f'):setattr(s,k,loaded[f's{i}_{k}'])
            e.segments.append(s)
        e._enforce();return e

    def save(self,path,failpoint=None):
        p=Path(path);pending=p.with_suffix('.pending');blob=self.dumps()
        with pending.open('wb') as f:f.write(blob);f.flush();os.fsync(f.fileno())
        if failpoint=='before_replace':os._exit(91)
        os.replace(pending,p)
        if failpoint=='after_replace':os._exit(92)
        return len(blob)

    def account(self):
        resident=owned(self);snap_est=len(self.dumps())
        # Conservative, identity-independent object/header reservation. Python
        # string/dict aliasing changes after deserialization; it must not cause
        # a restore operation to silently reclaim segments.
        reserved=sum(a.nbytes for a in self._arrays().values())+8192+2048*len(self.segments)
        if resident>reserved:raise MemoryError('Object/header reservation insufficient')
        return {'resident_bytes':resident,'snapshot_bound_bytes':snap_est,
                'resident_reserved_bytes':reserved,
                'resident_snapshot_workspace_bound':reserved+2*snap_est+self.cfg.workspace,
                'budget':self.cfg.budget,'fact_disk_bytes':self.cfg.keyspace*48,
                'service_disk_replacement_bound':self.cfg.keyspace*48+2*snap_est,
                'segments':len(self.segments),'cache_capacity':len(self.cache),
                'arrays_bytes':sum(a.nbytes for a in self._arrays().values()),
                'shared_bytes':0 if self.shared is None else self.shared.account()['shared_total_bytes'],
                'scope':'owned Python/storage + conservative snapshot bound + reserved per-request workspace; shared/runtime/RSS independently reported'}

    def _enforce(self):
        while self.account()['resident_snapshot_workspace_bound']>self.cfg.budget and len(self.segments)>1:
            self.segments.pop(0);self.control[7]+=1
        a=self.account()
        if a['resident_snapshot_workspace_bound']>self.cfg.budget:raise MemoryError('Complete service slice incl snapshot/workspace')
        if a['service_disk_replacement_bound']>self.cfg.disk_cap:raise MemoryError('Service disk cap')

    def validate(self):
        self._enforce();a=self.account();blob=self.dumps()
        if len(blob)>a['snapshot_bound_bytes']:raise MemoryError('Snapshot estimate insufficient')
        if not np.isfinite(np.concatenate([s.h for s in self.segments])).all() if self.segments else False:raise FloatingPointError('H')
        return a
