"""RQ2 figures from actual native results; no smoothing or missing-value imputation."""
from pathlib import Path
import json, os
os.environ.setdefault('MPLCONFIGDIR','/tmp/mtmemory-rq2-mpl')
import numpy as np
import matplotlib as mpl
mpl.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import MultipleLocator
ROOT=Path(__file__).resolve().parents[2]
DATA=ROOT/'results/rq2_precision_20261107'
FIG=ROOT/'paper/IEEE-conference-template-062824/figures/rq2_precision_20261107'
FIG.mkdir(parents=True,exist_ok=True)
mpl.rcParams.update({'font.family':'sans-serif','font.sans-serif':['Arial','Helvetica','DejaVu Sans'],'font.size':8,'axes.labelsize':9,'axes.titlesize':10,'xtick.labelsize':8,'ytick.labelsize':8,'legend.fontsize':8,'svg.fonttype':'none','pdf.fonttype':42,'axes.spines.top':False,'axes.spines.right':False,'axes.linewidth':.7,'legend.frameon':False,'savefig.facecolor':'white'})
WIDTHS=(8,16,32,64,128)
REACHES=(512,1024,2048,4096,8192,16384)
COLORS=('#0072B2','#009E73','#D55E00','#CC79A7','#444444')
MARKERS=('o','s','^','D','v')
STYLES=('-','--','-.',':','-')
rows=json.loads((DATA/'summary.json').read_text())
lookup={(r['budget_bytes'],r['h'],r['reach']):r for r in rows}
# Log-axis guard: reach values must be strictly positive.
assert np.all(np.asarray(REACHES) > 0)
assert all(np.diff(REACHES)>0)
YMAX=.40

def draw(ax,strip,budget,compact=False):
    for i,h in enumerate(WIDTHS):
        rr=[lookup[budget,h,r] for r in REACHES]
        good=[x for x in rr if x['feasible']]
        x=np.array([p['reach'] for p in good]);y=np.array([p['nrmse_mean'] for p in good]);ci=np.array([p['bootstrap95'] for p in good])
        assert np.all(np.isfinite(y)) and np.all(y>=0)
        # Straight segments join measured points only. No interpolation or extrapolation.
        ax.errorbar(x,y,yerr=np.vstack([y-ci[:,0],ci[:,1]-y]),color=COLORS[i],marker=MARKERS[i],linestyle=STYLES[i],linewidth=1.15,markersize=3.4,capsize=2,elinewidth=.65,capthick=.65,label=f'h = {h}')
        strip.scatter([p['reach'] for p in rr if not p['feasible']],[i]*sum(not p['feasible'] for p in rr),marker='x',s=21,linewidths=1,color=COLORS[i],clip_on=False)
    ax.set_xscale('log',base=2);strip.set_xscale('log',base=2)
    ax.set_xlim(420,20000);ax.set_ylim(0,YMAX)
    ax.yaxis.set_major_locator(MultipleLocator(.05));ax.grid(axis='y',color='#CFD6DD',linewidth=.6,alpha=.8)
    ax.tick_params(axis='x',labelbottom=False,length=0)
    ax.set_ylabel('Test NRMSE');ax.set_title(f'History ledger: {budget//1024} KiB',loc='left',pad=8,fontweight='bold')
    ax.legend(loc='upper left',bbox_to_anchor=(0,1.005),ncol=3 if not compact else 2,handlelength=2.0,columnspacing=1.0,labelspacing=.3,borderaxespad=.4,fontsize=8 if not compact else 7)
    strip.set_ylim(4.7,-.8);strip.set_yticks(range(5),[str(h) for h in WIDTHS]);strip.tick_params(axis='y',length=0,pad=4,labelsize=7)
    strip.set_ylabel('Over budget\nh',fontsize=7,rotation=0,rotation_mode='anchor',labelpad=27,va='center')
    strip.set_xticks(REACHES,[f'{r:,}' for r in REACHES]);strip.tick_params(axis='x',length=3,pad=4,labelsize=8 if not compact else 7)
    strip.set_xlabel('Declared reach',labelpad=6)
    strip.grid(axis='x',color='#E5E9ED',linewidth=.5)
    strip.spines['left'].set_visible(False);strip.spines['top'].set_visible(False);strip.spines['right'].set_visible(False)
    strip.spines['bottom'].set_color('#AAB4BD')

def export(fig,name):
    fig.savefig(FIG/f'{name}.pdf',facecolor='white')
    fig.savefig(FIG/f'{name}.svg',facecolor='white')
    fig.savefig(FIG/f'{name}.png',dpi=300,facecolor='white')
    fig.savefig(FIG/f'{name}.tiff',dpi=600,facecolor='white')
    # Require all text bounding boxes to remain inside the figure canvas.
    fig.canvas.draw();ren=fig.canvas.get_renderer();W,H=fig.canvas.get_width_height();bad=[]
    for a in fig.findobj(mpl.text.Text):
        if not a.get_visible() or not a.get_text():continue
        bb=a.get_window_extent(ren)
        if bb.x0 < -1 or bb.y0 < -1 or bb.x1>W+1 or bb.y1>H+1:bad.append(a.get_text())
    assert not bad,bad
    max_ci=max(r['bootstrap95'][1] for r in rows if r['feasible'])
    for ax in fig.axes:
        leg=ax.get_legend()
        if leg is not None:assert leg.get_window_extent(ren).y0>ax.transData.transform((512,max_ci))[1]+2

notes='Mean across 13 entities; bars: descriptive 95% bootstrap intervals.\nSmaller h = finer saved detail. × below the axis = over budget; no NRMSE point.'
for budget in (65536,131072,262144):
    fig=plt.figure(figsize=(7.2,4.65));gs=fig.add_gridspec(2,1,height_ratios=[4.8,1],hspace=.06,left=.15,right=.975,bottom=.23,top=.91)
    ax=fig.add_subplot(gs[0]);strip=fig.add_subplot(gs[1],sharex=ax);draw(ax,strip,budget)
    fig.text(.15,.045,notes,fontsize=7.5,linespacing=1.4,color='#444444')
    export(fig,f'rq2_{budget//1024}KiB');plt.close(fig)
# Three-budget comparison uses shared scales and redundant color/shape encodings.
fig=plt.figure(figsize=(10.8,4.3));gs=fig.add_gridspec(2,3,height_ratios=[4.6,1],hspace=.06,wspace=.38,left=.085,right=.985,bottom=.24,top=.91)
for j,budget in enumerate((65536,131072,262144)):
    ax=fig.add_subplot(gs[0,j]);strip=fig.add_subplot(gs[1,j],sharex=ax);draw(ax,strip,budget,compact=True)
fig.text(.085,.045,notes,fontsize=8,linespacing=1.4,color='#444444')
export(fig,'rq2_all_budgets');plt.close(fig)
# Grayscale QA retains marker and dash distinctions.
from PIL import Image
Image.open(FIG/'rq2_all_budgets.png').convert('L').save(FIG/'rq2_all_budgets_grayscale.png')
print(FIG)
