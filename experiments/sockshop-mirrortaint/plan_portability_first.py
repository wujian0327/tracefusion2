#!/usr/bin/env python3
"""Run unmodified frozen routing on every expressible sealed target, no success filtering."""
import argparse,time,traceback
from pathlib import Path
from run_portability_first import TASK_ROOT,verify,log
from run_planned_service import load,save,sha
from plan_capability_policy import choose

def run(root):
    verify(root);seal=root/'task-seal.json';tasks=load(seal);out=root/'planning-first';out.mkdir(exist_ok=True)
    for q in tasks['entries']:
        dest=out/q['id'];dest.mkdir(exist_ok=True);model=load(root/'metadata'/q['role']/'model.json');rows=[]
        for index,target in enumerate(q['return_targets']):
            path=dest/('%03d.json'%index)
            if path.exists():rows.append(load(path));continue
            started=time.monotonic();r={'api':q['id'],'index':index,'query':{'id':q['id']+'-'+str(index),'entry':q['entry'],'target':target['target'],'path':target['path'],'role':q['role'],'application':q['application']},'target_metadata':target,'task_seal_sha256':sha(seal),'evidence':'Static planning only; NOT an end-to-end answer or runtime execution'}
            if not target['target']:r.update(status='target_binding_unsupported',reason=target['binding'])
            else:
                try:
                    plan,route=choose(model,r['query']);save(dest/('%03d-plan.json'%index),plan);r.update(status='accepted',route=route,profile=plan['profile'],plan_sha256=sha(dest/('%03d-plan.json'%index)))
                except Exception as e:r.update(status='rejected',reason=str(e),exception_type=type(e).__name__)
            r['planning_wall_seconds']=time.monotonic()-started;save(path,r);rows.append(r);print(q['id'],index,r['status'],r.get('reason','')[:160],flush=True)
        save(dest/'summary.json',{'api':q['id'],'rows':rows,'effect_sink_count':len(q['effect_sink_candidates']),'effect_sink_state':'not_expressible_by_frozen_HTTP_response_target_interface'if q['effect_sink_candidates']else'none_statically_discovered','void_is_not_business_NA':True})
    verify(root);log(root,'05-static-first-plans',{'task_seal_sha256':sha(seal),'all_40_preserved':True,'core_unchanged':True})
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=TASK_ROOT);a=p.parse_args();run(a.root)
