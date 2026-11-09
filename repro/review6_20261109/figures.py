from pathlib import Path
import json
import numpy as np
import matplotlib as mpl
mpl.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.colors import TwoSlopeNorm
from matplotlib.ticker import FuncFormatter, NullFormatter, NullLocator
from PIL import Image,ImageOps
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'results/review6_20261109';DEST=OUT/'figures';DEST.mkdir(exist_ok=True)
A=json.loads((OUT/'analysis.json').read_text());COLORS={'none':'#777777','sync':'#2B6E9B','strict':'#C67535','fused':'#247F80','cache32':'#6A5598','on_demand':'#2B6E9B','cache32_on_demand':'#C67535'}
mpl.rcParams.update({'font.family':'sans-serif','font.sans-serif':['Arial','Helvetica','DejaVu Sans'],'font.size':7,'axes.labelsize':7,'xtick.labelsize':6.5,'ytick.labelsize':6.5,'legend.fontsize':6.2,'axes.titlesize':7.5,'pdf.fonttype':42,'svg.fonttype':'none','axes.spines.top':False,'axes.spines.right':False,'axes.linewidth':.6,'lines.linewidth':1.,'savefig.facecolor':'white'})
QA=[];PAGES=[]
def errorline(ax,x,rows,metric,label,color,marker,linestyle='-'):
 y=np.array([r[metric] for r in rows]);lo=np.array([r[metric+'_min'] for r in rows]);hi=np.array([r[metric+'_max'] for r in rows]);assert np.all(np.isfinite(y)) and np.all(y > 0) and np.all(lo > 0)
 ax.errorbar(x,y,yerr=np.vstack([y-lo,hi-y]),label=label,color=color,marker=marker,linestyle=linestyle,markersize=3,capsize=2,capthick=.7)
def panel(ax,letter,title):ax.set_title(f'{letter}  {title}',loc='left',fontweight='bold',pad=7)
def save(fig,name,note):
 fig.text(.015,.008,note,fontsize=6,va='bottom');fig.canvas.draw();renderer=fig.canvas.get_renderer();bad=[]
 for text in fig.findobj(mpl.text.Text):
  if not text.get_visible() or not text.get_text():continue
  box=text.get_window_extent(renderer);fb=fig.bbox
  if box.x0<-.5 or box.y0<-.5 or box.x1>fb.width+.5 or box.y1>fb.height+.5:bad.append(text.get_text())
 fig.savefig(DEST/f'{name}.svg');fig.savefig(DEST/f'{name}.png',dpi=300);fig.savefig(DEST/f'{name}.tiff',dpi=600)
 pdf.savefig(fig);PAGES.append((name,fig));QA.append(dict(figure=name,out_of_page_text=bad,panels=len(fig.axes),minimum_text_pt=min(t.get_fontsize() for t in fig.findobj(mpl.text.Text) if t.get_visible() and t.get_text())))
 im=Image.open(DEST/f'{name}.png');ImageOps.grayscale(im).save(DEST/f'{name}_gray.png')

with PdfPages(OUT/'experiment_figures.pdf') as pdf:
 fig,axes=plt.subplots(3,2,figsize=(7.2,6.6));fig.subplots_adjust(left=.085,right=.985,bottom=.13,top=.94,hspace=.60,wspace=.28)
 for row,q in enumerate([.28,.70,.95]):
  for col,metric in enumerate(['throughput','query_p999_ms']):
   ax=axes[row,col]
   for mode,marker,style,label in [('none','o',':','No checkpoint'),('sync','s','--','Synchronous'),('strict','^','-','Strict')]:
    rs=sorted([r for r in A['concurrency'] if r['group']=='main' and r['query_mix']==q and r['mode']==mode],key=lambda r:r['clients'])
    errorline(ax,[1,8,16],rs,metric,label,COLORS[mode],marker,style)
   panel(ax,chr(97+row*2+col),f'{int(q*100)}% queries');ax.set_xticks([1,8,16]);ax.set_xlabel('Clients');ax.grid(axis='y',alpha=.15)
   if col==0:ax.set_ylabel('Throughput (requests/s)');ax.ticklabel_format(axis='y',style='sci',scilimits=(3,3))
   else:ax.set_ylabel('Query p99.9 (ms)');ax.set_yscale('log');ax.yaxis.set_major_formatter(FuncFormatter(lambda v,pos:f'{v:g}'));ax.yaxis.set_minor_formatter(NullFormatter())
 handles,labels=axes[0,0].get_legend_handles_labels();fig.legend(handles,labels,ncol=3,loc='upper center',bbox_to_anchor=(.52,.995),frameon=False)
 save(fig,'concurrency_closed','Closed-loop saturation; K=500. Median and full range of 3 technical runs. No checkpoint has no recovery-loss guarantee.\nTail latency includes local execution and waits after a worker starts; it omits earlier scheduling delay. Source: concurrency_summary.csv.')
 fig,axes=plt.subplots(1,2,figsize=(7.2,2.9));fig.subplots_adjust(left=.085,right=.985,bottom=.26,top=.82,wspace=.28)
 for i,q in enumerate([.70,.95]):
  ax=axes[i]
  for mode,marker,style,label in [('none','o',':','No checkpoint'),('sync','s','--','Synchronous'),('strict','^','-','Strict')]:
   rs=sorted([r for r in A['paced'] if r['q']==q and r['mode']==mode],key=lambda r:r['rate'])
   errorline(ax,[20,60,100],rs,'query_p99_ms',label,COLORS[mode],marker,style)
  panel(ax,chr(97+i),f'{int(q*100)}% queries, 8 clients');ax.set_yscale('log');ax.yaxis.set_major_formatter(FuncFormatter(lambda v,pos:f'{v:g}'));ax.yaxis.set_minor_formatter(NullFormatter());ax.set_xticks([20,60,100]);ax.set_xlabel('Scheduled arrival rate (thousand requests/s)');ax.set_ylabel('Scheduled-to-completion query p99 (ms)');ax.grid(axis='y',alpha=.15)
 fig.legend(*axes[0].get_legend_handles_labels(),ncol=3,loc='upper center',bbox_to_anchor=(.52,.995),frameon=False)
 save(fig,'concurrency_paced','Median and full range of 3 technical runs; 2 s of arrivals, 1 ms batches, queue capacity 1,024. All requests complete.\nIncludes dispatcher scheduling, backpressure and queue wait; no network and no production SLO claim. Source: paced_summary.csv.')
 fig,axes=plt.subplots(2,3,figsize=(7.2,5.4));fig.subplots_adjust(left=.075,right=.985,bottom=.21,top=.90,hspace=.68,wspace=.29)
 groups=[(['mixed28_unique','mixed70_unique','mixed95_unique','readonly_unique','readonly_aligned'],['28%\nRandom','70%\nRandom','95%\nRandom','RO\nRandom','RO\nAligned'],['fused','cache32']),(['mixed95_hot','readonly_hot','mixed95_optional25_hot'],['95%\nHot','Read-only\nHot','95% hot\n25% cert.'],['fused','cache32','on_demand','cache32_on_demand'])]
 names={'fused':'Fused certificate','cache32':'Fused + cache32','on_demand':'Fused on demand','cache32_on_demand':'Cache32 on demand'};markers={'fused':'o','cache32':'s','on_demand':'^','cache32_on_demand':'D'}
 for j,(b,f,k) in enumerate([(64,8,8),(128,8,8),(128,16,16)]):
  for i,(workloads,labels,variants) in enumerate(groups):
   ax=axes[i,j]
   for vi,v in enumerate(variants):
    rs=[next(r for r in A['cost'] if r['b']==b and r['f']==f and r['k']==k and r['workload']==w and r['variant']==v) for w in workloads]
    x=np.arange(len(workloads))+(vi-(len(variants)-1)/2)*.14
    errorline(ax,x,rs,'ratio_to_reference',names[v],COLORS[v],markers[v],'none')
   ax.axhline(1,color='#888888',ls=':',lw=.8);ax.set_xticks(np.arange(len(workloads)),labels);ax.set_yscale('log');ax.set_ylim((.6,8) if i==0 else (.8,25));ax.set_yticks([1,2,4,8] if i==0 else [1,2,4,8,16]);ax.yaxis.set_major_formatter(FuncFormatter(lambda v,pos:f'{v:g}'));ax.yaxis.set_minor_locator(NullLocator());ax.set_ylabel('Paired throughput / reference');ax.grid(axis='y',alpha=.15);panel(ax,chr(97+i*3+j),f'b={b}, f={f}, k={k}')
 h,l=axes[1,0].get_legend_handles_labels();fig.legend(h,l,ncol=2,loc='upper center',bbox_to_anchor=(.52,.995),frameon=False)
 save(fig,'certificate_execution','Median and full range of 7 paired technical runs per layout; 10,000 requests/run, same trace for all variants; RO = read-only.\nReference computes a certificate for every query. On-demand returns certificates only when requested (25% in the last category).\nCache32 adds an 8 KiB payload reservation; random intervals permit repeats. Source: certificate_cost_summary.csv.')
 fig,axes=plt.subplots(2,3,figsize=(7.2,4.7));fig.subplots_adjust(left=.07,right=.88,bottom=.18,top=.92,hspace=.55,wspace=.30)
 workloads=['stable','dynamic_dominant','critical','held12','held24','held28'];titles=['Stable near','Persistent far','Fast switch','H12','H24','H28'];vals=[r['ratio_to_default_macro_mse'] for r in A['surface']];lo=min(vals);hi=max(vals);norm=TwoSlopeNorm(vmin=min(lo,.99),vcenter=1,vmax=max(hi,1.01))
 for i,(w,title) in enumerate(zip(workloads,titles)):
  ax=axes.flat[i];matrix=np.array([[next(r['ratio_to_default_macro_mse'] for r in A['surface'] if r['workload']==w and r['tau']==tau and r['L']==L) for tau in [.5,1,2,4,8]] for L in [32,128,512]])
  im=ax.imshow(matrix,cmap='coolwarm',norm=norm,aspect='auto');ax.set_xticks(range(5),['0.5','1','2','4','8']);ax.set_yticks(range(3),['32','128','512']);ax.set_xlabel('Kernel bandwidth tau');ax.set_ylabel('Query history length');panel(ax,chr(97+i),title)
  for row in range(3):
   for col in range(5):ax.text(col,row,f'{matrix[row,col]:.2f}',ha='center',va='center',fontsize=6.2,color='black')
 cax=fig.add_axes([.915,.27,.016,.57]);cb=fig.colorbar(im,cax=cax,ticks=[.6,.8,1.,1.2]);cb.set_label('Macro Test MSE / default macro Test MSE')
 save(fig,'sensitivity_surface','All 15 settings at fixed (b,f,k,R)=(64,8,16,4096); default tau=2, history=128. Smaller ratios favor lower error.\nEach cell is a macro mean over 13 entities (12 correlated stations); no confidence interval. Test surface is descriptive, not selection.\nValidation choices were frozen before all tests. Source: sensitivity_surface.csv and sensitivity_all_test.csv.')
 fig,axes=plt.subplots(1,2,figsize=(7.2,3.15));fig.subplots_adjust(left=.09,right=.985,bottom=.28,top=.88,wspace=.28)
 for j,metric in enumerate(['delta_selected_minus_default','delta_selected_minus_recent']):
  ax=axes[j]
  for i,w in enumerate(workloads):
   rs=sorted([r for r in A['selected'] if r['workload']==w],key=lambda r:(r['dataset'],r['entity']));x=np.linspace(i-.18,i+.18,len(rs));y=np.array([r[metric] for r in rs]);ax.scatter(x,y,s=9,c=['#C67535' if r['dataset']=='bike' else '#888888' for r in rs],alpha=.65,zorder=3);ax.scatter(i,float(y.mean()),marker='D',s=23,facecolors='#247F80',edgecolors='white',linewidths=.4,zorder=4)
  ax.axhline(0,color='#777777',ls=':',lw=.8);ax.set_xticks(range(6),['Stable','Far','Switch','H12','H24','H28']);ax.set_ylabel('Paired Test MSE difference');ax.ticklabel_format(axis='y',style='sci',scilimits=(-3,-3));panel(ax,chr(97+j),'Selected minus '+('default online' if j==0 else 'fixed recent'));ax.grid(axis='y',alpha=.15)
 save(fig,'sensitivity_selected','Dots: all 13 entity differences; orange: Bike, gray: correlated stations. Diamond: macro mean, no population CI.\nNegative values favor validation-selected online settings. Both comparators use the same fixed layout; this is not joint layout tuning.\nH24 worsens after validation selection; stable near is unchanged. Source: sensitivity_selected_entities.csv.')
(DEST/'geometry_QA.json').write_text(json.dumps(QA,indent=2)+'\n');print(json.dumps(QA,indent=2))
assert all(not x['out_of_page_text'] and x['minimum_text_pt']>=5 for x in QA)
# A Python-produced contact sheet supports whole-bundle inspection; vector pages remain authoritative.
thumbs=[]
for name,fig in PAGES:
 im=Image.open(DEST/f'{name}.png').convert('RGB');im.thumbnail((850,800));thumbs.append(im)
sheet=Image.new('RGB',(1700,2400),'white')
for i,im in enumerate(thumbs):sheet.paste(im,((i%2)*850,(i//2)*800))
sheet.save(DEST/'contact.png')
