#!/usr/bin/env python3
"""Standalone Cart cost figure: raw deployment points and medians, no CIs."""
import argparse,json,os
from pathlib import Path
os.environ.setdefault('MPLCONFIGDIR','/tmp/tracefusion2-matplotlib')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from run_planned_service import load,save,sha


def plot(root):
    a=load(root/'cost-audit.json');assert a['all_passed'];out=root/'figures';out.mkdir(exist_ok=False)
    plt.rcParams.update({'font.size':9,'svg.fonttype':'none'})
    fig,axes=plt.subplots(2,2,figsize=(10.6,7.2),layout='constrained');colors={'original':'#8a8f98','full_legacy':'#c77c3b','full':'#4c78a8','selective_base':'#72b7b2','selective':'#2a9d62'};labels={'original':'Original','full_legacy':'Full +\nextra audit','full':'Clean\nfull','selective_base':'Selective\nbase','selective':'Selective\ntarget'}
    configs=[('p95_ms','Online p95 (ms)',1,True),('online_cpu_percent','JVM CPU (% of one core)',1,True),('capture_bytes','Measured-request evidence (MiB)',2**20,False),('offline_core_seconds','Whole-batch offline core (s)',1,False)]
    for ax,(metric,title,scale,include_original)in zip(axes.flat,configs):
        arms=list(colors)if include_original else list(colors)[1:]
        for i,arm in enumerate(arms):
            vals=[v[metric]/scale for _,v in sorted(a['trials'][arm].items())];median=a['summary'][arm][metric]['median']/scale
            ax.bar(i,median,color=colors[arm],alpha=.28,width=.65);ax.scatter([i+x for x in (-.12,-.06,0,.06,.12)],vals,color=colors[arm],s=23,zorder=3);ax.plot([i-.23,i+.23],[median,median],color='#222222',linewidth=1.6,zorder=4)
        ax.set_xticks(range(len(arms)),[labels[v]for v in arms]);ax.set_title(title,loc='left',fontweight='bold');ax.set_ylim(bottom=0);ax.grid(axis='y',alpha=.18);ax.set_axisbelow(True)
    fig.suptitle('Cart: shared cleanup separated from query output projection',fontweight='bold');fig.supxlabel('Five independent deployments per configuration; dots = deployments, line = median. Fixed 2 requests/s.\nOffline includes warmup/setup batch evidence; original provides no provenance.',fontsize=8)
    fig.savefig(out/'cart-transport-ablation.png',dpi=180);raw=out/'cart-transport-ablation-raw.svg';fig.savefig(raw);plt.close(fig)
    import xml.etree.ElementTree as ET
    def text(s):return s if s and s.strip()else ''
    def normalized(e):return(e.tag,sorted(e.attrib.items()),text(e.text),text(e.tail),tuple(normalized(c)for c in e))
    tree=ET.parse(raw);before=normalized(tree.getroot());ET.register_namespace('','http://www.w3.org/2000/svg');ET.register_namespace('xlink','http://www.w3.org/1999/xlink');ET.indent(tree,space='')
    cleaned=out/'cart-transport-ablation.svg';tree.write(cleaned,encoding='utf-8',xml_declaration=True)
    with cleaned.open('a')as f:f.write('\n')
    assert before==normalized(ET.parse(cleaned).getroot())
    save(out/'sources.json',{'audit_sha256':sha(root/'cost-audit.json'),'source_sha256':sha(Path(__file__)),'raw_svg_sha256':sha(raw),'delivery_svg_sha256':sha(cleaned),'SVG_XML_semantics_preserved':True,'statistics':'Raw five-deployment points and median; no confidence-interval or significance claim.'})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);plot(p.parse_args().root.resolve())
