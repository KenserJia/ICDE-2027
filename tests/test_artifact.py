from pathlib import Path
import json
from mtmemory_artifact.io import ROOT
from mtmemory_artifact.cli import catalog,verify

def test_current_paper_registry_and_readonly_input_scope():
 rows=catalog();assert len(rows)==len({r['id'] for r in rows}) and {q for r in rows for q in r['rqs']}=={'RQ1','RQ2','RQ3','RQ4','RQ5'}
 for r in rows:
  for c in r['commands']:
   folder=ROOT/c['cwd'];assert folder.is_dir()
   if c['argv'][1]!='-c':assert (folder/c['argv'][1]).is_file()
  for p in r['reference_inputs']:
   from mtmemory_artifact.io import record
   e,source=record(p);assert source.exists()
 assert (ROOT/'LICENSE').read_text().startswith('MIT License')
 assert 'CC BY 4.0' in (ROOT/'data/README.md').read_text()

def test_published_integrity_and_original_core_hashes():
 assert verify()['passed']
 from mtmemory_artifact.io import sha256
 original=json.loads((ROOT/'provenance/CORE_SHA256.json').read_text())
 assert all(sha256(ROOT/p)==h for p,h in original.items())
