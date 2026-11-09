from pathlib import Path
import sys,json,random,subprocess
from performance_wide import OUT,ROOT,write,sha

def main():
 jobs=[dict(method=m,mix=70,clients=8,mode=mode,rep=rep,locality='random') for m in ['native','reference','fused'] for mode in ['sync','strict'] for rep in range(3)]
 random.Random(71113).shuffle(jobs)
 freeze=dict(jobs=jobs,N=100000,K=500,B=131072,reason='Mechanistic follow-up: Q70/C8; windows255/511/1023; delay0..255; all three methods use the same workload, geometry, budget and checkpoints. Complements the separate short-window control without deleting its flat outcomes. Wider recent queries can contain complete overlay segments and activate fusion.',hashes={str(p.relative_to(ROOT)):sha(p) for p in [Path(__file__),Path(__file__).parent/'performance_wide.py',*list((ROOT/'src/mtmemory_icde/core').glob('*.py'))]})
 dest=OUT/'COST_WIDE_FREEZE.json'
 if dest.exists():assert json.loads(dest.read_text())==freeze
 else:write(dest,freeze)
 rows=[]
 for i,j in enumerate(jobs):
  case=OUT/'cost_wide'/f'{j["method"]}-{j["mode"]}-{j["rep"]}';case.mkdir(parents=True,exist_ok=True)
  if not (case/'result.json').exists():
   c=subprocess.run([sys.executable,str(Path(__file__).parent/'performance_wide.py'),json.dumps(j),str(case)],capture_output=True,text=True,timeout=240);(case/'stderr.txt').write_text(c.stderr);assert c.returncode==0,c.stderr
  r=json.loads((case/'result.json').read_text());rows.append(r);write(OUT/'cost_wide_records.json',rows);print(i+1,len(jobs),j['method'],j['mode'],round(r['throughput_rps']),flush=True)
if __name__=='__main__':main()
