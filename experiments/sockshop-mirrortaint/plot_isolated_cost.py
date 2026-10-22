#!/usr/bin/env python3
"""Export five paired deployment ratios and medians; no invented intervals."""
import argparse
import csv
import json
from pathlib import Path
import hashlib


def plot(root):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    data=json.loads((root/'cost-audit.json').read_text());assert data['all_passed']
    out=root/'figures';out.mkdir();rows=[]
    panels=[('cart','Cart: execution kernel'),('train','Train: return forwarding'),('price','Price: collection fast path')]
    specs=[('online-overhead','selective/original',[('p95_ms','p95 latency'),('online_cpu_percent','JVM CPU'),('online_rss_mean_bytes','Mean RSS')]),
           ('observation-benefit','selective/full',[('capture_events','Records'),('capture_bytes','Bytes'),('offline_core_seconds','Offline core'),('offline_child_peak_rss_bytes','Offline RSS')])]
    plt.rcParams.update({'font.size':10,'svg.fonttype':'none','axes.spines.top':False,'axes.spines.right':False})
    for name,comparison,metrics in specs:
        fig,axes=plt.subplots(1,3,figsize=(11.5,3.5),sharey=True,layout='constrained')
        maxima=[];minima=[]
        for ax,(kind,title) in zip(axes,panels):
            ax.axhline(1,color='#555555',linestyle='--',linewidth=1)
            for i,(key,label) in enumerate(metrics):
                p=data['results'][kind]['paired'][comparison][key];ys=p['ratios'];maxima.extend(ys);minima.extend(ys)
                assert len(ys)==5
                ax.scatter([i+(j-2)*.055 for j in range(5)],ys,color='#1967a3',s=23,zorder=3)
                ax.plot([i-.22,i+.22],[p['median']]*2,color='#111111',linewidth=2,zorder=4)
                rows.extend({'figure':name,'kind':kind,'comparison':comparison,'metric':key,'round':j+1,'ratio':v,'median_ratio':p['median']} for j,v in enumerate(ys))
            ax.set_title(title);ax.set_xticks(range(len(metrics)),[label for _,label in metrics],rotation=20,ha='right');ax.grid(axis='y',alpha=.2)
        lo=min(.95,min(minima))*.9;hi=max(1.05,max(maxima))*1.07
        axes[0].set_ylim(max(0,lo),hi);axes[0].set_ylabel(comparison+' ratio (lower is better)')
        fig.suptitle('Five matched deployment pairs; dots = rounds, black bars = medians',fontsize=11)
        for ext in ('svg','png'):fig.savefig(out/('isolated-cost-20261022-'+name+'.'+ext),dpi=220)
        plt.close(fig)
    with (out/'paired-ratios.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,list(rows[0]),lineterminator='\n');writer.writeheader();writer.writerows(rows)
    (out/'source.json').write_text(json.dumps({'source':'../cost-audit.json','source_sha256':hashlib.sha256((root/'cost-audit.json').read_bytes()).hexdigest(),'points':'five independent matched deployment pairs per task','intervals':'none; all points displayed','online_comparison':'selective/original','observation_comparison':'selective/full','author_source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);plot(p.parse_args().root.resolve())
