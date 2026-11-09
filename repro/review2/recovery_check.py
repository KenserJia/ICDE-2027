from pathlib import Path
import sys,json,subprocess,tempfile,numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'src'))
from mtmemory_icde.core.replay import ReplayService
OUT=ROOT/'results/review2_20261104/replay';OUT.mkdir(exist_ok=True)
if len(sys.argv)>1:
 path=Path(sys.argv[1]);point=sys.argv[2];s=ReplayService(path)
 for i in range(700):s.mutate('observe',[i,i*.1,-i,1])
 s.checkpoint()
 for i in range(29):s.mutate('fact',[i,2,3,4],key=i)
 if point in ['after_journal','after_apply']:s.mutate('fact',[99,98,97,96],key=31,failpoint=point)
 else:s.checkpoint(failpoint=point)
 raise RuntimeError('failpoint did not kill')
rows=[]
for point in ['after_journal','after_apply','after_file_fsync','after_replace_before_dir_fsync','after_dir_fsync']:
 for seed in range(5):
  path=OUT/f'{point}-{seed}';p=subprocess.run([sys.executable,__file__,str(path),point]);assert p.returncode==-9
  s=ReplayService(path);expected=730 if point.startswith('after_') and point in ['after_journal','after_apply'] else 729
  assert s.service.ack_seq==expected
  for i in range(29):assert s.service.get_fact(i)['value'][0]==i
  before=s.service.dumps();s.checkpoint();again=ReplayService(path)
  assert again.service.ack_seq==expected and again.replayed==0
  assert np.allclose(s.service.query(1,32,64)['history']['value'],again.service.query(1,32,64)['history']['value'])
  rows.append(dict(failpoint=point,replica=seed,returncode=p.returncode,recovered_prefix=expected,replayed=s.replayed,repeat_replay_count=again.replayed))
(OUT/'results.json').write_text(json.dumps(rows,indent=2)+'\n');print('Passed',len(rows),'actual SIGKILL and idempotent replay trials')
