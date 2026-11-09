"""Blockwise V-optimal contiguous time histograms, with extrema certificates.

A bounded streaming adaptation of the classical optimal-histogram DP; it is not
DigitHist or a reproduction of all algorithms in the original histogram paper.
Fixed full blocks seal into q variable-width bins. Workspace is preallocated,
charged separately, and never serialized. No history/raw source is retained
outside the accounted active block and bounded sealed synopsis.
"""
import threading
import numpy as np
from .numerics import MissingHistory,certified_mean

def partitions(rows,max_bins):
    solver=HistogramWorkspace(len(rows),max_bins,rows.shape[1]);return solver.solve(rows)

class HistogramWorkspace:
    def __init__(self,b,q,c):
        self.b=b;self.q=q;self.c=c
        self.prefix=np.zeros((b+1,c));self.sq=np.zeros(b+1)
        self.diff=np.zeros((b,c));self.cost=np.zeros(b);self.candidates=np.zeros(b)
        self.indices=np.arange(b+1,dtype=float);self.lengths=np.zeros(b)
        self.dp=np.zeros((q+1,b+1));self.back=np.zeros((q+1,b+1),np.int32)
    @property
    def nbytes(self):return sum(x.nbytes for x in vars(self).values() if isinstance(x,np.ndarray))
    def solve(self,rows):
        b=len(rows);assert b==self.b
        self.prefix[0]=0;self.sq[0]=0
        for j,row in enumerate(rows,1):
            x=np.asarray(row,np.float64);self.prefix[j]=self.prefix[j-1]+x;self.sq[j]=self.sq[j-1]+float(x@x)
        self.dp.fill(np.inf);self.dp[0,0]=0;self.back.fill(-1)
        for j in range(1,b+1):
            np.subtract(self.prefix[j],self.prefix[:j],out=self.diff[:j]);np.square(self.diff[:j],out=self.diff[:j]);np.sum(self.diff[:j],axis=1,out=self.cost[:j])
            np.subtract(j,self.indices[:j],out=self.lengths[:j]);self.cost[:j]/=self.lengths[:j];self.cost[:j]*=-1;self.cost[:j]+=self.sq[j];self.cost[:j]-=self.sq[:j];np.maximum(self.cost[:j],0,out=self.cost[:j])
            for q in range(1,min(self.q,j)+1):
                np.add(self.dp[q-1,:j],self.cost[:j],out=self.candidates[:j]);k=int(np.argmin(self.candidates[:j]));self.dp[q,j]=self.candidates[k];self.back[q,j]=k
        result={}
        for q in range(1,self.q+1):
            ends=[b];j=b
            for qq in range(q,0,-1):j=int(self.back[qq,j]);ends.append(j)
            assert j==0;result[q]=list(reversed(ends))
        return result

class VOptimalHistory:
    def __init__(self,base_width=128,bins=2,max_reach=4096,channels=4):
        self.b=int(base_width);self.q=int(bins);self.R=int(max_reach);self.channels=int(channels)
        if not 1<=self.q<=self.b<=2**20 or not 1<=self.R<=2**20:raise ValueError('supported histogram sizes')
        self.slots=(self.R+self.b-1)//self.b+3
        self.ids=np.full(self.slots,-1,np.int64);self.ends=np.zeros((self.slots,self.q),np.int32)
        shape=(self.slots,self.q,self.channels)
        self.sums=np.zeros(shape);self.mins=np.full(shape,np.inf);self.maxs=np.full(shape,-np.inf)
        self.block_sums=np.zeros((self.slots,self.channels)) if self.q>1 else None
        self.active=np.zeros((self.b,self.channels),np.float32);self.active_count=0;self.active_id=-1;self.event_count=0
        self.solver=HistogramWorkspace(self.b,self.q,self.channels) if self.q>1 else None
        self._lock=threading.RLock();self.actions=[]
    def _trim_actions(self):self.actions.clear()
    def observe(self,row):
        row=np.asarray(row,np.float32)
        if row.shape!=(self.channels,) or not np.all(np.isfinite(row)):raise ValueError('finite channel vector')
        with self._lock:
            bid=self.event_count//self.b
            if bid!=self.active_id:
                if self.active_id>=0:self._seal()
                self.active.fill(0);self.active_count=0;self.active_id=bid
            self.active[self.active_count]=row;self.active_count+=1;self.event_count+=1
    def observe_many(self,rows):
        for row in rows:self.observe(row)
    def _seal(self):
        assert self.active_count==self.b
        cuts=[0,self.b] if self.q==1 else self.solver.solve(self.active)[self.q];slot=self.active_id%self.slots;self.ids[slot]=self.active_id
        for j,(lo,hi) in enumerate(zip(cuts,cuts[1:])):
            x=self.active[lo:hi];self.ends[slot,j]=hi;np.sum(x,axis=0,dtype=np.float64,out=self.sums[slot,j]);np.min(x,axis=0,out=self.mins[slot,j]);np.max(x,axis=0,out=self.maxs[slot,j])
        if self.block_sums is not None:np.sum(self.active,axis=0,dtype=np.float64,out=self.block_sums[slot])
    def _cells(self,lo,hi):
        for bid in range(lo//self.b,(hi-1)//self.b+1):
            base=bid*self.b
            if bid==self.active_id:
                for j in range(max(0,lo-base),min(self.active_count,hi-base)):
                    value=self.active[j].astype(float);yield base+j,1,value,value,value
            else:
                slot=bid%self.slots
                if self.ids[slot]!=bid:raise MissingHistory('histogram block identity')
                if lo<=base and hi>=base+self.b:
                    sums=self.sums[slot,0] if self.q==1 else self.block_sums[slot]
                    yield base,self.b,sums,self.mins[slot].min(axis=0),self.maxs[slot].max(axis=0);continue
                left=0
                for j,end in enumerate(self.ends[slot]):
                    yield base+left,int(end)-left,self.sums[slot,j],self.mins[slot,j],self.maxs[slot,j];left=int(end)
    def query(self,delay,window,record=True):
        delay=int(delay);window=int(window)
        with self._lock:
            hi=self.event_count-delay;lo=hi-window
            if delay<0 or window<=0 or delay+window>self.R or lo<0:return dict(status='UNKNOWN',value=None,resolution='UNKNOWN',bound=None)
            try:return certified_mean(self._cells(lo,hi),lo,hi,self.channels,self.b)
            except MissingHistory:return dict(status='UNKNOWN',value=None,resolution='UNKNOWN',bound=None)
    def state_arrays(self):
        out={n:getattr(self,n) for n in ['ids','ends','sums','mins','maxs','active']}
        if self.block_sums is not None:out['block_sums']=self.block_sums
        return out
    def export_meta(self):return dict(active_count=self.active_count,active_id=self.active_id,event_count=self.event_count)
    def restore_meta(self,meta):
        for k,v in meta.items():setattr(self,k,int(v))
    @property
    def workspace_bytes(self):return max(8192,0 if self.solver is None else self.solver.nbytes+4096)
    @property
    def derived_payload_bytes(self):return 0
