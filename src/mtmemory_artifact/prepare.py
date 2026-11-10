"""Rebuild the exact chronological arrays from integrity-checked UCI archives."""
from pathlib import Path
import csv,io,json,zipfile
import numpy as np
from .io import ROOT,sha256

def causal_fill(x):
 x=np.asarray(x,np.float64);last=np.zeros(x.shape[1]);missing=~np.isfinite(x)
 for i in range(len(x)):
  mask=np.isfinite(x[i]);last[mask]=x[i,mask];x[i]=last
 return x,int(missing.sum())

def prepare(output,root=ROOT):
 out=Path(output).resolve()
 if out.exists():raise FileExistsError(f'refusing to overwrite {out}')
 for info in json.loads((root/'data/real/SOURCES.json').read_text()):
  p=root/'data/raw'/f'{info["name"]}.zip'
  if sha256(p)!=info['sha256']:raise ValueError('raw archive hash differs: '+info['name'])
 out.mkdir(parents=True);datasets={};stations=[]
 with zipfile.ZipFile(root/'data/raw/bike.zip') as z:
  rows=list(csv.DictReader(io.TextIOWrapper(z.open('hour.csv'))));datasets['bike']=[np.array([[float(r[k]) for k in ['cnt','temp','hum','windspeed']] for r in rows])]
 with zipfile.ZipFile(root/'data/raw/beijing.zip') as outer:
  nested=next((n for n in outer.namelist() if n.endswith('.zip')),None)
  z=zipfile.ZipFile(io.BytesIO(outer.read(nested))) if nested else outer
  vals=[]
  for name in sorted(n for n in z.namelist() if n.endswith('.csv') and 'PRSA_Data_' in n):
   rows=list(csv.DictReader(io.TextIOWrapper(z.open(name))));x=np.array([[float(r[k]) if r[k] not in ['NA',''] else np.nan for k in ['PM2.5','TEMP','PRES','WSPM']] for r in rows]);x,missing=causal_fill(x);vals.append(x);stations.append(dict(entity=len(vals)-1,source_member=name,filled_values=missing))
  datasets['beijing']=vals
 with zipfile.ZipFile(root/'data/raw/household.zip') as z:
  member=next(n for n in z.namelist() if n.endswith('.txt'))
  with z.open(member) as f:
   rows=csv.DictReader(io.TextIOWrapper(f),delimiter=';')
   columns=['Global_active_power','Global_reactive_power','Voltage','Global_intensity']
   def values():
    for row in rows:
     for c in columns:
      try:yield float(row[c])
      except ValueError:yield np.nan
   x=np.fromiter(values(),dtype=np.float64).reshape(-1,4)
  x,house_missing=causal_fill(x);datasets['household']=[x]
 checks=[]
 for name,units in datasets.items():
  arrays={}
  for i,x in enumerate(units):
   a=int(len(x)*.6);b=int(len(x)*.8);mu=x[:a].mean(0);sd=np.maximum(x[:a].std(0),1e-6);y=((x-mu)/sd).astype(np.float32)
   if name=='household':
    arrays.update(train_0=y[:a].copy(),validation_0=y[a:b].copy(),test_0=y[b:].copy(),physical=x.astype(np.float32),mean=mu,std=sd)
   else:
    arrays.update({f'train_{i}':y[:a].copy(),f'validation_{i}':y[a:b].copy(),f'test_{i}':y[b:].copy(),f'mean_{i}':mu,f'std_{i}':sd})
  reference=np.load(root/f'data/real/{name}.npz');assert set(reference.files)==set(arrays)
  for key,value in arrays.items():
   if not np.array_equal(value,reference[key]):raise AssertionError(f'{name}/{key} not bitwise equal to published array')
  np.savez_compressed(out/f'{name}.npz',**arrays);checks.append(dict(dataset=name,entities=len(units),arrays=len(arrays),all_arrays_bitwise_equal=True))
 (out/'PREPARATION.json').write_text(json.dumps(dict(checks=checks,beijing_stations=stations,household_missing_values=house_missing,normalization='training mean/std only; minimum std1e-6; chronological60/20/20',causal_fill='forward fill all nonfinite values; zero until first finite observation',time='ingestion-index distance; no civil-hour gap insertion'),indent=2)+'\n')
 return checks
