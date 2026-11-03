"""Original common denominator; raw-coordinate oracle independent of answers."""
import argparse
import csv
import json
from pathlib import Path
from collections import Counter
from run_planned_service import ROOT,load,save,sha
from run_target_external_first import HOME,FINAL,OUT,verify


def selected(value,pattern):
    def walk(v,parts,path):
        if not parts:
            return [(path or '/',v)]if not isinstance(v,(list,dict))else[]
        key,*tail=parts
        if key=='*'and isinstance(v,list):return [leaf for i,item in enumerate(v)for leaf in walk(item,tail,path+'/'+str(i))]
        if isinstance(v,dict)and key in v:return walk(v[key],tail,path+'/'+key)
        return []
    return walk(value,pattern.strip('/').split('/')if pattern!='/'else[], '')


def unresolved_output_obligations(case,pattern):
    result=[];value=case['response'];path=''
    for part in pattern.strip('/').split('/'):
        if part=='*'or not isinstance(value,dict)or part not in value:break
        value=value[part];path+='/'+part
        if value is None:
            if path!=pattern:result.append({'path':path,'kind':'actual_null_ancestor','state':'target_interface_and_oracle_unresolved',
                'reason':'Actual null field remains an obligation; no member target and no empty-source guess.'})
            break
    if case['http_status']>=400 or isinstance(case['response'],dict)and case['response'].get('code',200)!=200:
        result.append({'kind':'original_business_failure_or_handler_output','http_status':case['http_status'],
            'state':'outside_selected_normal_field_scope','reason':'Preserved separately, not counted as answered or business N/A.'})
    return result


def audit(out):
    verify();assert load(OUT/'matrix-progress.json')['complete'];out.mkdir(parents=True,exist_ok=False)
    protocol=load(OUT/'task-seal.json');records=[];apis=[]
    import external_transfer_oracle as raw
    from run_mirror_capability_probe import read_events,native_answer
    from native_source_protocol import validate as validate_native
    from infer_distributed_fields import Reconstruction
    for app,tasks in protocol['tasks'].items():
        original=load(HOME/('ruoyi-original-03'if app=='ruoyi'else'teastore-original-02')/'sealed-original-requests/results.json')['cases']
        for q in tasks:
            qid=q['id'];pattern=q['target'].split('@')[-1]if'@'in q['target']else'/'
            expected_cases=[r for r in original if r['query']==qid];assert len(expected_cases)==6
            denominator=[(c,path,value)for c in expected_cases for path,value in selected(c['response'],pattern)]
            # HTTP/handler and no-selected-leaf obligations never become answers.
            api={'query':qid,'application':app,'selected_original_targets':len(denominator),
                 'original_requests':6,'no_selected_target_requests':sum(not selected(c['response'],pattern)for c in expected_cases),
                 'normal_source_boundary':q['source_calls'],'tools':{}}
            api['additional_output_obligations']=[{'case':c['case'],**o}for c in expected_cases for o in unresolved_output_obligations(c,pattern)]
            for mode in ('full','selective','mirrortaint'):
                dest=OUT/'runs'/qid/mode;plan_result=load(OUT/'plans'/qid/'result.json')
                rows=[];wire=[];graph=None;error=None;actual=[];source_complete=False;index=None
                if(dest/'result.json').exists():
                    run=load(dest/'result.json');actual=run['cases'];initial=run['state']
                    try:
                        if initial!='captured':raise ValueError(run.get('error','environment failed'))
                        if mode=='mirrortaint':
                            view=out/(qid+'-native-view');view.mkdir();(view/'role').symlink_to((dest/'capture').resolve(),target_is_directory=True)
                            rows=read_events(view,'role');validate_native(rows);source_complete=True
                            wire=raw.raw(dest/'capture/instances.jsonl')
                        else:
                            rows=raw.raw(dest/'capture/events.jsonl');raw.require_complete_raw_capture(rows)
                            b=out/(qid+'-'+mode)/'build/role';b.mkdir(parents=True);(b/'plan.json').write_bytes((OUT/'plans'/qid/'plan.json').read_bytes())
                            cap=b.parents[1]/'capture/role';cap.mkdir(parents=True);(cap/'events.jsonl').symlink_to((dest/'capture/events.jsonl').resolve())
                            graph=Reconstruction(b.parent,cap.parent,['role'],decoded_rows={'role':rows})
                            index=raw.RawFactIndex(rows)
                    except Exception as e:error=str(e)
                else:initial=plan_result['state'];error=plan_result.get('reason')
                tool_records=[]
                for case,path,value in denominator:
                    r={'application':app,'query':qid,'mode':mode,'case':case['case'],'path':path,
                       'state':initial,'reason':error,'business_equal':None,'target_bound':False,
                       'source_call_complete':source_complete,'oracle_adequate':False,'positive':None,
                       'TP':None,'FP':None,'FN':None}
                    own=[c for c in actual if c['case']==case['case']]
                    if own:
                        c=own[0];r['business_equal']=c['http_status']==case['http_status']and c['response']==case['response']
                        # New generated IDs/clocks can differ; no such mismatch
                        # can silently establish this missing generation oracle.
                        if not r['business_equal']:r.update(state='instrumented_business_difference',reason='Original and tool execution differ; raw outputs retained, not excluded.')
                        elif error:r['state']='evidence_invalid'
                        else:
                            try:
                                if mode=='mirrortaint':
                                    a=native_answer(rows,c['message'],path)
                                    targets=[s for s in rows if s['kind']=='target'and s.get('context',{}).get('message')==c['message']]
                                    assert len(targets)==1,'Raw target root missing/ambiguous';target=targets[0]
                                    fields=[f for s in wire if s.get('kind')=='http-json'and s.get('direction')=='response'and s.get('phase')=='write'and s.get('message')==c['message']for f in s['fields']if f['path']==path]
                                    assert len(fields)==1,'Actual wire target field missing/ambiguous';f=fields[0]
                                    matches=[v for v in target['fields']if v['path']==path and all(v.get(k)==f.get(k)and f.get(k)is not None for k in ('owner','field','version'))]
                                    assert len(matches)==1 and f.get('observed',{}).get('value',f.get('value'))==value,'Wire/root target coordinate differs'
                                    r['target_bound']=True
                                    if app!='ruoyi':raise ValueError('Copy/generation needs independent constructor/write correspondence; tags or equal values are not that fact.')
                                    sources=[s for s in rows if s['kind']=='source'and s.get('root')==target['root']and s.get('call')in q['source_calls']]
                                    r['source_call_complete']=bool(sources)
                                    wants=[(s['call'],s['ordinal'],v['path'],v['owner'],v['field'],v['version'])for s in sources for v in s['fields']if all(v.get(k)==f.get(k)and f.get(k)is not None for k in ('owner','field','version'))]
                                    if qid=='ruoyi-6':wants=[];assert value==200,'Non-success path requires separately reviewed constant rule'
                                    else:assert len(wants)==1,'Declared actual source field absent/ambiguous'
                                    want=set(wants);got=set(map(tuple,a.get('sources',[])));known=a['state']=='known'
                                else:
                                    a=graph.query(c['message'],path,'role',boundary=[{'kind':'binding-source'},{'kind':'argument'}])
                                    targets=index.returns.get(c['message'],[]);assert len(targets)==1,'Raw target root missing/ambiguous'
                                    fields=[f for f in targets[0]['fields']if f['path']==path];assert len(fields)==1;f=fields[0]
                                    assert f['observed']['value']==value;r['target_bound']=True
                                    sources=[s for s in index.source_family(targets[0]['frame'])if s.get('callee')in q['source_calls']]
                                    from audit_zlt_foundation_revision import tf_pair
                                    for s in sources:tf_pair(rows,s)
                                    r['source_call_complete']=bool(sources)
                                    wants=[(s['callee'],s['frame'],s['seq'],v['path'],v['owner'],v['field'],v['version'])for s in sources for v in s['fields']if all(v.get(k)==f.get(k)and f.get(k)is not None for k in ('owner','field','version'))]
                                    assert len(wants)==1,'Declared actual source field absent/ambiguous'
                                    want=set(wants);got={(s.get('callee'),s.get('root_frame'),s['seq'],s.get('path'),s['owner'],s['field'],s['version'])for s in a['sources']};known=a['known']
                                r.update(oracle_adequate=True,positive=bool(want),state=('known_correct'if got==want else'known_wrong')if known else'unknown',
                                         TP=len(got&want)if known else 0,FP=len(got-want)if known else 0,FN=len(want-got)if known else len(want),
                                         expected=sorted(want,key=str),actual=sorted(got,key=str),reason=None)
                            except Exception as e:
                                r.update(state='oracle_or_target_unavailable',reason=str(e))
                    tool_records.append(r);records.append(r)
                api['tools'][mode]={'states':dict(Counter(r['state']for r in tool_records)),
                    'oracle_adequate':sum(r['oracle_adequate']for r in tool_records),
                    'business_equal_requests':sum(c['http_status']==o['http_status']and c['response']==o['response']for c,o in zip(actual,expected_cases)),
                    'captured_requests':len(actual),'first_state':initial,'failure':error,
                    'raw_sources':sum(s.get('kind')in('source','binding-source')for s in rows)}
            apis.append(api)
    save(out/'instances.json',records);save(out/'summary.json',{'APIs':apis,'candidate':verify()['commit'],
        'all40_still_retained':True,'new_core_or_contracts':False,'third_party_blind':False,
        'scope':'12 sealed query families; complete old40 API experiment remains unfinished. Missing physical facts never supplied by labels/graphs or equal values.'})
    with(out/'instances.csv').open('w')as f:
        cols=['application','query','mode','case','path','state','business_equal','target_bound','source_call_complete','oracle_adequate','positive','TP','FP','FN','reason']
        writer=csv.DictWriter(f,cols,extrasaction='ignore');writer.writeheader();writer.writerows(records)
    print({mode:dict(Counter(r['state']for r in records if r['mode']==mode))for mode in('full','selective','mirrortaint')})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);audit(p.parse_args().out.resolve())
