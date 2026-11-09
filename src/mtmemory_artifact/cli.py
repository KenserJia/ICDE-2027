"""Isolated runners; recorded evidence is never used as a resume directory."""
from pathlib import Path
import argparse,json,os,shutil,subprocess,sys,tarfile,tempfile,urllib.request
from .io import ROOT,sha256,index,materialize,safe_path

def catalog(root=ROOT):return json.loads((root/'experiments/catalog.json').read_text())['experiments']
def write(p,x):Path(p).write_text(json.dumps(x,indent=2)+'\n')
def verify(full=False,root=ROOT):
 manifest=json.loads((root/'MANIFEST.json').read_text());bad=[]
 for name,info in manifest['files'].items():
  p=safe_path(root,name)
  if not p.exists() or sha256(p)!=info['sha256']:bad.append(name)
 raw=json.loads((root/'evidence/RAW_MANIFEST.json').read_text());installed=0
 for x in raw['files']:
  p=root/x['path']
  if p.exists():
   installed+=1
   if sha256(p)!=x['sha256']:bad.append(x['path'])
  elif full:bad.append(x['path'])
 result=dict(passed=not bad,repository_files=len(manifest['files']),raw_files_installed=installed,raw_files_available=len(raw['files']),mismatches=bad)
 if bad:raise RuntimeError(json.dumps(result))
 return result

def workspace(output,inputs=(),evidence_all=False):
 out=Path(output).expanduser().resolve()
 if out.exists():raise FileExistsError(f'refusing to overwrite existing output: {out}')
 # Explicitly protect packaged code, datasets, and evidence from being run targets.
 for p in [ROOT/'src',ROOT/'data',ROOT/'evidence',ROOT/'repro',ROOT/'figures',ROOT/'provenance']:
  if p.resolve()==out or p.resolve() in out.parents:raise ValueError('output must not be inside packaged inputs')
 out.mkdir(parents=True);work=out/'workspace';work.mkdir()
 for name in ['src','repro']:
  shutil.copytree(ROOT/name,work/name,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
 shutil.copytree(ROOT/'data/real',work/'data/real')
 for name in ['review7_20261109','review6_20261109','review4_20261109','review3_20261104','review2_20261104','review_revision_20261104','rq3_symmetric_20261107','rq2_precision_20261107','rq2_tradeoff_20261107','review4_paper_20261109','review7_paper_20261109','framework_20261109']:(work/'results'/name).mkdir(parents=True,exist_ok=True)
 (work/'paper/IEEE-conference-template-062824/figures').mkdir(parents=True)
 if evidence_all:materialize(work)
 elif inputs:materialize(work,inputs)
 return out,work

def execute(commands,out,work):
 env=os.environ.copy();env['MTMEM_ICDE_ROOT']=str(work);env['PYTHONPATH']=str(work/'src');env['MPLCONFIGDIR']=str(out/'mpl-cache');records=[]
 for n,cmd in enumerate(commands,1):
  argv=[t.replace('{python}',sys.executable) for t in cmd['argv']];cwd=work/cmd['cwd'];cwd.mkdir(parents=True,exist_ok=True);log=out/f'command-{n:02d}.log'
  print(f'{n}/{len(commands)}: {cmd["cwd"]}/{argv[1]} (log: {log.name})',flush=True)
  with log.open('w') as f:p=subprocess.run(argv,cwd=cwd,env=env,stdout=f,stderr=subprocess.STDOUT)
  records.append(dict(argv=argv,cwd=cmd['cwd'],returncode=p.returncode,log=log.name));write(out/'RUN.json',dict(status='failed' if p.returncode else 'running',commands=records))
  if p.returncode:raise RuntimeError(f'command failed; inspect {log}')
 return records

def run(id,output):
 spec=next((x for x in catalog() if x['id']==id),None)
 if not spec:raise ValueError(id)
 out,work=workspace(output,spec['reference_inputs']);write(out/'PROTOCOL.json',spec);commands=execute(spec['commands'],out,work)
 result=dict(status='complete',experiment=id,scientific_rerun=True,workspace='workspace',commands=commands,comparison='Compare deterministic quality/counts to recorded evidence; remeasure performance, do not expect timing equality.');write(out/'RUN.json',result);return result

def figures(output):
 needed=['results/review4_20261109/rq2_records.json','results/rq3_symmetric_20261107/summary.json','results/rq3_symmetric_20261107/selected_results.json','results/rq3_symmetric_20261107/layouts.json','results/rq3_symmetric_20261107/same_layout_summary.json','results/frozen/rq_closure/rq3_boundary/calibration_summary.json','results/review7_20261109/performance_records.json','results/review7_20261109/cost_control_records.json','results/review7_20261109/cost_wide_records.json']
 out,work=workspace(output,needed);commands=execute([dict(cwd='repro/review4_paper_20261109',argv=['{python}','figures.py']),dict(cwd='repro/rq3_symmetric_20261107',argv=['{python}','figures.py']),dict(cwd='repro/review7_paper_20261109',argv=['{python}','figures.py'])],out,work)
 src=work/'paper/IEEE-conference-template-062824/figures';target=out/'figures';target.mkdir()
 paths=['review4_rq2.pdf','rq3_symmetric_scope.pdf','review7_joint_operating.pdf','review7_framework/mtmemory_framework_en.pdf']
 for n in paths:
  for ext in ['.pdf','.svg','.png']:
   p=(src/n).with_suffix(ext)
   if p.exists():shutil.copy2(p,target/('framework'+ext if '/mtmemory' in n else p.name))
 result=dict(status='complete',figure_count=4,commands=commands,scientific_rerun=False,note='Rebuild from recorded scientific values; no remeasurement. Font/platform differences may change pixels.');write(out/'RUN.json',result);return result

def install_raw(archive):
 meta=json.loads((ROOT/'evidence/RAW_MANIFEST.json').read_text());p=Path(archive)
 if sha256(p)!=meta['sha256']:raise ValueError('raw archive checksum mismatch')
 expected={x['path']:x for x in meta['files']}
 with tarfile.open(p,'r:gz') as t:
  members=t.getmembers()
  if {m.name for m in members}!=set(expected):raise ValueError('raw archive inventory differs')
  for m in members:
   dst=safe_path(ROOT,m.name)
   if not m.isfile():raise ValueError('raw archive contains a nonregular member')
   if dst.exists() and sha256(dst)!=expected[m.name]['sha256']:raise FileExistsError(dst)
  for m in members:
   dst=safe_path(ROOT,m.name);dst.parent.mkdir(parents=True,exist_ok=True)
   if not dst.exists():
    with t.extractfile(m) as source,dst.open('wb') as target:shutil.copyfileobj(source,target)
   if sha256(dst)!=expected[m.name]['sha256']:raise ValueError('raw record checksum mismatch')
 return dict(passed=True,raw_files=len(expected))

def main(argv=None):
 p=argparse.ArgumentParser(description='MT-Memory current-manuscript reproducibility artifact');sub=p.add_subparsers(dest='command',required=True)
 sub.add_parser('list');v=sub.add_parser('verify');v.add_argument('--full',action='store_true')
 r=sub.add_parser('run');r.add_argument('experiment',choices=[x['id'] for x in catalog()]);r.add_argument('--output',type=Path,required=True)
 for name in ['smoke','tables','figures','prepare-data']:
  x=sub.add_parser(name);x.add_argument('--output',type=Path,required=True)
 x=sub.add_parser('install-raw');x.add_argument('--archive',type=Path,required=True)
 x=sub.add_parser('fetch-raw');x.add_argument('--url',required=True);x.add_argument('--download-to',type=Path,required=True)
 args=p.parse_args(argv)
 if args.command=='list':
  for x in catalog():print(f'{x["id"]:24s} {",".join(x["rqs"]):14s} {x["title"]}')
  return
 if args.command=='verify':result=verify(args.full)
 elif args.command=='run':result=run(args.experiment,args.output)
 elif args.command=='prepare-data':
  from .prepare import prepare
  result=prepare(args.output)
 elif args.command=='tables':
  from .analysis import tables
  result=tables(args.output)
 elif args.command=='smoke':
  from .checks import smoke
  result=smoke(args.output)
 elif args.command=='figures':result=figures(args.output)
 elif args.command=='install-raw':result=install_raw(args.archive)
 else:
  if not args.url.startswith('https://'):raise ValueError('use an HTTPS Release asset URL')
  if args.download_to.exists():raise FileExistsError(args.download_to)
  args.download_to.parent.mkdir(parents=True,exist_ok=True)
  with urllib.request.urlopen(args.url,timeout=120) as source,args.download_to.open('wb') as target:shutil.copyfileobj(source,target)
  result=install_raw(args.download_to)
 print(json.dumps(result,indent=2))
