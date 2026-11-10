from pathlib import Path
import numpy as np,zipfile,csv,json,hashlib
ROOT=Path(__file__).resolve().parents[2]
p=ROOT/'data/raw/household_power.zip'
with zipfile.ZipFile(p) as z:
 name=next(n for n in z.namelist() if n.endswith('.txt'))
 with z.open(name) as f:
  import io
  reader=csv.DictReader(io.TextIOWrapper(f),delimiter=';');cols=['Global_active_power','Global_reactive_power','Voltage','Global_intensity']
  rows=[];missing=0;previous=np.zeros(4,dtype=float);first=None;last=None
  for r in reader:
   if first is None:first=r['Date']+' '+r['Time']
   last=r['Date']+' '+r['Time'];v=previous.copy()
   for j,c in enumerate(cols):
    try:v[j]=float(r[c])
    except ValueError:missing+=1
   previous=v;rows.append(v)
 x=np.asarray(rows,np.float64);n=len(x);a=int(n*.6);b=int(n*.8);mean=x[:a].mean(0);std=x[:a].std(0);normalized=((x-mean)/std).astype(np.float32)
 out=ROOT/'data/real/household.npz'
 np.savez_compressed(out,train_0=normalized[:a],validation_0=normalized[a:b],test_0=normalized[b:],physical=x.astype(np.float32),mean=mean,std=std)
 meta=dict(source='https://archive.ics.uci.edu/dataset/235/individual+household+electric+power+consumption',doi='10.24432/C58K54',license='CC BY4.0',raw_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),channels=cols,counts=[a,b-a,n-b],missing_cells=missing,imputation='causal forward fill across chronological splits; initial zero only if leading value missing',normalization='training mean/std only',first=first,last=last,interval_minutes=1)
 (ROOT/'results/w1w4_20261110/DATA.json').write_text(json.dumps(meta,indent=2)+'\n');print(meta)
