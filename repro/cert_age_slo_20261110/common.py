from pathlib import Path
import sys,json
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'src'))
from mtmemory_icde.core.evidence_service import EvidenceService
OUT=ROOT/'results/cert_age_slo_20261110'
def write(p,x):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(x,indent=2,allow_nan=False)+'\n')
def service_at(config,rows,t,mode='sum'):
    s=EvidenceService(**config['options'],certificate_mode=mode)
    s.initialize_facts(128);o=config['options'];b=o['base_width'];R=o['max_reach']
    start=max(0,(t-R-2*b)//b*b);s.history.event_count=start
    for row in rows[start:t]:s.observe(row,count_ack=False)
    assert s.event_count==t
    return s
def units():
    for ds,n in [('bike',1),('beijing',12),('household',1)]:
        with np.load(ROOT/f'data/real/{ds}.npz') as z:
            for e in range(n):yield ds,e,*[z[f'{name}_{e}'].astype(np.float32) for name in ['train','validation','test']]
def selected():return json.loads((OUT/'SELECTIONS.json').read_text())

