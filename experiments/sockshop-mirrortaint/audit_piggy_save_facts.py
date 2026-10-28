#!/usr/bin/env python3
"""Recover already captured pre-save facts, WITHOUT adding any inference/query support."""
import argparse,json
from pathlib import Path
from run_planned_service import load,save,sha
from run_portability_first import TASK_ROOT,verify,log
import portability_piggy_oracle as oracle

def run(root,out):
    verify(root);out.mkdir(parents=True);facts=[]
    for mode in('full','selective'):
        home=root/'tool-runs/piggymetrics-2'/mode/'query-011';capture=home/'capture/events.jsonl';rows=[json.loads(l)for l in capture.open()];cases=load(home/'results.json')['cases'];frames={r['frame']:r for r in rows if r['kind']=='enter'}
        for c in cases:
            if c['http_status']!=200:continue
            ret=[r for r in rows if r['kind']=='binding-return'and r.get('message')==c['message']];assert len(ret)==1;root_frame=ret[0]['frame'];family={root_frame}
            for _ in range(len(frames)):
                before=len(family);family|={f for f,r in frames.items()if r.get('parent')in family}
                if len(family)==before:break
            calls=[r for r in rows if r['kind']=='collection-call-enter'and r['frame']in family and r['callee']=='com/piggymetrics/account/repository/AccountRepository.save(Ljava/lang/Object;)Ljava/lang/Object;'];assert len(calls)==1;call=calls[0];obj=call['args'][0]['object'];assert obj==ret[0]['result']['object'];ends=[r for r in rows if r['kind']=='collection-call-exit'and r['call_id']==call['call_id']];assert len(ends)==1 and ends[0]['result']['object']==obj
            touch=[r for r in rows if r['kind']=='binding-opaque-touch'and r.get('frame')==call['frame']and r.get('callee')==call['callee']and call['seq']<r['seq']<ends[0]['seq']and any(f.get('field')=='com/piggymetrics/account/domain/Account.name'for f in r['fields'])];assert len(touch)==1;event=touch[0];assert event['message']==c['message']
            holder=[r for r in rows if r['kind']=='write'and r.get('owner')==obj and r.get('field')=='com/piggymetrics/account/domain/Account.saving'and r['seq']<call['seq']];assert holder;holder=max(holder,key=lambda r:r['seq']);saving=holder['observed']['object']
            args=[r for r in rows if r['kind']=='binding-input'and r.get('frame')==root_frame and r.get('argument')==0];assert len(args)==1;username=[f for f in args[0]['fields']if f['path']=='/username'];assert len(username)==1
            for f in event['fields']:
                p=f['path'];rule=oracle.return_rule('piggymetrics-2',p);assert rule['source']!='unresolved'
                assert f['owner']==(saving if p.startswith('/saving/')else obj)
                expected=[]
                if rule['source']:expected=[{'event_seq':args[0]['seq'],'message':c['message'],'frame':root_frame,'argument':0,**username[0]}]
                facts.append({'api':'piggymetrics-2','case':c['case'],'kind':'pre-save-argument','mode':mode,'sink':'account-create-save','path':p,'message':c['message'],'call_id':call['call_id'],'call_frame':call['frame'],'call_pc':call['pc'],'snapshot_seq':event['seq'],'save_argument_object':obj,'target_coordinate':{k:f[k]for k in('owner','field','version')},'expected_source_instances':expected,'independent_rule':rule,'TF_state':'target_binding_unsupported','native_sink_instance_export':'absent in first fixed exporter','why_not_a_new_TF_answer':'This audit locates raw pre-call facts and original-code expectations only. Frozen TF has no configured/queryable persistence-sink target; no propagation or graph answer is invented.','raw_capture_sha256':sha(capture)})
    assert len(facts)==72 and sum(bool(f['expected_source_instances'])for f in facts)==8
    summary={'per_mode':{'full':36,'selective':36},'unique_original_case_sink_path_tasks':36,'positive_source_tasks_per_mode':4,'missing_currency_pre_call_projection_per_mode':4,'TF_answer_state':'target_binding_unsupported despite existing raw facts','does_not_change_paired_return_40_scoring':True,'does_not_fill_MT_missing_sink_coordinates':True,'first_captures_unmodified':True}
    save(out/'pre-save-raw-facts.json',facts);save(out/'summary.json',summary);verify(root);log(root,'09-piggy-existing-save-facts',{'summary':str(out/'summary.json'),'sha256':sha(out/'summary.json'),'existing_facts_not_new_answers':True});print(summary)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=TASK_ROOT);p.add_argument('--out',type=Path,required=True);a=p.parse_args();run(a.root.resolve(),a.out.resolve())
