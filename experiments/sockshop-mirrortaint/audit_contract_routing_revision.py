#!/usr/bin/env python3
"""Audit exposed write queries and the narrow application-value ablation.

Never overwrites the first heldout or native scores. Query truth is selected
from original business semantics and raw field/call coordinates, not TF edges.
"""
import argparse,copy,json
from collections import Counter
from pathlib import Path
from run_planned_service import ROOT,load,save,sha
from audit_application_call_revision import class_hashes
import run_contract_routing_revision as revision
import run_frozen_capability_acceptance as driver


def final_root(root):return Path(load(root/'current-final.json')['root'])if(root/'current-final.json').exists()else root/'final'


def oracle_correction(root):
    parent=revision.PARENT/'heldout21-first';changes=[];checked=0;hashes={}
    queries={q['id']:q for q in load(root/'protocol.json')['queries']}
    for role in ('route','price'):
        for file in sorted((parent/('runtime-'+role)).glob('*/evaluation.json')):
            ev=load(file);q=queries[ev['query']];capture=file.parent/'capture'
            run=load(capture/'run.json');rows={role:[json.loads(x)for x in(capture/role/'events.jsonl').read_text().splitlines()]}
            hashes[str(file)]=sha(file);hashes[str(capture/role/'events.jsonl')]=sha(capture/role/'events.jsonl')
            for t in ev['predictions']:
                c=next(c for c in run['cases']if c['case']==t['case'])
                expected=revision.independent_tf(q,c,t['path'],rows);checked+=1
                if sorted(expected,key=str)!=sorted(map(tuple,t['expected']),key=str):changes.append({'mode':ev['mode'],'query':q['id'],'case':t['case'],'path':t['path'],'old_expected':t['expected'],'corrected_expected':sorted(expected,key=str),'old_state_preserved':t['state']})
    assert checked==192 and len(changes)==8
    save(root/'oracle-correction-audit.json',{'all_passed':True,'first_targets_reviewed':checked,'changed_expected_sets':len(changes),'changes':changes,'original_file_hashes':hashes,'original_first_answers_unchanged':'All96 targets per mode remained unanswered; source-coordinate correction does not make any failed first answer successful.','not_a_TF_graph_or_native_label_oracle':True})


def writes(root):
    final=final_root(root);driver.HOME=final;driver.check();driver.independent=revision.independent_tf
    base=final/'frozen-base';classes=class_hashes(base/'distributed-observer.jar');out=root/('write-audit-final'if final.name=='final-v2'else'write-audit');out.mkdir();records=[];targets={}
    native={}
    for file in(root/'native-first').glob('*/evaluation-corrected-oracle.json'):
        for q in load(file):
            for t in q['predictions']:native[(q['query'],t['case'],t['path'])]=t
    for role in ('route','price'):
        home=final/('development-'+role+'-frozen');summary=load(home/'results.json');assert summary['complete']
        assert not any('failure'in r for r in summary['results'])
        for d in sorted(home.glob('*-heldout-*')):
            ev=load(d/'evaluation.json');q=next(q for q in load(root/'protocol.json')['queries']if q['id']==ev['query']);mode=ev['mode']
            assert class_hashes(d/'build/distributed-observer.jar')==classes
            assert sha(d/'build'/role/'plan.json')==sha(final/'write-plans'/(q['id']+'.json'))
            rec=out/(mode+'-'+q['id']);rec.mkdir();(rec/'build').symlink_to((d/'build').resolve(),target_is_directory=True);(rec/'capture').symlink_to((d/'capture').resolve(),target_is_directory=True)
            scored=driver.evaluate(rec,q);ev=load(rec/'evaluation.json');rows=[json.loads(x)for x in(d/'capture'/role/'events.jsonl').read_text().splitlines()]
            records.append({**scored,'evaluation_file':str(rec/'evaluation.json'),'capture':str(d/'capture'),'version_only_writes':sum(r['kind']=='write-version'for r in rows),'event_bytes':(d/'capture'/role/'events.jsonl').stat().st_size,'events':len(rows)})
            cases={c['case']:c for c in load(d/'capture/run.json')['cases']}
            first_query=next(v for v in load(root/'protocol.json')['queries']if v['entry']==q['entry'])
            native_cases={c['case']:c for c in load(root/'native-first'/first_query['id']/'capture/run.json')['cases']}
            assert cases.keys()==native_cases.keys()
            for case,c in cases.items():
                for field in ('request_body','database_documents','response'):assert c[field]==native_cases[case][field],(q['id'],case,field)
            # Cross-tool compare actual case/path/client values and independent
            # states. Object IDs belong to each JVM and cannot be equated.
            for t in ev['predictions']:
                k=(q['id'],t['case'],t['path']);n=native[k];assert t['client_value']==n['client_value'];targets[(mode,*k)]={'tf':t['state'],'baseline':n['state'],'expected':t['expected'],'actual':t.get('actual',[])}
    modes={m:{'queries':sum(r['mode']==m for r in records),'requests':sum(r['requests']for r in records if r['mode']==m),'targets':sum(r['targets']for r in records if r['mode']==m),'states':dict(Counter(v['tf']for k,v in targets.items()if k[0]==m)),'N/A_requests':sum(r['N/A_requests']for r in records if r['mode']==m),'tp':sum(r['tp']for r in records if r['mode']==m),'fp':sum(r['fp']for r in records if r['mode']==m),'fn':sum(r['fn']for r in records if r['mode']==m),'paired_capability':dict(Counter((v['tf'],v['baseline'])for k,v in targets.items()if k[0]==m))}for m in ('full','selective')}
    for v in modes.values():v['paired_capability']={a+' / '+b:n for (a,b),n in v['paired_capability'].items()}
    assert all(v['queries']==15 and v['targets']==96 and v['states']=={'known_correct':96}for v in modes.values())
    save(out/'audit.json',{'all_passed':True,'algorithm':load(final/'algorithm-freeze.json')['commit'],'modes':modes,'baseline_states':dict(Counter(v['state']for v in native.values())),'records':records,'Station':'Six query families retain403; not run with authentication.','unseen_queries':False,'cost_comparison':False})


def ablation(root):
    final=final_root(root);on=load(root/('write-audit-final'if final.name=='final-v2'else'write-audit')/'audit.json');queries={q['id']:q for q in load(root/'protocol.json')['queries']};records=[]
    for r in on['records']:
        if r['mode']!='selective'or queries[r['query']]['role']!='route':continue
        d=final/'application-off'/('selective-'+r['query']);ev=load(d/'evaluation.json');assert ev['states']=={'known_correct':ev['targets']}
        p=load(d/'build/route/plan.json');p['execution_observation_closure']['application_write_values']['enabled']=True
        assert p==load(final/'write-plans'/(r['query']+'.json'))
        rows=[json.loads(x)for x in(d/'capture/route/events.jsonl').read_text().splitlines()];assert not any(v['kind']=='write-version'for v in rows)
        before=load(Path(r['evaluation_file']))['predictions'];after=ev['predictions'];assert[(t['case'],t['path'],t['state'])for t in before]==[(t['case'],t['path'],t['state'])for t in after]
        def measured(cap):
            lines=(cap/'route/events.jsonl').read_text().splitlines(keepends=True);events=[json.loads(x)for x in lines];cases=load(cap/'run.json')['cases'];messages={c['message']for c in cases};returns=[e for e in events if e['kind']=='binding-return'and e.get('message')in messages];frames=set()
            for ret in returns:frames.update(driver.family(events,ret))
            selected=[(line,e)for line,e in zip(lines,events)if e.get('frame')in frames or e.get('message')in messages]
            return {'events':len(selected),'event_bytes':sum(len(line.encode())for line,e in selected),'version_only_writes':sum(e['kind']=='write-version'for line,e in selected),'known_request_roots':len(returns),'raw_file_sha256':sha(cap/'route/events.jsonl')}
        records.append({'query':r['query'],'targets':r['targets'],'answers_preserved':True,'with_policy':measured(Path(r['capture'])),'without_policy':measured(d/'capture')})
    assert len(records)==5 and sum(r['with_policy']['version_only_writes']for r in records)>0
    save(root/'application-value-ablation.json',{'all_passed':True,'records':records,'only_changed':'application_write_values.enabled','interpretation':'Brief capability captures. Value boxing/persistence omitted; write/version events and all calls/path records retained. Not a latency/CPU or statistically repeated cost experiment.','record_count_claim':False})


def save_guards(root):
    from infer_execution_kernel import infer_execution
    d=root/'final/development-route-frozen/full-heldout-closure-route-createAndModify-startStationId';p=load(d/'build/route/plan.json');rows=[json.loads(x)for x in(d/'capture/route/events.jsonl').read_text().splitlines()]
    message=load(d/'capture/run.json')['cases'][0]['message'];ret=next(e for e in rows if e['kind']=='binding-return'and e.get('message')==message);frame=ret['frame'];faults={}
    for label in ('missing-proof','library-version','id-changed','callback','different-result','changed-field','incomplete-call'):
        changed=copy.deepcopy(rows);s=next(e for e in changed if e['kind']=='mongo-save-effect'and e['frame']==frame)
        if label=='missing-proof':changed.remove(s)
        elif label=='library-version':s['class_sha256'][next(iter(s['class_sha256']))]='0'*64
        elif label=='id-changed':s['id_after']['value']='OTHER'
        elif label=='callback':s['callback_invocations']=1
        elif label=='different-result':s['result']['object']='other-same-value-entity'
        elif label=='changed-field':s['after'][0]['version']+=1
        else:
            end=next(e for e in changed if e['kind']=='collection-call-exit'and e.get('call_id')==s['call_id']);changed.remove(end)
        try:infer_execution(p,changed)
        except ValueError:faults[label]=True
        else:raise AssertionError('Accepted contradictory save effect '+label)
    changed=copy.deepcopy(rows);s=next(e for e in changed if e['kind']=='mongo-save-effect'and e['frame']==frame);s['valid']=False;s['reason']='unsupported callback configuration'
    result=infer_execution(p,changed);answers=[a for a in result['answers']if a['root_frame']==frame];assert answers and not answers[0]['known']
    save(root/'save-effect-guards.json',{'all_passed':True,'contradictory_evidence_rejected':faults,'unmodeled_effect_remains_unknown':True,'metadata_and_native_id_concrete_write_regression':str(root/'save-id-regression/results.json')})


def cache_guards(root,out):
    from audit_frozen_capability_acceptance import audit
    final=final_root(root);driver.HOME=final;source=final/'compatible-score-cache';out.mkdir();checks={}
    for label in ('scoring-code','raw-evidence','derived-score'):
        c=out/label;c.mkdir();meta=copy.deepcopy(load(source/'audit.json'));hashes=load(source/'raw-hashes.json')
        if label=='scoring-code':meta['scoring_source_sha256']={k:'0'*64 for k in meta['scoring_source_sha256']}
        elif label=='raw-evidence':hashes={k:'0'*64 for k in hashes}
        else:meta['derived_sha256']={k:'0'*64 for k in meta['derived_sha256']}
        save(c/'audit.json',meta);save(c/'raw-hashes.json',hashes)
        for p in source.glob('rescore-*'):(c/p.name).symlink_to(p,target_is_directory=True)
        try:audit(final,out/(label+'-attempt'),partial=True,reuse=c)
        except AssertionError:checks[label]=True
        else:raise AssertionError('Accepted corrupt score cache '+label)
    save(out/'results.json',{'all_passed':True,'refusals':checks,'original_cache_audit_sha256':sha(source/'audit.json'),'raw_captures_unchanged':True})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',required=True,type=Path);p.add_argument('--stage',required=True,choices=('oracle','writes','ablation','save-guards','cache-guards'));p.add_argument('--out',type=Path);a=p.parse_args()
    if a.stage=='cache-guards':
        if a.out is None:p.error('--out is required for cache-guards; use a new directory')
        cache_guards(a.root.resolve(),a.out.resolve())
    else:{'oracle':oracle_correction,'writes':writes,'ablation':ablation,'save-guards':save_guards}[a.stage](a.root.resolve())
