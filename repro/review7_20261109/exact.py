"""Independent exact oracle for finite float32 values, outside the service ledger."""
import numpy as np
DEN=1<<149
class ExactPrefix:
 def __init__(self,rows):
  rows=np.asarray(rows,np.float32);bits=rows.view(np.uint32);self.values=[[0]*rows.shape[1]]
  for bitrow in bits:
   prev=self.values[-1];new=[]
   for j,word in enumerate(bitrow):
    word=int(word);sign=-1 if word>>31 else 1;ex=(word>>23)&255;mant=word&((1<<23)-1)
    if ex==255:raise ValueError('finitefloat32 oracle')
    val=mant if ex==0 else ((1<<23)|mant)<<(ex-1);new.append(prev[j]+sign*val)
   self.values.append(new)
 def mean(self,lo,hi):return np.array([(b-a)/((hi-lo)*DEN) for a,b in zip(self.values[lo],self.values[hi])])
 def contains(self,lo,hi,pred,bound):
  td=(hi-lo)*DEN
  for a,b,p,t in zip(self.values[lo],self.values[hi],pred,bound):
   pn,pd=float(p).as_integer_ratio();tn,dd=float(t).as_integer_ratio()
   if abs(pn*td-(b-a)*pd)*dd>tn*pd*td:return False
  return True
