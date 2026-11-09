"""All paired entity contrasts from frozen symmetric RQ3 validation/test outputs."""
from pathlib import Path
import os,json
os.environ.setdefault('MPLCONFIGDIR','/tmp/rq3-symmetric-mpl')
import numpy as np
import matplotlib as mpl
mpl.use('Agg')
import matplotlib.pyplot as plt
from PIL import Image
ROOT=Path(__file__).resolve().parents[2];DATA=ROOT/'results/rq3_symmetric_20261107';OUT=ROOT/'paper/IEEE-conference-template-062824/figures';ORDER=('stable','critical','dynamic_dominant','held12','held24','held28');LABELS=('Near','Switch','Far','H12','H24','H28')
mpl.rcParams.update({'font.family':'sans-serif','font.sans-serif':['Arial','Helvetica','DejaVu Sans'],'font.size':7,'axes.titlesize':8,'axes.labelsize':7,'xtick.labelsize':7,'ytick.labelsize':7,'legend.fontsize':7,'pdf.fonttype':42,'svg.fonttype':'none','axes.spines.top':False,'axes.spines.right':False,'axes.linewidth':.7,'legend.frameon':False})
summary=json.loads((DATA/'summary.json').read_text());raw=json.loads((DATA/'selected_results.json').read_text());layout=json.loads((DATA/'layouts.json').read_text());same=json.loads((DATA/'same_layout_summary.json').read_text());qa=[]
def points(profile,label):
    rr=[x for x in raw if x['profile']==profile and x['workload']==label];ix={(x['dataset'],x['entity'],x['policy']):x for x in rr};units=sorted({(x['dataset'],x['entity']) for x in rr});return np.array([ix[d,e,'online']['mse']-ix[d,e,'recent']['mse'] for d,e in units])
def paired(ax,profile,title):
    all_d=[]
    for i,label in enumerate(ORDER):
        values=points(profile,label);all_d.extend(values);row=next(x for x in summary if x['profile']==profile and x['workload']==label);mean=row['online_minus_recent'];lo,hi=row['bootstrap95']
        # Horizontal offsets reveal all paired entities; y values are never altered.
        ax.scatter(i+np.linspace(-.13,.13,13),values,s=9,c='#A7AFB7',alpha=.8,zorder=2)
        ax.errorbar(i,mean,yerr=[[max(0,mean-lo)],[max(0,hi-mean)]],fmt='D',ms=3.5,capsize=2,color='#0072B2',elinewidth=.8,zorder=3)
    ax.axhline(0,color='#555555',lw=.7);ax.set_xticks(range(6),LABELS);ax.set_ylabel('Tuned dynamic − tuned recent MSE');ax.set_title(title,loc='left',pad=7);ax.grid(axis='y',alpha=.18)
    return all_d

def save(fig,name):
    fig.canvas.draw();ren=fig.canvas.get_renderer();W,H=fig.canvas.get_width_height();bad=[]
    for t in fig.findobj(mpl.text.Text):
        if not t.get_visible() or not t.get_text():continue
        b=t.get_window_extent(ren)
        if b.x0<-.5 or b.y0<-.5 or b.x1>W+.5 or b.y1>H+.5:bad.append(t.get_text())
    assert not bad,bad
    fig.savefig(OUT/f'{name}.pdf');fig.savefig(OUT/f'{name}.svg');fig.savefig(OUT/f'{name}.png',dpi=300);fig.savefig(OUT/f'{name}.tiff',dpi=600,pil_kwargs={'compression':'tiff_lzw'});plt.close(fig);qa.append(dict(figure=name,text_canvas_pass=True,all13_entity_pairs_retained=True))
# Main-paper panel (a) retains the original calibration; panel (b) replaces one-sided tuning.
fig,(a,b)=plt.subplots(1,2,figsize=(7.2,2.45));fig.subplots_adjust(left=.075,right=.99,bottom=.28,top=.84,wspace=.48)
cal=json.loads((ROOT/'results/frozen/rq_closure/rq3_boundary/calibration_summary.json').read_text());shifts=[8,16,24,30];dwells=[4,16,64,256,0];grid=np.array([[np.mean([x['mean_mse_dynamic_minus_fixed'] for x in cal if x['spec']['shift_buckets']==shift and x['spec']['dwell_queries']==dwell]) for dwell in dwells] for shift in shifts]);lim=np.max(np.abs(grid))
im=a.imshow(grid,cmap='RdBu_r',vmin=-lim,vmax=lim,aspect='auto');a.set_xticks(range(5),['4','16','64','256','Steady']);a.set_yticks(range(4),shifts);a.set_xlabel('Hotspot dwell (queries)');a.set_ylabel('Shift (coarse buckets)');a.set_title('(a) Original matched-layout calibration',loc='left')
for i in range(4):
    for j in range(5):a.text(j,i,f'{1000*grid[i,j]:.1f}',ha='center',va='center',fontsize=7,color='white' if abs(grid[i,j])>.6*lim else '#111111')
cb=fig.colorbar(im,ax=a,orientation='horizontal',fraction=.075,pad=.37);cb.ax.tick_params(labelsize=7);cb.set_label('Dynamic − original recent MSE',fontsize=7,labelpad=1)
paired(b,'verified50924','(b) Both layouts tuned: 13 candidates')
save(fig,'rq3_symmetric_scope')
# Standalone resource sensitivity with consistent y scaling and all gains/losses/ties.
fig,axes=plt.subplots(1,2,figsize=(7.2,3.2));fig.subplots_adjust(left=.085,right=.985,bottom=.28,top=.84,wspace=.38)
all_d=[]
for ax,profile,title in zip(axes,('verified50924','verified44780'),('(a) 50,924 B: 13 candidates per policy','(b) 44,780 B: 7 candidates per policy')):all_d+=paired(ax,profile,title)
lo=min(all_d);hi=max(all_d);pad=.12*(hi-lo)
for ax in axes:ax.set_ylim(lo-pad,hi+pad)
fig.text(.085,.105,'Gray: 13 paired entities; blue: mean and descriptive 95% entity-bootstrap interval (5,000 resamples).',fontsize=7)
fig.text(.085,.05,'Positive favors tuned recent; negative favors tuned dynamic. Correlated stations limit inference.',fontsize=7)
save(fig,'rq3_symmetric_budget')
# Same-layout effect: every geometry is kept, not a test-selected optimum.
fig,ax=plt.subplots(figsize=(7.2,4.7));fig.subplots_adjust(left=.2,right=.88,bottom=.2,top=.9)
mat=np.array([[next(x for x in same if x['layout']==c['name'] and x['workload']==w)['mean_online_minus_recent'] for w in ORDER] for c in layout]);lim=float(np.max(np.abs(mat)));assert lim>0
im=ax.imshow(mat,cmap='RdBu_r',vmin=-lim,vmax=lim,aspect='auto');ax.set_xticks(range(6),LABELS);ax.set_yticks(range(13),[c['name']+(' *' if c['verified_charge']<=44780 else '') for c in layout]);ax.set_ylabel('Shared (b, f, k) layout');ax.set_title('Same-layout dynamic − recent MSE',loc='left',pad=8)
for i in range(13):
    for j in range(6):ax.text(j,i,f'{1000*mat[i,j]:.2f}',ha='center',va='center',fontsize=7,color='white' if abs(mat[i,j])>.65*lim else '#111111')
cb=fig.colorbar(im,ax=ax,fraction=.04,pad=.035);cb.set_label('Mean paired MSE difference');fig.text(.2,.1,'Cell labels are 1,000 × mean difference over all 13 entities; color uses raw MSE.',fontsize=7);fig.text(.2,.055,'* Fits the stricter 44,780 B verified ledger. No test-based layout selection.',fontsize=7)
save(fig,'rq3_symmetric_same_layout')
Image.open(OUT/'rq3_symmetric_budget.png').convert('L').save(OUT/'rq3_symmetric_budget_grayscale.png')
(DATA/'figure_layout_QA.json').write_text(json.dumps(qa,indent=2)+'\n')
print('Generated main scope, symmetric budget comparison and all same-layout effects.')
