#!/usr/bin/env python3
"""Additional evidence-fault controls on frozen real-JVM semantic captures."""
import argparse
import copy
import json
from pathlib import Path
from infer_distributed_fields import Reconstruction
from run_planned_service import load,save


def audit(root):
    result={}
    for case,mutations in {'catch-unused':['missing-failed-call','wrong-failed-call','wrong-handler'],
                           'overwrite-flag':['missing-target-write','old-return-version']}.items():
        base=root/'semantics-final'/case;capture=base/'capture';rows=[json.loads(x) for x in (capture/'fixture/events.jsonl').read_text().splitlines()]
        wire=next(r for r in rows if r['kind']=='http-json');path=wire['fields'][0]['path']
        for mutation in mutations:
            bad=copy.deepcopy(rows)
            if mutation in ('wrong-failed-call','wrong-handler','missing-failed-call'):
                caught=next(r for r in bad if r['kind']=='collection-catch')
                if mutation=='wrong-failed-call':caught['failed_call_pc']=-1
                elif mutation=='wrong-handler':caught['pc']=-1
                else:
                    victim=next(r for r in reversed(bad[:bad.index(caught)]) if r['kind']=='collection-call-enter' and r['frame']==caught['frame'])
                    bad.remove(victim)
            elif mutation=='missing-target-write':
                victim=next(r for r in bad if r['kind']=='write' and r['field'].endswith('.flag'));bad.remove(victim)
            else:
                ret=next(r for r in bad if r['kind']=='binding-return');ret['fields'][0]['version']-=1
            for seq,r in enumerate(bad,1):r['seq']=seq
            try:
                graph=Reconstruction(base/'build',capture,['fixture'],decoded_rows={'fixture':bad})
                assert not graph.query(wire['message'],path,'fixture')['known'],mutation
            except ValueError:pass
            result[case+'/'+mutation]='rejected or unknown'
    save(root/'additional-refusal-audit.json',{'all_passed':True,'controls':result,'scope':'Perturbed copies only; original captures and frozen algorithm unchanged.'});print(result)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);a=p.parse_args();audit(a.root.resolve())
