"""Contract-matched baselines; original estimators and checkpoints are reused."""
import numpy as np
from .histogram import HistogramWorkspace
from .joint import JointService

class BoundWorkspace(HistogramWorkspace):
    """DP minimizes a training-width-weighted mean-channel analytical bound.

    This optimizes an additive bound surrogate, not G(epsilon) or a global optimum.
    Uniform query-start phase is an explicit fixed prior. No future data are used.
    """
    def __init__(self,b,q,c,widths):
        super().__init__(b,q,c)
        self.coefficient=np.zeros(b+1)
        for m in range(1,b+1):
            total=0.
            for w in widths:
                lo=np.arange(-w+1,m);r=np.maximum(0,np.minimum(lo+w,m)-np.maximum(lo,0))
                total+=np.sum(r*(m-r)/(m*w))
            self.coefficient[m]=total/len(widths)
    def solve(self,rows):
        self.dp.fill(np.inf);self.dp[0,0]=0;self.back.fill(-1);b=self.b
        for j in range(1,b+1):
            lower=self.diff[:j];upper=self.prefix[1:j+1]
            np.minimum.accumulate(rows[:j][::-1],axis=0,out=lower);np.maximum.accumulate(rows[:j][::-1],axis=0,out=upper)
            np.subtract(upper[::-1],lower[::-1],out=self.diff[:j]);np.mean(self.diff[:j],axis=1,out=self.cost[:j]);self.cost[:j]*=self.coefficient[j-np.arange(j)]
            for q in range(1,min(self.q,j)+1):
                np.add(self.dp[q-1,:j],self.cost[:j],out=self.candidates[:j]);k=int(np.argmin(self.candidates[:j]));self.dp[q,j]=self.candidates[k];self.back[q,j]=k
        result={}
        for q in range(1,self.q+1):
            ends=[b];j=b
            for qq in range(q,0,-1):j=int(self.back[qq,j]);ends.append(j)
            assert j==0;result[q]=list(reversed(ends))
        return result

class FixedWorkspace:
    def __init__(self,b,q):self.ends=np.linspace(0,b,q+1,dtype=np.int32);self.q=q
    @property
    def nbytes(self):return self.ends.nbytes
    def solve(self,rows):return {self.q:self.ends.tolist()}

class ComparisonService(JointService):
    def __init__(self,*args,hist_variant='sse',prior_widths=(16,17,31,32,63,64,127,128),**kwargs):
        super().__init__(*args,**kwargs)
        self.options.update(hist_variant=hist_variant,prior_widths=list(prior_widths))
        if self.options['engine']=='histogram' and self.history.q>1:
            h=self.history
            if hist_variant=='bound':h.solver=BoundWorkspace(h.b,h.q,h.channels,prior_widths)
            elif hist_variant=='fixed':h.solver=FixedWorkspace(h.b,h.q)
            elif hist_variant!='sse':raise ValueError('histogram variant')
        if not self.account()['within_budget']:raise MemoryError('full baseline workspace exceeds budget')
