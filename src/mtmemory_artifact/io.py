from pathlib import Path
import gzip,hashlib,json,shutil
ROOT=Path(__file__).resolve().parents[2]
def sha256(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def index(root=ROOT):return json.loads((root/'evidence/INDEX.json').read_text())['records']
def record(path,root=ROOT):
 p=str(path).removeprefix('evidence/');rows=index(root);entry=next((r for r in rows if r['runtime_path']==p),None)
 if entry is None:raise FileNotFoundError(p)
 src=root/entry['stored_path']
 if not src.exists():raise FileNotFoundError(f'{p}: install the separately supplied raw-evidence archive')
 return entry,src

def read_bytes(path,root=ROOT):
 e,p=record(path,root);return gzip.decompress(p.read_bytes()) if e['transport']=='gzip' else p.read_bytes()
def load_json(path,root=ROOT):return json.loads(read_bytes(path,root))
def safe_path(root,relative):
 p=Path(relative)
 if p.is_absolute() or '..' in p.parts:raise ValueError('unsafe artifact-relative path')
 result=(root/p).resolve()
 if root.resolve() not in result.parents:raise ValueError('path escapes artifact root')
 return result

def materialize(destination,prefixes=None,include_raw=False,root=ROOT):
 destination=Path(destination).resolve();count=0
 for e in index(root):
  if prefixes and not any(e['runtime_path'].startswith(p) for p in prefixes):continue
  if e['transport']=='raw-release' and not include_raw:continue
  src=root/e['stored_path']
  if not src.exists():
   if include_raw:raise FileNotFoundError(src)
   continue
  dst=safe_path(destination,e['runtime_path']);dst.parent.mkdir(parents=True,exist_ok=True)
  if dst.exists():raise FileExistsError(dst)
  if e['transport']=='gzip':
   with gzip.open(src,'rb') as f,dst.open('wb') as g:shutil.copyfileobj(f,g)
  else:shutil.copy2(src,dst)
  if sha256(dst)!=e['sha256']:raise ValueError(f'evidence checksum mismatch: {dst}')
  count+=1
 return count
