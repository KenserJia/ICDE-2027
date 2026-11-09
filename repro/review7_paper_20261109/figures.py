from pathlib import Path
import json,os,hashlib
import numpy as np
os.environ.setdefault('MPLCONFIGDIR','/tmp/review7-paper-mpl')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import NullLocator
R=Path(__file__).resolve().parents[2];O=R/'results/review7_paper_20261109';P=Path(os.environ.get('MTMEM_PAPER_DEST',str(R/'paper/IEEE-conference-template-062824')));D=R/'results/review7_20261109';F=P/'figures'
plt.rcParams.update({'font.family':'sans-serif','font.sans-serif':['Arial','DejaVu Sans'],'font.size':7.1,'axes.spines.top':False,'axes.spines.right':False,'axes.linewidth':.65,'svg.fonttype':'none','pdf.fonttype':42,'legend.frameon':False})
C=['#287c8e','#b17835','#6e6a89'];MARK=['o','s','^'];METHODS=['fused','cache32','histogram'];NAMES=['Fused certificate','Certificate + Cache32','Block V-optimal'];rows=json.loads((D/'performance_records.json').read_text());cost=json.loads((D/'cost_control_records.json').read_text());wide=json.loads((D/'cost_wide_records.json').read_text());sources=[]
fig,axs=plt.subplots(2,2,figsize=(7.16,4.9),layout='constrained');conditions=[(28,'sync'),(28,'strict'),(95,'sync'),(95,'strict')];xt=['28 / sync','28 / strict','95 / sync','95 / strict']
def points(ax,x,vals,color,marker,label=None):
 v=np.asarray(vals);center=np.median(v);ax.errorbar(x,center,yerr=[[center-v.min()],[v.max()-center]],fmt=marker,ms=4,color=color,capsize=2,lw=.8,label=label);ax.scatter(x+np.linspace(-.025,.025,len(v)),v,c=color,s=7,alpha=.65,zorder=3)
for mi,m in enumerate(METHODS):
 for ci,(mix,mode) in enumerate(conditions):
  a=[r for r in rows if (r['method'],r['mix'],r['clients'],r['mode'],r['locality'])==(m,mix,8,mode,'random')];assert len(a)==3
  points(axs[0,0],ci+(mi-1)*.19,[r['throughput_rps']/1000 for r in a],C[mi],MARK[mi],NAMES[mi] if ci==0 else None)
  vals=[r['latencies']['query']['p99_ms'] for r in a];assert np.all(np.asarray(vals)>0)
  points(axs[1,1],ci+(mi-1)*.19,vals,C[mi],MARK[mi]);sources.extend(dict(panel='a,d',method=m,mix=mix,mode=mode,rep=r['rep'],throughput=r['throughput_rps'],query_p99_ms=r['latencies']['query']['p99_ms']) for r in a)
axs[0,0].set_title('a  Joint throughput: eight clients',loc='left');axs[0,0].set_ylabel('Throughput (k requests/s)');axs[0,0].set_xticks(range(4),xt,rotation=15,rotation_mode='anchor',ha='right');axs[0,0].set_ylim(bottom=0)
axs[1,1].set_title('d  Joint query tail: eight clients',loc='left');axs[1,1].set_ylabel('Query p99 (ms)');axs[1,1].set_xticks(range(4),xt,rotation=15,rotation_mode='anchor',ha='right');axs[1,1].set_yscale('log');axs[1,1].set_yticks([.04,.06,.1],['0.04','0.06','0.10']);axs[1,1].yaxis.set_minor_locator(NullLocator())
ax=axs[0,1];ax.axhline(1,c='.5',lw=.6)
for ci,(label,data,mode) in enumerate([('Short / sync',cost,'sync'),('Short / strict',cost,'strict'),('Wide / sync',wide,'sync'),('Wide / strict',wide,'strict')]):
 a={r['rep']:r for r in data if r['method']=='fused' and r['mode']==mode};b={r['rep']:r for r in data if r['method']=='reference' and r['mode']==mode};v=[a[i]['throughput_rps']/b[i]['throughput_rps'] for i in sorted(a)];points(ax,ci,v,C[0],'o');sources.extend(dict(panel='b',condition=label,rep=i,ratio=v[j]) for j,i in enumerate(sorted(a)))
ax.set_xticks(range(4),['Short / sync','Short / strict','Wide / sync','Wide / strict'],rotation=15,rotation_mode='anchor',ha='right');ax.set_ylabel('Fused / reference throughput');ax.set_title('b  Fusion opportunity: 70% queries',loc='left');ax.set_ylim(.85,1.8)
ax=axs[1,0];ax.axhline(1,c='.5',lw=.6)
for mi,m in enumerate(METHODS):
 for ci,mode in enumerate(['sync','strict']):
  a={r['rep']:r for r in rows if (r['method'],r['mix'],r['clients'],r['mode'],r['locality'])==(m,95,8,mode,'hot8')};b={r['rep']:r for r in rows if (r['method'],r['mix'],r['clients'],r['mode'],r['locality'])==(m,95,8,mode,'random')};v=[a[i]['throughput_rps']/b[i]['throughput_rps'] for i in sorted(a)];points(ax,ci+(mi-1)*.19,v,C[mi],MARK[mi]);sources.extend(dict(panel='c',method=m,mode=mode,rep=i,ratio=v[j]) for j,i in enumerate(sorted(a)))
ax.set_xticks(range(2),['Sync','Strict']);ax.set_ylabel('Hotspot / random throughput');ax.set_title('c  Locality: 95% queries, eight clients',loc='left');ax.set_ylim(bottom=0)
for ax in axs.flat:
 ax.grid(axis='y',alpha=.15);ax.title.set_fontsize(8)
h,l=axs[0,0].get_legend_handles_labels();fig.legend(h,l,loc='outside lower center',ncol=3,fontsize=7.1)
fig.savefig(F/'review7_joint_operating.pdf',bbox_inches='tight');fig.savefig(F/'review7_joint_operating.svg',bbox_inches='tight');fig.savefig(F/'review7_joint_operating.png',dpi=600,bbox_inches='tight');plt.close(fig)
(O/'joint_figure_source.json').write_text(json.dumps(sources,indent=2)+'\n')
# Reuse the established vector diagram; change only the joint-state semantics.
s=(R/'repro/framework_20261109/draw.py').read_text()
s=s.replace("ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'paper/IEEE-conference-template-062824/figures/framework_20261109';QA=ROOT/'results/framework_20261109'",f"ROOT=Path({str(R)!r});OUT=Path({str(F/'review7_framework')!r});QA=Path({str(O/'framework_QA')!r});OUT.mkdir(exist_ok=True);QA.mkdir(exist_ok=True)")
s=s.replace('Accounted native service state','Accounted joint service state').replace('纳入资源核算的原生服务状态','纳入资源核算的联合服务状态')
s=s.replace("('Certificate extension','误差证书扩展')","('Certificate state','误差证书状态')").replace('Rounding allowance F\\n\\nSeparate evaluation','Arithmetic allowance F\\n\\nJoint checkpoint').replace('数值误差余量 F\\n\\n单独评估','数值误差余量 F\\n\\n联合检查点')
s=s.replace('Solid: native service paths. Dashed: separately evaluated certificate augmentation.','Solid: service execution. Dashed: certificate-to-cell associations in joint state.').replace('实线：原生服务路径。虚线：单独评估的误差证书扩展。','实线：服务执行路径。虚线：联合状态中的证书与单元关联。')
s=s.replace('Value / status\\nPrefix / source\\nResolution','Value / status / T\\nPrefix / source\\nResolution')
s=s.replace("for lang in ['en','zh']:draw(lang)","for lang in ['en']:draw(lang)")
(O/'framework_draw.py').write_text(s)
exec(compile(s,str(O/'framework_draw.py'),'exec'),{'__file__':str(O/'framework_draw.py')})
print('Figure source records',len(sources))
