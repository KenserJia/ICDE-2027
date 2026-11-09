"""Local durable replay log; external effects and distributed replay excluded."""
from pathlib import Path
import json,os,threading
from .checkpoint import TwoSlotStore
from .service import IntegratedService

class ReplayService:
 def __init__(self,directory):
  self.directory=Path(directory);self.directory.mkdir(exist_ok=True,parents=True);self.store=TwoSlotStore(self.directory/'snapshots');self.log=self.directory/'mutations.jsonl';self.lock=threading.RLock()
  try:_,blob,_=self.store.recover();self.service=IntegratedService.loads(blob)
  except FileNotFoundError:self.service=IntegratedService();self.store.commit(self.service.dumps())
  self.replayed=0;self.prefix=self.service.ack_seq
  if self.log.exists():
   lines=self.log.read_bytes().splitlines(keepends=True)
   for line in lines:
    if not line.endswith(b'\n'):raise ValueError('incomplete journal suffix requires explicit repair')
    r=json.loads(line)
    if r['seq']<=self.service.ack_seq:continue
    if r['seq']!=self.service.ack_seq+1:raise ValueError('replay gap')
    self._apply(r);self.replayed+=1
 def _apply(self,r):
  if r['kind']=='observe':self.service.observe(r['value'])
  elif r['kind']=='fact':self.service.put_fact(r['key'],r['value'],delete=r['delete'])
  else:raise ValueError('unknown command')
  if self.service.ack_seq!=r['seq']:raise ValueError('prefix mismatch')
 def mutate(self,kind,value,key=0,delete=False,failpoint=None):
  with self.lock:
   r={'seq':self.service.ack_seq+1,'kind':kind,'value':list(map(float,value)),'key':int(key),'delete':bool(delete)}
   with self.log.open('ab',buffering=0) as f:
    f.write((json.dumps(r,separators=(',',':'))+'\n').encode());os.fsync(f.fileno())
   if failpoint=='after_journal':os.kill(os.getpid(),9)
   self._apply(r)
   if failpoint=='after_apply':os.kill(os.getpid(),9)
   return self.service.ack_seq
 def checkpoint(self,failpoint=None):
  with self.lock:return self.store.commit(self.service.dumps(),failpoint=failpoint)
