"""Local range-mean subset of Plato FL polynomial/L2 compression (PVLDB 2020).

This is not the upstream Plato engine. The bounded ring and online sealing are
adapters; polynomial fitting and residual-norm propagation follow the paper.
"""
from io import BytesIO
import math
import numpy as np

class PlatoRange:
    def __init__(self, budget, width, degree, reach=4096, channels=4):
        self.budget=budget;self.width=width;self.degree=degree;self.reach=reach;self.channels=channels
        n=math.ceil(reach/width)+3
        self.ids=np.full(n,-1,np.int64);self.counts=np.zeros(n,np.int32)
        self.coefficients=np.zeros((n,degree+1,channels),np.float64)
        self.norms=np.zeros((n,channels));self.gammas=np.zeros((n,channels));self.maxabs=np.zeros((n,channels))
        self.active=np.zeros((width,channels),np.float32);self.event_count=0;self.active_count=0
        if self.account()['charged_bytes']>budget:raise MemoryError('Plato subset exceeds ledger')
    def arrays(self):
        return {n:getattr(self,n) for n in ('ids','counts','coefficients','norms','gammas','maxabs','active')}
    def account(self):
        a=sum(x.nbytes for x in self.arrays().values());m=4096;w=max(4096,192*self.width+1024)
        return dict(resident_array_bytes=a,metadata_bytes=m,snapshot_slot_bytes=a+m,workspace_bytes=w,charged_bytes=3*(a+m)+w,budget_bytes=self.budget)
    def fit(self,rows):
        x=rows.astype(np.float64);m=len(x);t=np.arange(m,dtype=np.float64)-(m-1)/2
        coef=np.zeros((self.degree+1,self.channels));coef[0]=x.mean(0)
        if self.degree and m>1:coef[1]=t@x/(t@t)
        prediction=coef[0]+(t[:,None]*coef[1] if self.degree else 0)
        residual=x-prediction;norm=np.sqrt(np.sum(residual*residual,axis=0));ma=np.abs(x).max(0)
        # The gamma record bounds the nonzero residual sum caused by rounded
        # coefficients/summation. The centered slope sums to zero analytically.
        u=np.finfo(np.float64).eps/2;g=(4*m+32)*u/(1-(4*m+32)*u)
        delta=np.array([abs(math.fsum(x[:,j])-m*coef[0,j]) for j in range(self.channels)])
        delta=np.nextafter(delta+g*m*ma,np.inf)
        return coef,np.nextafter(norm+g*np.sqrt(m)*ma,np.inf),delta,ma
    def observe(self,row):
        row=np.asarray(row,np.float32)
        if row.shape!=(self.channels,) or not np.all(np.isfinite(row)):raise ValueError('finite float32 vector required')
        if self.active_count==self.width:
            bid=(self.event_count-1)//self.width;s=bid%len(self.ids)
            self.ids[s]=bid;self.counts[s]=self.width
            self.coefficients[s],self.norms[s],self.gammas[s],self.maxabs[s]=self.fit(self.active)
            self.active_count=0
        self.active[self.active_count]=row;self.active_count+=1;self.event_count+=1
    def query(self,delay,window,record=True):
        end=self.event_count-delay;start=end-window
        if delay<0 or window<=0 or start<0 or delay+window>self.reach:return dict(status='UNKNOWN',value=None,bound=None)
        total=np.zeros(self.channels);bound=np.zeros(self.channels);mag=np.zeros(self.channels);terms=0
        current=(self.event_count-1)//self.width
        for bid in range(start//self.width,(end-1)//self.width+1):
            if bid==current:
                m=self.active_count;coef,norm,delta,ma=self.fit(self.active[:m])
            else:
                s=bid%len(self.ids)
                if self.ids[s]!=bid:return dict(status='UNKNOWN',value=None,bound=None)
                m=int(self.counts[s]);coef=self.coefficients[s];norm=self.norms[s];delta=self.gammas[s];ma=self.maxabs[s]
            lo=max(start-bid*self.width,0);hi=min(end-bid*self.width,m);r=hi-lo
            if r<=0:continue
            total+=r*coef[0]
            if self.degree:total+=r*((lo+hi-1)/2-(m-1)/2)*coef[1]
            # For any residual e, e-(sum(e)/m)1 has norm <= ||e||.
            # Inner product with the centered query mask gives this bound.
            bound+=np.sqrt(r*(m-r)/m)*norm+(r/m)*delta
            mag+=r*(np.abs(coef[0])+(m*np.abs(coef[1]) if self.degree else 0)+ma);terms+=1
        u=np.finfo(np.float64).eps/2;n=4*self.width+4*terms+64;g=n*u/(1-n*u)
        rounding=np.nextafter(4*g*(mag/window+bound/window)/(1-4*g),np.inf)
        analytical=bound/window
        return dict(status='ANSWERED',value=total/window,bound=analytical,rounding_bound=rounding,total_bound=np.nextafter(analytical+rounding,np.inf))
    def dumps(self):
        f=BytesIO();np.savez(f,**self.arrays(),meta=np.array([self.budget,self.width,self.degree,self.reach,self.channels,self.event_count,self.active_count],np.int64));return f.getvalue()
    @classmethod
    def loads(cls,blob):
        with np.load(BytesIO(blob),allow_pickle=False) as z:
            b,h,d,r,c,t,n=z['meta'].tolist();out=cls(b,h,d,r,c)
            for name in out.arrays():getattr(out,name)[:]=z[name]
            out.event_count=t;out.active_count=n;return out
