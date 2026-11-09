from pathlib import Path
import sys,json,time,numpy as np,duckdb
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'repro/round78_rq_closure'));import run as old
OUT=ROOT/'results/review2_20261104';results=[]
specs=json.loads((ROOT/'results/frozen/rq_closure/rq3_boundary/RQ3_FREEZE.json').read_text())['workloads']
for ui,(ds,en,train,val,test) in enumerate(old.all_split_units()):
 rows=np.concatenate([train[-4096:],val,test]);offset=len(rows)-len(test);db=duckdb.connect();db.execute('SET threads=1');db.execute('CREATE TABLE observations(i BIGINT, a DOUBLE,b DOUBLE,c DOUBLE,d DOUBLE)')
 db.executemany('INSERT INTO observations VALUES (?,?,?,?,?)',[(i,*map(float,x)) for i,x in enumerate(rows)])
 for label,sp in specs.items():
  qs=old.workload_queries(len(test),sp['spec'],20261104+ui*31,warmup=2432,offset=offset)
  for seed in [11,29,47]:
   # Upstream reservoir sample, built separately for each retained R=4096 horizon.
   errs=[];exacterr=[];lat=[];exlat=[];empties=0
   for q in qs:
    t=q['t'];lo=t-q['delay']-q['window'];hi=t-q['delay'];truth=rows[lo:hi].astype('float64').mean(0)
    started=time.perf_counter_ns();v=db.execute('SELECT avg(a),avg(b),avg(c),avg(d) FROM observations WHERE i>=? AND i<?',[lo,hi]).fetchone();exlat.append((time.perf_counter_ns()-started)/1000);exacterr.append(float(np.mean((np.asarray(v)-truth)**2)))
    # Materialize from a retained raw source, not from bounded online state.
    db.execute(f'CREATE OR REPLACE TEMP TABLE sample AS SELECT * FROM (SELECT * FROM observations WHERE i>={t-4096} AND i<{t}) USING SAMPLE reservoir(512 ROWS) REPEATABLE({seed})')
    started=time.perf_counter_ns();v=db.execute('SELECT sum(a),sum(b),sum(c),sum(d),count(*) FROM sample WHERE i>=? AND i<?',[lo,hi]).fetchone();lat.append((time.perf_counter_ns()-started)/1000)
    if v[4]==0:empties+=1
    pred=np.asarray([0. if x is None else x for x in v[:4]])*(4096/512)/q['window'];errs.append(float(np.mean((pred-truth)**2)))
   results.append(dict(dataset=ds,entity=en,workload=label,seed=seed,queries=len(qs),sampling_mse=float(np.mean(errs)),exact_mse=float(np.mean(exacterr)),empty_sample_ranges=empties,sample_query_p50_us=float(np.median(lat)),exact_query_p50_us=float(np.median(exlat)),sample_payload_bytes=512*40,raw_payload_bytes=len(rows)*40,retained_raw_payload_bytes=4096*40,duckdb_version=duckdb.__version__,contract='offline exact and uniform-reservoir range operators; raw source retained; not managed-budget or RPO matched; sample rebuilding excluded from query latency'))
 db.close();(OUT/'duckdb_raw.json').write_text(json.dumps(results,indent=2)+'\n');print('DuckDB entity complete',ds,en,flush=True)
print('COMPLETE',sum(r['queries'] for r in results))
