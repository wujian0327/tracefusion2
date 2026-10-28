#!/usr/bin/env python3
"""Current first-pass audit. Does not claim an independent oracle where absent."""
import argparse,collections,datetime,json,shutil,traceback
from pathlib import Path
from run_portability_first import TASK_ROOT,verify,log
from run_planned_service import load,save,sha
from infer_distributed_fields import Reconstruction
from analysis_status import AnalysisLimit

def leaves(value,path):
    parts=path.split('/')[1:]
    def visit(x,at,p):
        if at==len(parts):return[(p,x)]
        part=parts[at]
        if part=='*':
            items=enumerate(x)if isinstance(x,list)else x.items()if isinstance(x,dict)else[]
            return[a for k,v in items for a in visit(v,at+1,p+'/'+str(k))]
        if isinstance(x,dict)and part in x:return visit(x[part],at+1,p+'/'+part)
        if isinstance(x,list)and part.isdigit()and int(part)<len(x):return visit(x[int(part)],at+1,p+'/'+part)
        return[]
    return visit(value,0,'')

def evaluate(root,dest,out):
    run=load(dest/'results.json');mode=run['mode'];api=dest.parent.parent.name
    if mode=='mirrortaint':
        p=dest/'capture/native-capability.jsonl';rows=[json.loads(l)for l in p.read_text().splitlines()]if p.exists()else[]
        return {'api':api,'mode':mode,'run':str(dest.relative_to(root)),'requests':len(run['cases']),'deployment_status':run['status'],'raw_event_counts':dict(collections.Counter(r['kind']for r in rows)),'source_instance_targets_scored':0,'oracle_status':'pending_independent_instance_scoring','adapter_scope':'Frozen exporter exports return objects; void persistence/message sink obligations not exported as complete instance answers. Native source-label export is not itself an independent accuracy score.','capture_sha256':sha(p)if p.exists()else None}
    index=int(dest.name.split('-')[1]);q=load(root/'planning-first'/api/('%03d.json'%index))['query'];plan=root/'planning-first'/api/('%03d-plan.json'%index);role=q['role'];work=out/api/mode/dest.name;build=work/'build'/role;build.mkdir(parents=True);shutil.copyfile(plan,build/'plan.json');shutil.copyfile(root/'metadata'/role/'model.json',build/'model.json');(work/role).symlink_to(dest/'capture',target_is_directory=True)
    result={'api':api,'mode':mode,'query':q,'run':str(dest.relative_to(root)),'requests':len(run['cases']),'target_instances':0,'known_unverified':0,'unknown':0,'evidence_invalid':0,'analysis_limited':0,'N_A_requests':0,'non_2xx_requests':0,'instrumented_business_failure_targets':0,'instrumented_business_failure_requests':0,'oracle_unavailable':0,'exact_verified':None,'wrong_verified':None,'relation_TP_FP_FN':None,'predictions':[]}
    graph=None;invalid=None;limited=None
    try:graph=Reconstruction(work/'build',work,[role])
    except AnalysisLimit as e:limited=str(e)
    except Exception as e:invalid=str(e);(work/'offline-error.txt').write_text(traceback.format_exc())
    result.update(reconstruction_error=invalid,analysis_limit_reason=limited)
    control=load(root/'original/piggymetrics/attempt04-approved8/results.json');controls={(c['api'],c['case']):c for c in control['cases']}
    for case in run['cases']:
        original=controls[(api,case['case'])]
        if not 200<=original.get('http_status',0)<300:result['non_2xx_requests']+=1;continue
        targets=leaves(original['response'],q['path'])
        if case.get('http_status')!=original['http_status']:
            result['instrumented_business_failure_requests']+=1
            result['instrumented_business_failure_targets']+=len(targets)
            result['target_instances']+=len(targets)
            result['oracle_unavailable']+=len(targets)
            for path,value in targets:result['predictions'].append({'case':case['case'],'path':path,'status':'instrumented_business_failure','original_http_status':original['http_status'],'actual_http_status':case.get('http_status'),'reason':'Original response target retained in denominator; tool run changed business completion. Not business N/A.'})
            continue
        if not targets:result['N_A_requests']+=1
        for path,value in targets:
            result['target_instances']+=1;item={'case':case['case'],'path':path,'client_value':value,'message':case['message'],'oracle':'not independently instance-scored; never counted exact'}
            if limited:item.update(status='analysis_limited',reason=limited)
            elif invalid:item.update(status='evidence_invalid',reason=invalid)
            else:
                try:
                    answer=graph.query(case['message'],path,role,boundary=[{'kind':'binding-source'},{'kind':'argument'},{'kind':'http-json','direction':'response','phase':'read'}]);item.update(answer=answer,status='known_unverified'if answer['known']else'unknown')
                except AnalysisLimit as e:item.update(status='analysis_limited',reason=str(e))
                except Exception as e:item.update(status='evidence_invalid',reason=str(e))
            result[item['status']]+=1;result['oracle_unavailable']+=1;result['predictions'].append(item)
    p=dest/'capture/events.jsonl';result['capture_sha256']=sha(p)if p.exists()else None;save(work/'evaluation.json',result);return result

def run(root,out):
    verify(root);out.mkdir(parents=True);items=[]
    for dest in sorted((root/'tool-runs').glob('*/*/*/results.json')):
        try:items.append(evaluate(root,dest.parent,out))
        except Exception as e:items.append({'run':str(dest.parent.relative_to(root)),'audit_error':str(e)})
    snapshot={'at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'core_unchanged':True,'task_seal_sha256':sha(root/'task-seal.json'),'tool_runs_at_snapshot':items,'complete':False,'warning':'Checkpoint only. Native target scoring and independent fine-grained oracles are incomplete. Known_unverified MUST NOT be called correct; no overall accuracy is reported.'}
    save(out/'snapshot.json',snapshot);log(root,'06-current-results-snapshot',{'snapshot':str(out/'snapshot.json'),'sha256':sha(out/'snapshot.json'),'runs':len(items),'first_results_not_complete':True});print({'runs':len(items),'out':str(out)})
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=TASK_ROOT);p.add_argument('--out',type=Path,required=True);a=p.parse_args();run(a.root,a.out)
