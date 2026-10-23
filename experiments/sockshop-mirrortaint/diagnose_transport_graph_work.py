#!/usr/bin/env python3
"""Count persisted graph work from completed captures, without timing a rerun."""
import argparse,statistics
from pathlib import Path
from collections import Counter
from run_planned_service import load,save,sha
from infer_response_binding import matches


def run(root):
    assert load(root/'pipeline-complete.json')['all_passed']
    config=load(root/'config.json');records={}
    for job in config['order']:
        if job['mode']=='original':continue
        d=root/'deployments'/job['name'];graph=load(d/'field-graph.json');plan=load(root/'builds'/job['arm']/'carts/plan.json');pattern=plan['response_binding']['path']
        kinds=Counter(n['kind']for n in graph['nodes']);writes=[n for n in graph['nodes']if n['kind']=='http-json'and n.get('phase')=='write'and n.get('direction')=='response']
        rows={'nodes':len(graph['nodes']),'edges':len(graph['edges']),'http_json_nodes':kinds['http-json'],'source_boundary_nodes':kinds['binding-source'],'execution_result_nodes':kinds['bytecode-execution'],'response_target_nodes':sum(matches(pattern,n['path'])for n in writes),'response_other_nodes':sum(not matches(pattern,n['path'])for n in writes)}
        records.setdefault(job['arm'],{})[job['name'][:8]]=rows
    medians={arm:{k:statistics.median(v[k]for v in records[arm].values())for k in next(iter(records[arm].values()))}for arm in records}
    for repeat,a in records['full'].items():
        b=records['selective'][repeat];base=records['selective_base'][repeat]
        for key in ('edges','source_boundary_nodes','execution_result_nodes','response_target_nodes'):assert a[key]==b[key]==base[key]
        assert b['response_other_nodes']<a['response_other_nodes']
        assert a['nodes']-b['nodes']==a['response_other_nodes']-b['response_other_nodes']
    save(root/'graph-work-audit.json',{'all_passed':True,'records':records,'medians':medians,'script_sha256':sha(Path(__file__)),'cost_audit_sha256':sha(root/'cost-audit.json'),'scope':'Whole captured graph including setup and warmup; not additional correctness targets. Counts only; no new timing or exclusive causal attribution. The current alias implementation repeatedly scans binding-return records for non-target serialized fields.'})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);run(p.parse_args().root.resolve())
