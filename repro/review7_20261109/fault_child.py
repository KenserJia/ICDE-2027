from pathlib import Path
import os,sys,json,signal,argparse,threading,time
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'src'))
from mtmemory_icde.core.joint import JointService
from mtmemory_icde.core.checkpoint import TwoSlotStore
import mtmemory_icde.core.checkpoint as checkpoint_module
def pinned_kill():
 os.kill(os.getpid(),signal.SIGKILL)
 while True:time.sleep(.1)
checkpoint_module._kill=pinned_kill
from mtmemory_icde.core.rpo import CheckpointCoordinator
WARM=4355
VARIANTS={'fused':dict(engine='certified',cache_capacity=0),'cache32':dict(engine='certified',cache_capacity=32),'histogram':dict(engine='histogram')}
def value(i):return np.asarray([np.sin(i/17),np.cos(i/29),(i%97)/97,np.sin(i/71)+np.cos(i/11)],np.float32)
def main():
 p=argparse.ArgumentParser();p.add_argument('--case',required=True);p.add_argument('--variant',required=True);p.add_argument('--K',type=int,required=True);p.add_argument('--mode',required=True);p.add_argument('--rep',type=int,required=True);a=p.parse_args()
 s=JointService(**VARIANTS[a.variant]);s.initialize_facts(128)
 for i in range(WARM):s.observe(value(i),count_ack=False)
 store=TwoSlotStore(Path(a.case)/'checkpoint');co=CheckpointCoordinator(s,store,a.K,verify_capture=False);commit=store.commit;entered=threading.Event()
 def hooked(payload,*args,**kwargs):
  entered.set()
  if a.mode=='boundary':
   while True:time.sleep(.05)
  if a.mode not in ['random','clean_prefix']:return commit(payload,*args,failpoint=a.mode,**kwargs)
  return commit(payload,*args,**kwargs)
 store.commit=hooked
 stop=threading.Event()
 def reads(worker):
  j=worker
  while not stop.is_set():
   s.query(j%256,[0,7,135,1031][j%4],[17,63,127,63][j%4]);j+=1
   if j%16==0:time.sleep(.0001)
 def controls():
  j=0
  while not stop.is_set():
   if a.variant!='histogram':
    s.set_active_capacity([0,4,2,4][j%4]);s.controller_tick()
   j+=1;time.sleep(.0007)
 for w in range(4):threading.Thread(target=reads,args=(w,),daemon=True).start()
 threading.Thread(target=controls,daemon=True).start()
 target=(a.K if a.mode=='boundary' else a.K+7+a.rep*3 if a.mode=='random' else 2*a.K-1 if a.mode=='clean_prefix' else 3*a.K+7)
 for i in range(1,target+1):
  if i%5==0:co.mutate(lambda i=i:s.put_fact(i%256,value(WARM+i),delete=i%35==0))
  else:co.mutate(lambda i=i:s.observe(value(WARM+i)))
  print(json.dumps(dict(ack=i)),flush=True)
  if a.mode=='boundary' and i==a.K:
   assert entered.wait(10);print(json.dumps(dict(boundary=True,gap=s.ack_seq-co.durable_seq)),flush=True);os.kill(os.getpid(),signal.SIGKILL)
 if a.mode=='random':os.kill(os.getpid(),signal.SIGKILL)
 if a.mode=='clean_prefix':
  print(json.dumps(dict(durable=co.durable_seq,ack=s.ack_seq)),flush=True);os._exit(0)
 raise AssertionError('commit failpoint did not fire')
if __name__=='__main__':main()
