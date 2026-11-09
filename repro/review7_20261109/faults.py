from pathlib import Path
import sys,json,subprocess,random,hashlib,time
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'src'))
from mtmemory_icde.core.joint import JointService
from mtmemory_icde.core.checkpoint import TwoSlotStore
from mtmemory_icde.core.rpo import CheckpointCoordinator
from fault_child import WARM,value,VARIANTS
from exact import ExactPrefix
from quality import OUT,write,sha
FAILPOINTS=['after_partial_write','before_file_fsync','after_file_fsync','after_replace_before_dir_fsync','after_dir_fsync']
def verify_state(service,last_ack):
 a=service.ack_seq;assert 0<=a<=last_ack+1
 fact_values=np.zeros((256,4),np.float32);versions=np.zeros(256,np.int64);live=np.zeros(256,bool)
 for key in range(128):fact_values[key]=np.array([key,key*.5,-key,key*.25],np.float32)/128;versions[key]=key+1;live[key]=True
 for i in range(5,a+1,5):
  key=i%256;versions[key]=128+i//5;live[key]=i%35!=0;fact_values[key]=value(WARM+i) if live[key] else 0
 assert service.version==128+a//5 and np.array_equal(service.fact_values,fact_values) and np.array_equal(service.fact_versions,versions) and np.array_equal(service.fact_live,live)
 rows=np.asarray([value(i) for i in range(WARM)]+[value(WARM+i) for i in range(1,a+1) if i%5],np.float32);assert service.event_count==len(rows)
 oracle=ExactPrefix(rows);checks=0
 for d,w in [(0,1),(0,17),(1,127),(7,63),(135,127),(1031,63),(3500,63)]:
  z=service.query(7,d,w);h=z['history'];assert z['prefix']==a and h['status']=='ANSWERED' and oracle.contains(len(rows)-d-w,len(rows)-d,h['value'],h['total_bound']);checks+=1
 assert service.query(0,4096,1)['history']['status']=='UNKNOWN'
 if hasattr(service.history,'cache'):assert len(service.history.cache)<=32
 return checks

def main():
 (OUT/'faults').mkdir(exist_ok=True)
 jobs=[]
 for variant in VARIANTS:
  for K in [100,500,2000]:
   for rep in range(3):
    for mode in FAILPOINTS+['boundary','random']:jobs.append(dict(variant=variant,K=K,rep=rep,mode=mode))
  for rep in range(3):
   for mode in ['newest_corrupt','both_corrupt','semantic_invalid']:jobs.append(dict(variant=variant,K=100,rep=rep,mode=mode))
 random.Random(71109).shuffle(jobs)
 packet=dict(order=jobs,source_sha256=sha(Path(__file__)),child_sha256=sha(Path(__file__).parent/'fault_child.py'),scope='process kills and deliberate corruption only; latest completed valid image required for K bound')
 f=OUT/'FAULT_FREEZE.json'
 if not f.exists():write(f,packet)
 else:assert json.loads(f.read_text())==packet
 records=[]
 for ji,job in enumerate(jobs):
  name=f'{job["variant"]}-K{job["K"]}-r{job["rep"]}-{job["mode"]}';case=OUT/'faults'/name;case.mkdir(exist_ok=True);dest=case/'result.json'
  if dest.exists():records.append(json.loads(dest.read_text()));continue
  childmode='clean_prefix' if job['mode'] in ['newest_corrupt','both_corrupt','semantic_invalid'] else job['mode'];a=time.perf_counter()
  child=subprocess.run([sys.executable,str(Path(__file__).parent/'fault_child.py'),'--case',str(case),'--variant',job['variant'],'--K',str(job['K']),'--mode',childmode,'--rep',str(job['rep'])],capture_output=True,text=True,timeout=60)
  (case/'child_stdout.jsonl').write_text(child.stdout);(case/'child_stderr.txt').write_text(child.stderr)
  assert child.returncode in [0,-9],(name,child.returncode,child.stderr)
  msgs=[json.loads(s) for s in child.stdout.splitlines() if s.startswith('{')];last=max(x.get('ack',0) for x in msgs);store=TwoSlotStore(case/'checkpoint');mode=job['mode']
  if mode=='newest_corrupt':
   gen,payload,info=store.recover();path=store.paths[info['slot']];blob=bytearray(path.read_bytes());blob[len(blob)//2]^=1;path.write_bytes(blob)
  elif mode=='both_corrupt':
   for path in store.paths:
    blob=bytearray(path.read_bytes());blob[len(blob)//2]^=1;path.write_bytes(blob)
  elif mode=='semantic_invalid':store.commit(b'INVALID_JOINT_PAYLOAD')
  expected_failure=mode in ['both_corrupt','semantic_invalid'];failure=None
  try:gen,payload,info=store.recover();service=JointService.loads(payload)
  except (FileNotFoundError,ValueError) as exc:
   failure=type(exc).__name__;assert expected_failure,(name,failure)
  else:assert not expected_failure
  if failure:r=dict(**job,caller_ack=last,explicit_failure=failure,returncode=child.returncode,seconds=time.perf_counter()-a)
  else:
   checks=verify_state(service,last);a0=service.ack_seq;loss=max(0,last-a0)
   if mode not in ['newest_corrupt']:assert loss<=job['K'],(name,loss)
   if mode=='boundary':assert last==job['K'] and a0==0 and loss==job['K']
   if mode in FAILPOINTS[:3]:assert a0==0
   if mode in FAILPOINTS[3:]:assert a0==job['K']
   if mode=='newest_corrupt':assert loss>job['K'] and a0==0
   co=CheckpointCoordinator(service,store,job['K'],verify_capture=False)
   for i in range(17):co.mutate(lambda i=i:service.observe(value(100000+i)))
   co.close();_,blob,_=store.recover();again=JointService.loads(blob);assert again.ack_seq==a0+17 and all(np.array_equal(a,b) for a,b in zip(service._arrays().values(),again._arrays().values()))
   account=service.account(len(blob));assert account['within_budget'] and account['snapshot_fits']
   r=dict(**job,caller_ack=last,recovered_ack=a0,recovered_unacknowledged=max(0,a0-last),loss=loss,bound_claimed=mode!='newest_corrupt',certificate_checks=checks,continued_checkpoint=True,ledger=account,returncode=child.returncode,seconds=time.perf_counter()-a)
  write(dest,r);records.append(r);write(OUT/'fault_records.json',records)
  print(ji+1,len(jobs),name,'loss',r.get('loss'),r.get('explicit_failure','ok'),flush=True)
 write(OUT/'fault_records.json',records)
if __name__=='__main__':main()
