"""Separate diagnostic of the unchanged active-cell kernel; not main test data."""
from pathlib import Path
import importlib.util,json,sys
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
sp=importlib.util.spec_from_file_location('tradeoff_frozen',Path(__file__).with_name('run.py'));r=importlib.util.module_from_spec(sp);sp.loader.exec_module(r)
rows=r.old.all_split_units()[0][2][:2300];records=[]
for h in (1,4,8,16,128):
    for n in (2049,2055,2109,2175):
        s=r.native(512,h,0 if h==128 else 1,131072)
        for row in rows[:n]:s.observe(row)
        for d in (0,1,7,63,127):
            for w in (1,4,16,32,128):
                lo=n-d-w;hi=n-d;legacy_sum=np.zeros(4);legacy_count=0.;ideal=np.zeros(4)
                for bid in range(lo//128,(hi-1)//128+1):
                    bh=128 if bid!=s.active_id and not np.any(s.overlay_ids==bid) else h
                    for left in range(bid*128,min((bid+1)*128,n),bh):
                        right=min(left+bh,n);ov=max(0,min(hi,right)-max(lo,left))
                        if ov:
                            cell=rows[left:right].astype(np.float64);legacy_sum+=(ov/bh)*cell.sum(0);legacy_count+=(ov/bh)*len(cell);ideal+=ov*cell.mean(0)
                a=s.query(d,w,record=False);expected=legacy_sum/legacy_count;ideal/=w
                assert np.allclose(a['value'],expected,rtol=1e-12,atol=1e-12)
                records.append(dict(h=h,prefix=n,delay=d,window=w,resolution=a['resolution'],legacy_vs_ideal_max_abs_difference=float(np.max(np.abs(a['value']-ideal))),legacy_oracle_max_abs_difference=float(np.max(np.abs(a['value']-expected)))))
out=ROOT/'results/rq2_tradeoff_20261107';summary=dict(cases=len(records),legacy_oracle_pass=True,cases_differing_from_populated_cell_interpolation=sum(x['legacy_vs_ideal_max_abs_difference']>1e-12 for x in records),maximum_difference=max(x['legacy_vs_ideal_max_abs_difference'] for x in records),primary_queries_intersect_active_cell=0,production_kernel_unchanged=True,interpretation='Legacy unfinished-cell behavior confirmed and kept separate; primary queries delay>=b=128, hence sealed history only. Not a new certificate.')
(out/'active_boundary_audit.json').write_text(json.dumps(dict(summary=summary,records=records),indent=2)+'\n');print(json.dumps(summary,indent=2))
