from pathlib import Path
import json,csv,os
os.environ.setdefault('MPLCONFIGDIR','/tmp/review4-paper-mpl')
import numpy as np
import matplotlib as mpl
mpl.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
ROOT=Path(__file__).resolve().parents[2];DATA=ROOT/'results/review4_20261109';OUT=ROOT/'paper/IEEE-conference-template-062824/figures';QA=ROOT/'results/review4_paper_20261109'
r=json.loads((DATA/'rq2_records.json').read_text());RS=[512,1024,2048,4096,8192,16384];assert np.all(np.array(RS)>0)
mpl.rcParams.update({'font.family':'sans-serif','font.sans-serif':['Arial','Helvetica','DejaVu Sans'],'font.size':7,'axes.titlesize':7.5,'axes.labelsize':7,'xtick.labelsize':7,'ytick.labelsize':7,'legend.fontsize':7,'pdf.fonttype':42,'svg.fonttype':'none','axes.spines.top':False,'axes.spines.right':False,'legend.frameon':False})
colors=['#0072B2','#D55E00','#009E73','#CC79A7'];markers=['o','s','^','D'];styles=['-','--','-.',':']
fig,axes=plt.subplots(3,3,figsize=(7.2,5.4));fig.subplots_adjust(left=.08,right=.985,bottom=.09,top=.9,wspace=.43,hspace=.5)
fig.legend(handles=[Line2D([],[],color=c,marker=m,ls=st,lw=.9,ms=3,label=f'Fine h = {h}') for h,c,m,st in zip([1,4,8,16],colors,markers,styles)],loc='upper center',ncol=4,bbox_to_anchor=(.53,.99))
source=[]
for row,B in enumerate([65536,131072,262144]):
 for col,(key,metric) in enumerate([('0/-1/-1','coverage'),('0/-1/-1','exact'),('1/0/-1','nrmse')]):
  ax=axes[row,col]
  for h,c,m,st in zip([1,4,8,16],colors,markers,styles):
   yy=[];low=[];high=[]
   for R in RS:
    v=[x for x in r if x['B']==B and x['R']==R and x['b']==128 and x['h']==h];k=max(x['k'] for x in v);v=[x for x in v if x['k']==k]
    seeds=[np.mean([x['metrics'][key][metric] for x in v if x['seed']==seed]) for seed in range(3)];yy.append(np.mean(seeds));low.append(min(seeds));high.append(max(seeds));source.append(dict(B=B,R=R,h=h,k=k,metric=metric,mean=float(yy[-1]),seed_min=float(low[-1]),seed_max=float(high[-1])))
   if col==0:
    if h!=16:continue
    c='#555555';m='o';st='-'
   ax.plot(RS,yy,color=c,marker=m,ls=st,lw=.9,ms=3,markerfacecolor='white');ax.fill_between(RS,low,high,color=c,alpha=.15,lw=0)
  ax.set_xscale('log',base=2);ax.set_xticks(RS,['512','1k','2k','4k','8k','16k']);ax.grid(axis='y',alpha=.2,lw=.5)
  ax.set_title(f'({chr(97+row*3+col)}) '+(f'{B//1024} KiB: coverage' if col==0 else 'Structural exactness' if col==1 else 'Fixed near-panel error'),loc='left',pad=5)
  if row==2:ax.set_xlabel('Declared reach')
  else:ax.tick_params(labelbottom=False)
  if col==0:ax.set_ylabel('Answered fraction');ax.set_ylim(-.025,1.04);ax.set_yticks([0,.5,1])
  elif col==1:ax.set_ylabel('Exact fraction');ax.set_ylim(-.02,.6);ax.set_yticks([0,.2,.4,.6])
  else:ax.set_ylabel('Test NRMSE');ax.set_ylim(-.01,.41);ax.set_yticks([0,.2,.4])
fig.canvas.draw();renderer=fig.canvas.get_renderer();w,h=fig.canvas.get_width_height();bad=[]
for t in fig.findobj(mpl.text.Text):
 if t.get_visible() and t.get_text():
  b=t.get_window_extent(renderer)
  if b.x0<-.5 or b.y0<-.5 or b.x1>w+.5 or b.y1>h+.5:bad.append(t.get_text())
assert not bad,bad
fig.savefig(OUT/'review4_rq2.pdf');fig.savefig(OUT/'review4_rq2.svg');fig.savefig(OUT/'review4_rq2.png',dpi=300);fig.savefig(OUT/'review4_rq2.tiff',dpi=600,pil_kwargs={'compression':'tiff_lzw'});plt.close(fig)
with (QA/'figure_source.csv').open('w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=list(source[0]));w.writeheader();w.writerows(source)
(QA/'figure_geometry.json').write_text(json.dumps(dict(panels=9,source_points=len(source),all_text_inside_canvas=True,minimum_font=7,range='three query-seed macro means; not CI'),indent=2))
