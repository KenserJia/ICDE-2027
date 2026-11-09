"""Fixed-query resource tradeoff triptychs and distance composition supplements."""
from pathlib import Path
import json,os,shutil
os.environ.setdefault('MPLCONFIGDIR','/tmp/mtmemory-tradeoff-mpl')
import numpy as np
import matplotlib as mpl
mpl.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from PIL import Image
ROOT=Path(__file__).resolve().parents[2];DATA=ROOT/'results/rq2_tradeoff_20261107';FIG=ROOT/'paper/IEEE-conference-template-062824/figures/rq2_tradeoff_20261107';FIG.mkdir(parents=True,exist_ok=True)
mpl.rcParams.update({'font.family':'sans-serif','font.sans-serif':['Arial','Helvetica','DejaVu Sans'],'font.size':7,'axes.labelsize':7.5,'axes.titlesize':8,'xtick.labelsize':7,'ytick.labelsize':7,'legend.fontsize':7,'svg.fonttype':'none','pdf.fonttype':42,'axes.spines.top':False,'axes.spines.right':False,'axes.linewidth':.7,'legend.frameon':False})
BUDGETS=(65536,131072,262144);REACHES=(512,1024,2048,4096,8192,16384)
METHODS=('h1','h4','h8','h16','coarse','tail')
LABELS=('Fine h = 1','Fine h = 4','Fine h = 8','Fine h = 16','Coarse only','Exact tail')
COLORS=('#0072B2','#009E73','#D55E00','#AA4499','#777777','#111111')
MARKERS=('o','s','^','D','v','x');STYLES=('-','--','-.',':','--','-')
s=json.loads((DATA/'summary.json').read_text());dist=json.loads((DATA/'distance_summary.json').read_text())
# Strictly positive reach is required by the log2 axis.
assert np.all(np.asarray(REACHES)>0)
assert all(np.isfinite(r['common_nrmse']) and r['common_nrmse']>=0 for r in s)
lookup={(r['budget'],r['reach'],r['method']):r for r in s};qa=[]
C_MAX=float(np.ceil(max(r['common_nrmse_ci95'][1] for r in s)/.05)*.05+.025)
handles=[Line2D([],[],color=c,marker=m,ls=ls,lw=1.1,markersize=3.4,label=label,markerfacecolor='white' if m!='x' else c) for c,m,ls,label in zip(COLORS,MARKERS,STYLES,LABELS)]

def export(fig,stem):
    fig.canvas.draw();ren=fig.canvas.get_renderer();W,H=fig.canvas.get_width_height();bad=[]
    for text in fig.findobj(mpl.text.Text):
        if not text.get_visible() or not text.get_text():continue
        bb=text.get_window_extent(ren)
        if bb.x0<-.5 or bb.y0<-.5 or bb.x1>W+.5 or bb.y1>H+.5:bad.append(text.get_text())
    assert not bad,bad
    fig.savefig(FIG/f'{stem}.pdf',facecolor='white')
    fig.savefig(FIG/f'{stem}.svg',facecolor='white')
    fig.savefig(FIG/f'{stem}.png',dpi=300,facecolor='white')
    fig.savefig(FIG/f'{stem}.tiff',dpi=600,facecolor='white',pil_kwargs={'compression':'tiff_lzw'})
    qa.append(dict(figure=stem,text_canvas_check=True,minimum_source_font_pt=7,vector_text_editable=True))

for B in BUDGETS:
    fig,axs=plt.subplots(1,3,figsize=(7.2,3.3));fig.subplots_adjust(left=.075,right=.985,bottom=.27,top=.73,wspace=.39)
    fig.suptitle(f'History ledger: {B//1024} KiB',x=.075,y=.985,ha='left',fontsize=10,fontweight='bold')
    fig.legend(handles=handles,loc='upper center',bbox_to_anchor=(.54,.93),ncol=3,columnspacing=2.3,handlelength=2.5)
    for j,(metric,title,ylabel) in enumerate(zip(('answered','exact','common_nrmse'),('(a) Historical answerability','(b) Structural exactness','(c) Error on unchanged queries'),('Answered-query coverage','Exact-query coverage','Test NRMSE (common queries)'))):
        ax=axs[j]
        for i,m in enumerate(METHODS):
            rr=[lookup[B,R,m] for R in REACHES]
            # All five native answered-coverage curves coincide exactly; show one trace.
            if j==0 and m not in ('coarse','tail'):
                assert all(lookup[B,R,m]['answered']==lookup[B,R,'coarse']['answered'] for R in REACHES);continue
            y=np.array([r[metric] for r in rr]);ci=np.array([r[metric+'_ci95'] for r in rr]);err=np.maximum(0,np.vstack([y-ci[:,0],ci[:,1]-y]))
            ax.errorbar(REACHES,y,yerr=err,color=COLORS[i],marker=MARKERS[i],ls=STYLES[i],lw=1.0,ms=3.2,capsize=1.5,elinewidth=.55,markerfacecolor='white' if MARKERS[i]!='x' else COLORS[i],markeredgewidth=.8)
        ax.set_title(title,loc='left',pad=6);ax.set_xscale('log',base=2);ax.set_xlim(420,20000);ax.set_xticks(REACHES,['512','1k','2k','4k','8k','16k']);ax.set_xlabel('Declared reach');ax.set_ylabel(ylabel);ax.grid(axis='y',color='#D5DCE1',lw=.55)
        if j<2:ax.set_ylim(-.035,1.035);ax.set_yticks([0,.25,.5,.75,1])
        else:ax.set_ylim(-.015,C_MAX)
    axs[0].text(.04,.94,'All tiered layouts coincide',transform=axs[0].transAxes,va='top',fontsize=7,color='#555555')
    fig.text(.075,.125,'Means of 13 entities; bars: descriptive 95% entity-bootstrap intervals (correlated stations).',fontsize=7)
    fig.text(.075,.075,'Global demand is fixed across layouts; common queries always lie within reach 512. No smoothing.',fontsize=7)
    fig.text(.075,.025,'Fine h is the overlay width; b = 128. Ledger includes images and workspace; it is not an RSS cap.',fontsize=7)
    export(fig,f'rq2_triptych_{B//1024}KiB');plt.close(fig)
# Actual oldest-query-age composition for every method at prespecified reaches.
STATE_COLORS=('#0072B2','#E69F00','#DDDDDD');STATE_LABELS=('Exact','Approximate','Unavailable')
STATE_HATCH=('', '///', '..')
for B in BUDGETS:
    for R in (512,4096,16384):
        fig,axs=plt.subplots(2,3,figsize=(7.2,4.85));fig.subplots_adjust(left=.08,right=.985,bottom=.22,top=.79,hspace=.52,wspace=.3)
        fig.suptitle(f'Actual query-age composition | {B//1024} KiB | Declared reach {R:,}',x=.08,y=.98,ha='left',fontsize=9,fontweight='bold')
        ph=[Patch(facecolor=c,hatch=h,label=l,edgecolor='#555555',linewidth=.3) for c,h,l in zip(STATE_COLORS,STATE_HATCH,STATE_LABELS)]
        fig.legend(handles=ph,loc='upper center',bbox_to_anchor=(.54,.925),ncol=3,handlelength=2.0)
        for i,(ax,m) in enumerate(zip(axs.flat,METHODS)):
            rows=sorted([r for r in dist if r['budget']==B and r['reach']==R and r['method']==m],key=lambda r:r['age_bin']);x=np.arange(7);bottom=np.zeros(7)
            for key,c,h in zip(('exact','approximate','unavailable'),STATE_COLORS,STATE_HATCH):
                y=np.array([r[key] for r in rows]);ax.bar(x,y,bottom=bottom,width=.78,color=c,hatch=h,edgecolor='#777777',linewidth=.25);bottom+=y
            assert np.allclose(bottom,1)
            ax.set_title(f'({chr(97+i)}) {LABELS[i]}',loc='left',pad=4);ax.set_ylim(0,1.03);ax.set_yticks([0,.5,1]);ax.set_xticks(x,['256','512','1k','2k','4k','8k','16k']);ax.set_ylabel('Query fraction' if i%3==0 else '');ax.tick_params(axis='x',pad=2)
        fig.text(.08,.125,'Oldest query age: bin upper endpoint (observations); bins run from (128, 256] to (8,192, 16,384].',fontsize=7)
        fig.text(.08,.075,'Bar heights: mean state fractions over 13 entities; bins have equal global-demand weight.',fontsize=7)
        fig.text(.08,.025,'Composition only: no inference intervals; entity fractions and per-bin errors are retained in source data.',fontsize=7)
        export(fig,f'rq2_distance_{B//1024}KiB_R{R}');plt.close(fig)
# Preserve prior fixed-h supplement and source data byte for byte.
prior=FIG.parent/'rq2_precision_20261107';sup=FIG/'supplement_fixed_h';sup.mkdir(exist_ok=True)
for p in prior.iterdir():
    if p.suffix in ('.pdf','.svg','.png','.tiff'):shutil.copy2(p,sup/p.name)
for name in ('source_data.csv','entity_source_data.csv','RESULTS.txt','PROTOCOL.md'):
    p=ROOT/'results/rq2_precision_20261107'/name
    if p.exists():shutil.copy2(p,sup/name)
shutil.copy2(ROOT/'repro/rq2_precision_20261107/PROTOCOL.md',sup/'PROTOCOL.md')
# Color and grayscale contact sheets are inspection aids, not manuscript panels.
files=[FIG/f'rq2_triptych_{b}KiB.png' for b in (64,128,256)]
imgs=[Image.open(f).convert('RGB') for f in files];contact=Image.new('RGB',(imgs[0].width,sum(x.height for x in imgs)),'white');y=0
for im in imgs:contact.paste(im,(0,y));y+=im.height
contact.save(FIG/'triptychs_contact.png');contact.convert('L').save(FIG/'triptychs_grayscale.png')
dimgs=[Image.open(FIG/f'rq2_distance_{b}KiB_R{r}.png').convert('RGB') for b in (64,128,256) for r in (512,4096,16384)]
thumbs=[]
for im in dimgs:im.thumbnail((864,582));thumbs.append(im)
contact=Image.new('RGB',(864*3,582*3),'white')
for i,im in enumerate(thumbs):contact.paste(im,((i%3)*864,(i//3)*582))
contact.save(FIG/'distance_contact.png')
(DATA/'figure_layout_QA.json').write_text(json.dumps(qa,indent=2)+'\n')
print(FIG)
