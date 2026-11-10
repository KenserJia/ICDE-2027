from pathlib import Path
import json,csv
import numpy as np
import matplotlib as mpl
mpl.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'results/cert_age_slo_20261110'
FIG=ROOT/'paper/figures/cert_age_slo'

def main():
    rows=json.loads((OUT/'LOAD_SUMMARY.json').read_text())
    raw=json.loads((OUT/'load_records.json').read_text())
    assert len(raw)==27 and len(rows)==9
    rates=sorted({x['base'] for x in rows});assert len(rates)==3
    methods=['recent','age','hist'];colors={'recent':'#0072B2','age':'#D55E00','hist':'#666666'}
    labels={'recent':'Recent','age':'Age rollup','hist':'SSE bins'}
    markers={'recent':'o','age':'s','hist':'D'};offset={'recent':-.18,'age':0.,'hist':.18}
    mpl.rcParams.update({'font.family':'sans-serif','font.sans-serif':['DejaVu Sans'],
        'font.size':8,'axes.labelsize':8,'xtick.labelsize':7.5,'ytick.labelsize':7.5,
        'legend.fontsize':8,'axes.spines.top':False,'axes.spines.right':False,
        'axes.linewidth':.7,'svg.fonttype':'none','pdf.fonttype':42,'savefig.dpi':600})
    fig,axes=plt.subplots(1,3,figsize=(7.1,2.25),gridspec_kw={'width_ratios':[1,1.25,1.1]})
    fig.subplots_adjust(left=.065,right=.99,bottom=.28,top=.79,wspace=.45)
    keys=[('G01',100,'Certified queries (%)'),('scheduled_query_p99_ms',1,'Scheduled p99 (ms)'),('timely_goodput_20ms',.001,'Timely certified rate (k/s)')]
    for i,(ax,(key,scale,ylabel)) in enumerate(zip(axes,keys)):
        for method in methods:
            selected=[next(x for x in rows if x['base']==rate and x['method']==method) for rate in rates]
            center=np.array([x['median'][key]*scale for x in selected])
            lower=np.array([x['range'][key][0]*scale for x in selected]);upper=np.array([x['range'][key][1]*scale for x in selected])
            assert np.all(lower<=center) and np.all(center<=upper)
            if key=='scheduled_query_p99_ms' and np.any(lower<=0):
                raise ValueError('p99 range must be strictly positive for logarithmic display')
            x=np.arange(3,dtype=float)+offset[method]
            ax.errorbar(x,center,yerr=np.vstack([center-lower,upper-center]),fmt=markers[method],linestyle='none',color=colors[method],markersize=4,capsize=2,elinewidth=.9,markeredgewidth=.7,label=labels[method])
        ax.set_xticks(range(3),[f'{rate/1000:g}/{4*rate/1000:g}' for rate in rates])
        ax.set_xlim(-.5,2.5);ax.set_xlabel('Load setting: base/burst (k/s)');ax.set_ylabel(ylabel)
        ax.tick_params(width=.7,length=3,pad=2)
        ax.text(0.,1.07,'abc'[i],transform=ax.transAxes,fontsize=10,fontweight='bold',va='bottom')
        if key=='G01':ax.set_ylim(0,100);ax.set_yticks([0,25,50,75,100])
        elif key=='scheduled_query_p99_ms':
            ax.set_yscale('log');ax.axhline(20,color='#333333',linestyle='--',linewidth=.8)
            ax.text(2.43,20,'20 ms',fontsize=7.5,ha='right',va='bottom')
        else:ax.set_ylim(bottom=0)
    handles=[Line2D([],[],color=colors[m],marker=markers[m],linestyle='none',markersize=4,label=labels[m]) for m in methods]
    fig.legend(handles=handles,loc='upper center',bbox_to_anchor=(.52,.99),ncol=3,frameon=False,handletextpad=.5,columnspacing=1.7)
    FIG.mkdir(parents=True,exist_ok=True)
    fig.savefig(FIG/'quality_latency_points.pdf',dpi=600)
    fig.savefig(FIG/'quality_latency_points.svg',dpi=600)
    fig.savefig(FIG/'quality_latency_points.png',dpi=600)
    fig.savefig(FIG/'quality_latency_points.tiff',dpi=600,pil_kwargs={'compression':'tiff_lzw'})
    plt.close(fig)
    qa=dict(backend='python',archetype='quantitative grid',observations_used=len(raw),observations_excluded=0,technical_repeats_per_point=3,center='median',spread='full range',interpolation='none',x_axis='categorical tested base/burst settings; method offsets are visual grouping only',figure_inches=[7.1,2.25],panels=[dict(panel='a',claim='certification fraction',uncertainty='all3 technical repeats'),dict(panel='b',claim='whole-query20ms tail feasibility',uncertainty='all3 technical repeats; positive log axis'),dict(panel='c',claim='individual timely certified completion rate',uncertainty='all3 technical repeats')],rendered_visual_review='pending')
    (OUT/'FIGURE_QA.json').write_text(json.dumps(qa,indent=2)+'\n')
    print('Created paired quality/latency figure from all27 raw runs')
if __name__=='__main__':main()
