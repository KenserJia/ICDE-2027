from pathlib import Path
import os,json,hashlib
os.environ.setdefault('MPLCONFIGDIR','/tmp/framework-mpl')
import matplotlib as mpl
mpl.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle,FancyArrowPatch
from matplotlib.font_manager import FontProperties
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'paper/IEEE-conference-template-062824/figures/framework_20261109';QA=ROOT/'results/framework_20261109'
mpl.rcParams.update({'font.family':'sans-serif','font.sans-serif':['Arial','DejaVu Sans'],'font.size':7.4,'pdf.fonttype':42,'svg.fonttype':'none','axes.linewidth':.8})
INK='#344A5C';BLUE='#507A9B';BORDER='#8D9CA8';PALE='#EBF2F7';GRAY='#F3F5F6';WHITE='#FFFFFF'
FONTS={'en':FontProperties(family='DejaVu Sans'),'zh':FontProperties(family='DejaVu Sans')}
STR={
 'title':('MT-Memory: coverage-preserving history and local recovery','MT-Memory：覆盖保持的历史状态与本地恢复'),
 'a':('a  Requests, admission and ingestion','a  请求输入、修改准入与历史写入'),
 'b':('b  Accounted native service state','b  纳入资源核算的原生服务状态'),
 'c':('c  Persistence and query readout','c  一致检查点与联合查询读出'),
 'obs':('Observations','历史观测'), 'put':('Fact put / overwrite','事实写入／覆盖更新'), 'delete':('Fact deletes','事实删除'),
 'dispatch':('Request dispatch','请求分派'), 'dispatchbody':('Observations / facts\nTyped mutations','区分观测与事实修改\n类型化输入'),
 'gate':('Mutation admission','修改准入'), 'gatebody':('a: counted mutations\nAdmit while a − p < K\nWait at the boundary','a：已计数修改前缀\na − p < K 时准入\n达到边界后等待'),
 'ingest':('History ingestion','历史写入'), 'ingestbody':('Update active fine cells\nSeal the coarse aggregate\nConsider a fine overlay','更新活动细单元\n封闭时写入粗摘要\n按策略保留精细层'),
 'factlabel':('Facts','事实'), 'historylabel':('Observations','观测'),
 'manager':('Bounded state\nmanager','有界状态管理'), 'managerbody':('Budget accounting\nRetention scores\nSeal / replace\nReclaim segments\nKeep base coverage','容量与预算核算\n近期／延迟需求评分\n建段、替换与回收\n保持粗层覆盖'),
 'facts':('Exact current facts','精确当前事实'), 'factsbody':('Latest values\nVersions and tombstones\nBounded key catalog','最新值\n版本与删除标记\n有界键目录'),
 'lock':('One local prefix\nOne service lock','同一本地前缀\n同一服务锁'),
 'active':('Active segment: fine SUM / COUNT over populated cells','活动分段：按实际填充区间维护细粒度 SUM／COUNT'),
 'coarse':('Mandatory coarse ring','必需的粗历史环'), 'coarsedesc':('Coarse width b; declared reach R','粗单元宽度 b；声明历史范围 R'),
 'fine':('Replaceable fine overlays','可替换精细覆盖层'), 'finedesc':('Fine width f; at most k overlays','细单元宽度 f；最多 k 个覆盖层'),
 'id':('Absolute segment ID','绝对分段标识'), 'sum':('SUM','SUM'), 'count':('COUNT','COUNT'),
 'coarsebottom':('Coverage survives fine eviction','移除精细层后仍保留覆盖'), 'finebottom':('Recent / delay-directed policy','近期保留／查询延迟驱动保留'),
 'seal':('Seal','封闭'), 'admit':('Retain','保留'),
 'metadata':('Bounded query history | segment identities | versions | policy state','有界查询历史｜分段标识｜版本｜保留策略状态'),
 'ledger':('Managed ledger: resident state + metadata + image reserves + workspace','资源账本：驻留状态＋元数据＋镜像预留＋工作区'),
 'cert':('Certificate extension','误差证书扩展'), 'certbody':('Append-only history\n\nCell min / max\nAnalytical bound B\nRounding allowance F\n\nSeparate evaluation','仅追加历史\n\n单元最小／最大值\n解析误差界 B\n数值误差余量 F\n\n单独评估'),
 'persistnote':('Persistence\nCapture and restore\none coherent prefix','持久化\n捕获与恢复\n同一完整前缀'),
 'assumption':('Recovery assumption\nLatest completed\nimage remains valid','恢复前提\n最新完成的镜像\n保持有效'),
 'checkpoint':('Checkpoint coordinator','检查点协调器'), 'checkpointbody':('Capture prefix q, then persist\nAdvance durable p only after commit','捕获前缀 q 后持久化\n提交完成后才推进持久前缀 p'),
 'disk':('Two-slot persistent image','双槽持久镜像'), 'diskbody':('Generation, length and checksums\nRecover the newest valid prefix p','代际、长度与校验和\n恢复最新有效前缀 p'),
 'readout':('Versioned query readout','带版本的查询读出'), 'readoutbody':('Facts + finest retained history\nEXACT / APPROX / UNKNOWN','事实＋可用的最细历史\nEXACT／APPROX／UNKNOWN'),
 'query':('Range query','范围查询'), 'querybody':('Key; delay d\nWidth w','键；延迟 d\n宽度 w'), 'result':('Query result','查询结果'), 'resultbody':('Value / status\nPrefix / source\nResolution','值与状态\n前缀与来源\n分辨率'),
 'capture':('Capture / restore','捕获／恢复'), 'read':('Locked read','加锁读取'),
 'footer':('Solid: native service paths. Dashed: separately evaluated certificate augmentation.','实线：原生服务路径。虚线：单独评估的误差证书扩展。')}

def draw(lang):
 fig=plt.figure(figsize=(7.2,8.35));ax=fig.add_axes([0,0,1,1]);ax.set_xlim(0,14.4);ax.set_ylim(0,17.2);ax.axis('off');texts=[];boxes=[];segments=[]
 fp=FONTS[lang]
 def val(key):return STR[key][lang=='zh']
 def text(x,y,s,fs=7.4,ha='center',weight='normal',color=INK,container=None):
  t=ax.text(x,y,s,fontsize=fs,fontproperties=fp,ha=ha,va='center',color=color,weight=weight,linespacing=1.45,zorder=5);texts.append((t,container));return t
 def label(x,y,key,**kw):return text(x,y,val(key),**kw)
 def box(x,y,w,h,fill=WHITE,edge=BORDER,dashed=False):
  ax.add_patch(Rectangle((x,y),w,h,facecolor=fill,edgecolor=edge,linewidth=.9,linestyle=(0,(3,2)) if dashed else '-',zorder=2));bounds=(x,y,x+w,y+h);boxes.append(bounds);return bounds
 def arrow(points,color=INK,dashed=False,bidir=False,head=True):
  # Orthogonal native flow; dashed strokes only associate the separate variant.
  for a,b in zip(points[:-2],points[1:-1]):ax.plot([a[0],b[0]],[a[1],b[1]],color=color,lw=.8,ls='--' if dashed else '-',zorder=3)
  if head:
   a,b=points[-2:];p=FancyArrowPatch(a,b,arrowstyle='<->' if bidir else '-|>',mutation_scale=7,linewidth=.8,color=color,linestyle='--' if dashed else '-',shrinkA=0,shrinkB=0,zorder=3);ax.add_patch(p)
  else:
   a,b=points[-2:];ax.plot([a[0],b[0]],[a[1],b[1]],color=color,lw=.8,ls='--' if dashed else '-',zorder=3)
  segments.append(points)
 label(.35,16.85,'title',fs=10,ha='left');ax.plot([.35,14.05],[16.57,16.57],color=BORDER,lw=.8)
 label(.35,16.22,'a',fs=8.4,ha='left',weight='bold')
 for y,key in [(14.95,'obs'),(13.75,'put'),(12.55,'delete')]:
  b=box(.35,y,2.15,.8);label(1.425,y+.4,key,fs=7.7,container=b)
 # Merge counted mutation inputs before admission. Queries enter independently below.
 ax.plot([2.88,2.88],[12.95,15.35],color=INK,lw=.8,zorder=3)
 for y in [15.35,14.15,12.95]:arrow([(2.5,y),(2.88,y)],head=False)
 arrow([(2.88,14.7),(3.45,14.7)])
 b=box(3.45,13.65,2.35,2.1,PALE,BLUE);label(4.625,15.25,'dispatch',fs=8.2,weight='bold',container=b);label(4.625,14.45,'dispatchbody',fs=7.1,container=b)
 arrow([(5.8,14.7),(6.35,14.7)])
 b=box(6.35,13.65,3.2,2.1,PALE,BLUE);label(7.95,15.25,'gate',fs=8.2,weight='bold',container=b);label(7.95,14.35,'gatebody',fs=7.4,container=b)
 arrow([(9.55,14.7),(10.2,14.7)]);text(9.875,14.95,'Obs.' if lang=='en' else '观测',fs=7)
 b=box(10.2,13.65,3.55,2.1);label(11.975,15.25,'ingest',fs=8.2,weight='bold',container=b);label(11.975,14.35,'ingestbody',fs=7.4,container=b)
 # Native boundary contains facts, history, active state and bounded control data.
 box(3.05,4.85,10.98,7.75,fill='#FAFCFE',edge=BLUE)
 b=box(3.35,9.1,2.45,3.15);label(4.575,11.87,'facts',fs=8.2,weight='bold',container=b);label(4.575,10.65,'factsbody',fs=7.4,container=b)
 b=box(3.35,7.9,2.45,.75);label(4.575,8.275,'lock',fs=7.3,container=b)
 arrow([(7.4,13.65),(7.4,13.1),(4.575,13.1),(4.575,12.25)]);label(4.95,12.92,'factlabel',fs=7,ha='left')
 b=box(6.2,11.5,7.55,.75,PALE,BLUE);label(9.975,11.875,'active',fs=7.7,container=b)
 arrow([(11.975,13.65),(11.975,12.25)]);label(12.2,12.93,'historylabel',fs=7,ha='left')
 for x,w,kind in [(6.2,3.7,'coarse'),(10.3,3.45,'fine')]:
  b=box(x,7.9,w,3.2,GRAY);label(x+w/2,10.8,kind,fs=8.2,weight='bold',container=b);label(x+w/2,10.4,kind+'desc',fs=7.1,color=BLUE,container=b)
  q=box(x+.2,9.83,w-.4,.4);label(x+w/2,10.03,'id',fs=7.1,container=q)
  half=(w-.65)/2
  for j,key in enumerate(['sum','count']):
   q=box(x+.2+j*(half+.25),8.93,half,.67,PALE,BLUE);label(x+.2+j*(half+.25)+half/2,9.265,key,fs=7.8,container=q)
  q=box(x+.2,8.15,w-.4,.45);label(x+w/2,8.375,kind+'bottom',fs=7,container=q)
 arrow([(8.05,11.5),(8.05,11.1)]);label(8.23,11.3,'seal',fs=7,ha='left')
 arrow([(12.025,11.5),(12.025,11.1)]);label(12.2,11.3,'admit',fs=7,ha='left')
 # Capacity and retention manager: native control, no learned encoder assumptions.
 b=box(.35,8.75,2.15,3.5,PALE,BLUE);label(1.425,11.65,'manager',fs=7.7,weight='bold',container=b);label(1.425,10.2,'managerbody',fs=7.1,container=b);arrow([(2.5,10.5),(3.05,10.5)],color=BLUE)
 # A separate certificate variant associates extrema with retained cells.
 b=box(.35,5.1,2.15,3.05,fill=WHITE,edge=BLUE,dashed=True);label(1.425,7.78,'cert',fs=7.6,weight='bold',color=BLUE,container=b);label(1.425,6.45,'certbody',fs=7,container=b)
 arrow([(2.5,7.45),(2.85,7.45),(2.85,7.65),(8.05,7.65),(8.05,7.9)],color=BLUE,dashed=True,head=False)
 arrow([(8.05,7.65),(12.025,7.65),(12.025,7.9)],color=BLUE,dashed=True,head=False)
 b=box(3.35,6.5,10.1,.65);label(8.4,6.825,'metadata',fs=7.4,container=b)
 b=box(3.35,5.6,10.1,.65);label(8.4,5.925,'ledger',fs=7.3,container=b)
 label(3.3,5.12,'b',fs=8.3,ha='left',weight='bold',color=BLUE)
 # Lower strip mirrors the reference's persistence / readout arrangement.
 box(.35,.55,13.68,3.85,GRAY);label(.55,4.1,'c',fs=8.2,weight='bold',ha='left')
 label(.6,3.05,'persistnote',fs=7.3,ha='left');label(.6,1.65,'assumption',fs=7.1,ha='left')
 b=box(3.35,2.65,4.3,1.15,PALE,BLUE);label(5.5,3.52,'checkpoint',fs=8,weight='bold',container=b);label(5.5,3.04,'checkpointbody',fs=7.1,container=b)
 arrow([(5.5,4.85),(5.5,3.8)],bidir=True);label(5.68,4.64,'capture',fs=7,ha='left')
 b=box(3.35,.9,4.3,1.1);label(5.5,1.76,'disk',fs=8,weight='bold',container=b);label(5.5,1.24,'diskbody',fs=7.1,container=b)
 arrow([(5.5,2.65),(5.5,2.0)],bidir=True)
 b=box(10.1,2.65,3.65,1.15);label(11.925,3.52,'readout',fs=8,weight='bold',container=b);label(11.925,3.04,'readoutbody',fs=7,container=b)
 arrow([(11.925,4.85),(11.925,3.8)]);label(12.1,4.64,'read',fs=7,ha='left')
 for x,w,key,body in [(10.1,1.7,'query','querybody'),(12.05,1.7,'result','resultbody')]:
  b=box(x,.7,w,1.4);label(x+w/2,1.87,key,fs=7.6,weight='bold',container=b);label(x+w/2,1.25,body,fs=7 if lang=='zh' else 6.8,container=b)
 arrow([(10.95,2.1),(10.95,2.65)]);arrow([(12.9,2.65),(12.9,2.1)])
 label(.35,.22,'footer',fs=7,ha='left')
 # Accommodate portable font metrics without changing diagram wording or boxes.
 for _ in range(5):
  fig.canvas.draw();renderer=fig.canvas.get_renderer()
  for t,b in texts:
   if not b:continue
   bb=t.get_window_extent(renderer)
   lo,hi=ax.transData.transform([[b[0]+.05,b[1]+.05],[b[2]-.05,b[3]-.05]])
   factor=min(1.,(hi[0]-lo[0])/bb.width,(hi[1]-lo[1])/bb.height)
   if factor<1:t.set_fontsize(t.get_fontsize()*factor*.99)
 fig.canvas.draw();renderer=fig.canvas.get_renderer();bad=[]
 for t,b in texts:
  bb=t.get_window_extent(renderer);xy=ax.transData.inverted().transform([[bb.x0,bb.y0],[bb.x1,bb.y1]])
  if b and (xy[0,0]<b[0]+.035 or xy[1,0]>b[2]-.035 or xy[0,1]<b[1]+.035 or xy[1,1]>b[3]-.035):bad.append(dict(text=t.get_text(),bounds=b,text_bounds=xy.tolist()))
  if bb.x0<0 or bb.y0<0 or bb.x1>fig.bbox.width or bb.y1>fig.bbox.height:bad.append(dict(outside_canvas=t.get_text()))
 prefix=OUT/f'mtmemory_framework_{lang}'
 fig.savefig(str(prefix)+'.pdf');fig.savefig(str(prefix)+'.svg');fig.savefig(str(prefix)+'.png',dpi=300);fig.savefig(str(prefix)+'.tiff',dpi=600,pil_kwargs={'compression':'tiff_lzw'})
 # Python-only grayscale QA render.
 for patch in ax.patches:
  from matplotlib.colors import to_rgba
  for name in ['facecolor','edgecolor']:
   c=getattr(patch,'get_'+name)();lum=.2126*c[0]+.7152*c[1]+.0722*c[2];getattr(patch,'set_'+name)((lum,lum,lum,c[3]))
 for t,_ in texts:t.set_color('#303030')
 for line in ax.lines:line.set_color('#666666')
 fig.savefig(QA/f'grayscale_{lang}.png',dpi=300);plt.close(fig)
 (QA/f'geometry_{lang}.json').write_text(json.dumps(dict(language=lang,boxes=len(boxes),texts=len(texts),segments=len(segments),font_min_pt=min(t.get_fontsize() for t,_ in texts),out_of_box=bad),ensure_ascii=False,indent=2)+'\n')
 print(lang,'geometry issues',bad,flush=True)
for lang in ['en']:draw(lang)
