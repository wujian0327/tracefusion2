#!/usr/bin/env python3
"""Re-score fresh captures into the original 431 target-instance acceptance set."""
import argparse,collections,csv,json
from pathlib import Path
from run_planned_service import ROOT,HERE,load,save,sha
from audit_application_call_revision import class_hashes
import run_frozen_capability_acceptance as driver
import run_response_binding_revision as old

def audit(root,out,partial=False):
    out.mkdir(parents=True,exist_ok=False);driver.check();freeze=load(root/'algorithm-freeze.json');base=Path(freeze['base_build']);agent=class_hashes(base/'distributed-observer.jar');oldrows=load(ROOT/'artifacts/baseline-capability-20261020/audit-final-v3/instances.json');before={(r['query'],r['case'],r['path']):r for r in oldrows};assert len(before)==431
    assert sha(HERE/'build_distributed_plans.py')==freeze['builder_sha256']
    assert sha(HERE/'capability-acceptance-protocol-20261021.json')==freeze['acceptance_protocol_sha256']
    assert sha(HERE/'date-effects-protocol-20261021.json')==freeze['protocol_sha256']
    assert sha(root/'frozen-plans/planning.json')==freeze['planning_sha256']
    for planned in load(root/'frozen-plans/planning.json'):
        if planned['status']=='accepted':assert sha(root/'frozen-plans'/(planned['query']['id']+'.json'))==planned['plan_sha256']
    queries=driver.QUERIES;by_query={q['id']:q for q in queries};records=[];families=[];receipts={};builds=[]
    candidates=[];repeat_meta={};primary_failures=[]
    for worker in root.glob('all62-*'):
        if worker.name not in ('all62-reads','all62-route','all62-travel','all62-cart','all62-orders-serial'):continue
        candidates.extend(d for d in sorted(worker.glob('*-*-*'))if (d/'capture/run.json').exists())
        summary=worker/'results.json'
        if summary.exists():
            for row in load(summary)['results']:
                if 'failure'in row:primary_failures.append({**row,'directory':str(worker/(row['mode']+'-'+row['query']))})
    repeat_file=root/'business-repeats/results.json'
    if repeat_file.exists():
        repetitions=load(repeat_file);assert repetitions['complete']
        assert load(root/'business-repeats/protocol-before-repeats.json')['protocol_sha256']==sha(HERE/'capability-business-repeat-protocol-20261021.json')
        for item in repetitions['results']:
            if not item['both_repeats_passed']:continue
            first=Path(item['attempts'][0]['directory']);second=Path(item['attempts'][1]['directory']);assert item['selected_receipt']==str(first)
            candidates.append(first);repeat_meta[(item['mode'],item['query'])]=item
            q=by_query[item['query']];checkdir=out/('corroboration-'+item['mode']+'-'+item['query']);checkdir.mkdir();(checkdir/'build').symlink_to(second/'build',target_is_directory=True);(checkdir/'capture').symlink_to(second/'capture',target_is_directory=True)
            assert class_hashes(second/'build/distributed-observer.jar')==agent and sha(second/'build'/q['role']/'plan.json')==sha(root/'frozen-plans'/(q['id']+'.json'))
            second_result=driver.evaluate(checkdir,q);assert not second_result['oracle_unavailable'] and set(second_result['states'])<=set(['known_correct'])
            for path in (second/'capture'/q['role']/'events.jsonl',second/'input-audit.json',second/'capture/run.json'):receipts[str(path.relative_to(ROOT))]=sha(path)
    for d in candidates:
        mode,qid=d.name.split('-',1);q=by_query.get(qid)
        if q is None:continue
        build=d/'build';assert class_hashes(build/'distributed-observer.jar')==agent
        p=load(build/q['role']/'plan.json');frozen_plan=driver.plan(q);assert p==frozen_plan
        assert sha(build/q['role']/'plan.json')==sha(root/'frozen-plans'/(qid+'.json'))
        for role,h in freeze['original_jars'].items():assert sha(build/role/'original.jar')==h
        assert load(d/'input-audit.json')['checks'];rec=out/('rescore-'+mode+'-'+qid);rec.mkdir();(rec/'build').symlink_to(build,target_is_directory=True);(rec/'capture').symlink_to(d/'capture',target_is_directory=True)
        repeat=repeat_meta.get((mode,qid));basis='first-fixed-repeat-with-second-corroboration'if repeat else'primary'
        result=driver.evaluate(rec,q);families.append({'mode':mode,'entry':q['entry'],'application':q['application'],**result,'capture':str(d/'capture'),'capture_basis':basis,'primary_failure':repeat['primary']if repeat else None});ev=load(rec/'evaluation.json');rows=ev['predictions']
        for r in rows:records.append({**r,'mode':mode,'application':q['application'],'capture':str(d/'capture')})
        for p in (d/'capture'/q['role']/'events.jsonl',d/'capture/run.json',d/'input-audit.json',build/q['role']/'plan.json'):receipts[str(p.relative_to(ROOT))]=sha(p)
        builds.append(str(build))
    # A rejected query has no TF execution. Enumerate its actual target leaves
    # from a fresh same-entry business capture with identical original inputs.
    # This is a business receipt, never a source answer or a substituted plan.
    for rejection in load(root/'frozen-plans/planning.json'):
        if rejection.get('status')!='rejected':continue
        q=rejection['query']
        for mode in ('full','selective'):
            receipt=next((f for f in families if f['mode']==mode and f['entry']==q['entry']),None)
            if receipt is None:continue
            cap=Path(receipt['capture']);run=load(cap/'run.json');targets=0;na=0
            for case in run['cases']:
                values=old.leaves(case['response'],q['path']) if 200<=case['http_status']<300 else [];na+=not bool(values)
                for path,value in values:
                    key=(q['id'],case['case'],path);assert key in before
                    assert value==before[key]['client_value'];targets+=1
                    records.append({'mode':mode,'query':q['id'],'application':q['application'],'case':case['case'],'path':path,'client_value':value,'state':'planning_rejected','rejection':rejection['rejection'],'runtime_for_rejected_query':False,'business_target_receipt':str(cap),'tp':0,'fp':0,'fn':before[key]['source_set_size'],'relation_count_basis':'Independent original reference oracle cardinality; no new source-coordinate answer is claimed'})
            families.append({'mode':mode,'query':q['id'],'entry':q['entry'],'application':q['application'],'requests':len(run['cases']),'targets':targets,'states':{'planning_rejected':targets},'N/A_requests':na,'runtime_for_rejected_query':False,'business_target_receipt':str(cap),'rejection':rejection['rejection']})
    pair=root/'cart-create-pair'
    if (pair/'results.json').exists():
        assert load(pair/'results.json')['all_passed']
        metadata=pair/('protocol-correction.json'if(pair/'protocol-correction.json').exists()else'launch-metadata.json');correction=load(metadata);assert correction['actual_customerId']=='56e8f576709b70d0ace01fb0'
        assert sha(root/'drivers/cart-pair-library-driver-at-launch.py')==correction['driver_at_launch_sha256']
        if metadata.name=='launch-metadata.json':assert correction['original_declared_input_already_correct'] and correction['driver_at_launch_sha256']==freeze['pair_driver_sha256']
        receipts[str(metadata.relative_to(ROOT))]=sha(metadata)
        for mode in ('full','selective'):
            d=pair/mode;assert class_hashes(d/'build/distributed-observer.jar')==agent;assert sha(d/'build/carts/plan.json')==sha(root/'frozen-plans/sockshop-carts-get-customerId.json')
            g=old.Reconstruction(d/'build',d/'capture',['carts']);rs=g.rows['carts']
            for index,c in enumerate(load(d/'capture/run.json')['cases']):
                ret=next(r for r in rs if r['kind']=='binding-return' and r.get('message')==c['message']);frames=driver.family(rs,ret);sources=[r for r in rs if r['kind']=='binding-source' and r.get('frame') in frames and '.findByCustomerId(' in r.get('callee','')];assert len(sources)==1
                calls=[r for r in rs if r['kind']=='collection-call-enter' and r.get('frame') in frames and r['callee']==sources[0]['callee']];assert len(calls)==(2 if index==0 else 1)
                f=next(f for f in sources[0]['fields'] if f['path']=='/0/customerId');expected={old.source_coord('carts',sources[0],f)};assert f['observed']['value']==c['customerId']=='56e8f576709b70d0ace01fb0'
                a=g.query(c['message'],'/customerId','carts',boundary=old.BOUNDARY);actual={old.predicted_coord(s) for s in a['sources']};state=('known_correct' if actual==expected else 'known_wrong') if a['known'] else 'unknown'
                records.append({'mode':mode,'query':'sockshop-carts-get-customerId','application':'sockshop','case':'first-create' if index==0 else 'second-read','path':'/customerId','client_value':c['response']['customerId'],'state':state,'expected':sorted(expected,key=str),'actual':sorted(actual,key=str),'supplementary':True,'tp':len(actual&expected) if a['known'] else 0,'fp':len(actual-expected) if a['known'] else 0,'fn':len(expected-actual) if a['known'] else len(expected),'capture':str(d/'capture')})
            receipts[str((d/'capture/carts/events.jsonl').relative_to(ROOT))]=sha(d/'capture/carts/events.jsonl')
    primary_partial={};partial_wrong=[]
    for failure in primary_failures:
        source=Path(failure['directory']);q=by_query[failure['query']];cases=[load(p)for p in sorted((source/'capture').glob('group-*/contract-result.json'))]
        if not cases:continue
        reference={c['case']:c for c in load(driver.previous(q)/'run.json')['cases']}
        for case in cases:
            previous=reference[case['case']];assert case['fixture']==previous['fixture'] and case['request_body']==previous['request_body'] and case['http_status']==previous['http_status']
            assert old.leaves(case['response'],q['path'])==old.leaves(previous['response'],q['path'])
        dest=out/('primary-partial-'+failure['mode']+'-'+failure['query']);dest.mkdir();(dest/'build').symlink_to(source/'build',target_is_directory=True);cap=dest/'capture';cap.mkdir();(cap/q['role']).symlink_to(source/'capture'/q['role'],target_is_directory=True)
        save(cap/'run.json',{'status':'partial-business-capture','roles':[q['role']],'mode':failure['mode'],'cases':cases,'original_capture':str(source/'capture'),'failed_batch_not_completed':True});driver.evaluate(dest,q)
        for r in load(dest/'evaluation.json')['predictions']:
            primary_partial[(failure['mode'],r['query'],r['case'],r['path'])]=r
            if r['state']=='known_wrong':partial_wrong.append(r)
    summaries={};joined=[];first_attempt={};first_states={}
    failure_keys={(r['mode'],r['query']):r for r in primary_failures}
    for mode in ('full','selective'):
        present={(r['query'],r['case'],r['path']):r for r in records if r['mode']==mode};states=collections.Counter();business_cases=[];first_states[mode]={}
        for key,reference in before.items():
            failure=failure_keys.get((mode,key[0]));row=present.get(key)
            if failure:
                partial=primary_partial.get((mode,*key))
                if partial:state=partial['state']
                else:
                    case_dir=Path(failure['directory'])/'capture'/key[1];attempted=(case_dir/'http-client-observations.json').exists();state='business_error'if attempted else'not_executed_after_batch_failure';business_cases.append({'key':key,'state':state})
            else:state=row['state']if row else'pending'
            states[state]+=1;first_states[mode][key]=state
        first_attempt[mode]={'reference_target_states':dict(states),'affected_reference_instances':business_cases,'failed_configurations':sum(r['mode']==mode for r in primary_failures),'first_attempt_business_all_passed':not any(r['mode']==mode for r in primary_failures)}
    for mode in ('full','selective'):
        selected=[r for r in records if r['mode']==mode];mapping={(r['query'],r['case'],r['path']):r for r in selected};assert len(mapping)==len(selected),'Duplicate target instance'
        assert set(mapping)<=set(before),'Added/substituted target instance'
        mtgood=tfoldgood=uniongood=mtnonempty=0;loss=[]
        for key,new in mapping.items():
            prior=before[key]
            if key[0]!='sockshop-orders-newOrder-date':assert new['client_value']==prior['client_value'],('Changed original target business value',key)
            good=new['state']=='known_correct';mt=prior['baseline_state']=='known_correct';tf=prior['tf_state']=='known_correct'
            mtgood+=mt and good;tfoldgood+=tf and good;uniongood+=(mt or tf) and good;mtnonempty+=mt and prior['source_set_size']>0 and good
            if (mt or tf) and not good:loss.append(key)
            joined.append({**new,'old_tf_state':prior['tf_state'],'baseline_state':prior['baseline_state'],'required_by_union':mt or tf,'first_attempt_state':first_states[mode][key],'source_receipt_basis':'fixed-repeat-1'if(mode,key[0])in repeat_meta else'primary-or-static-rejection'})
        states=dict(collections.Counter(r['state'] for r in selected));missing=sorted(set(before)-set(mapping));summaries[mode]={'expected_targets':431,'actual_targets':len(selected),'states':states,'known_answer_exact_rate':states.get('known_correct',0)/sum(states.get(s,0) for s in ('known_correct','known_wrong','known_unchecked')) if any(states.get(s,0) for s in ('known_correct','known_wrong','known_unchecked')) else None,'answerability':states.get('known_correct',0)/431,'baseline_correct_preserved':mtgood,'baseline_correct_required':368,'baseline_nonempty_correct_preserved':mtnonempty,'baseline_nonempty_correct_required':337,'old_tf_correct_preserved':tfoldgood,'old_tf_correct_required':213,'union_preserved':uniongood,'union_required':382,'union_losses':loss,'missing_targets':missing,'tp':sum(r.get('tp',0) for r in selected),'fp':sum(r.get('fp',0) for r in selected),'fn_including_unknown':sum(r.get('fn',0) for r in selected),'all_passed':not missing and not loss and not states.get('known_wrong',0) and not states.get('known_unchecked',0) and mtgood==368 and tfoldgood==213 and uniongood==382}
    concordance=[]
    for key in before:
        a=next((r for r in records if r['mode']=='full' and (r['query'],r['case'],r['path'])==key),None);b=next((r for r in records if r['mode']=='selective' and (r['query'],r['case'],r['path'])==key),None)
        if a and b:concordance.append({'key':key,'same_state':a['state']==b['state'],'both_correct':a['state']==b['state']=='known_correct'})
    controls=load(root/'date-controls/results.json') if (root/'date-controls/results.json').exists() else None
    if controls:
        assert controls['all_passed'] and class_hashes(root/'date-controls/build/distributed-observer.jar')==agent
        assert all(r['targets']==28 and r['known_exact']==16 and r['expected_unknown']==12 and len(r['faults'])==10 and all(r['faults'].values()) for r in controls['modes'].values())
    mutation=load(root/'received-controls/results.json') if (root/'received-controls/results.json').exists() else None
    legacy=load(root/'legacy-collection-controls/results.json') if (root/'legacy-collection-controls/results.json').exists() else None
    if mutation:
        assert mutation['all_passed'] and class_hashes(root/'received-controls/build/distributed-observer.jar')==agent
        assert all(r['targets']==6 and r['known_exact']==2 and r['expected_unknown']==4 and r['business_mutations_completed']==4 and all(r['faults'].values())for r in mutation['modes'].values())
    if legacy:
        assert legacy['all_passed'] and class_hashes(root/'legacy-collection-controls/build/distributed-observer.jar')==agent
        assert all(r['exact']==r['queries']==10 and r['tamper_rejected']for r in legacy['profiles'].values())
        assert all(r['rejected']for r in legacy['negative_contracts'].values())
    seen={(f['mode'],f['query']) for f in families};complete_queries=len(seen)==124
    result={'algorithm_commit':freeze['commit'],'queries':62,'entries':len({q['entry'] for q in queries}),'query_configurations_scored':len(families),'complete_query_configurations':complete_queries,'modes':summaries,'full_selective_state_agreement':sum(r['same_state'] for r in concordance),'paired_target_instances':len(concordance),'date_controls_passed':bool(controls),'planning_accepted':sum(r.get('status')=='accepted'for r in load(root/'frozen-plans/planning.json')),'planning_rejected':sum(r.get('status')=='rejected'for r in load(root/'frozen-plans/planning.json')),'received_mutation_controls_passed':bool(mutation),'legacy_collection_controls_passed':bool(legacy),'heldout_candidates_unexamined':29,'no_new_performance':True,'all_passed':complete_queries and all(r['all_passed'] for r in summaries.values()) and len(concordance)==431 and all(r['same_state'] for r in concordance) and bool(controls) and bool(mutation) and bool(legacy)}
    first_pairs=collections.Counter()
    for key in before:
        full=first_states['full'][key]=='known_correct';selective=first_states['selective'][key]=='known_correct';first_pairs['both_correct'if full and selective else'full_correct_selective_not_correct'if full else'selective_correct_full_not_correct'if selective else'both_not_correct']+=1
    result['first_attempt_pairing']=dict(first_pairs)
    result['provenance_union_passed']=result['all_passed'] and not partial_wrong;result['primary_partial_wrong_answers']=partial_wrong;result['first_attempt']=first_attempt;result['primary_business_failures']=primary_failures
    result['first_attempt_business_all_passed']=not primary_failures
    result['all_passed']=result['provenance_union_passed'] and result['first_attempt_business_all_passed']
    result['unqualified_end_to_end_acceptance']=result['all_passed']
    result['business_repeat_protocol_sha256']=sha(HERE/'capability-business-repeat-protocol-20261021.json')
    for failure in primary_failures:
        folder=Path(failure['directory'])
        for path in folder.rglob('*'):
            if path.is_file() and path.suffix in ('.json','.jsonl','.log') and 'build'not in path.relative_to(folder).parts:receipts[str(path.relative_to(ROOT))]=sha(path)
    save(out/'audit.json',result);save(out/'instances.json',joined);save(out/'queries.json',families);save(out/'raw-hashes.json',receipts)
    with (out/'instances.csv').open('w',newline='') as f:
        fields=['mode','application','query','case','path','state','old_tf_state','baseline_state','required_by_union','first_attempt_state','source_receipt_basis','tp','fp','fn'];w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(joined)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    if not partial:assert result['provenance_union_passed'],'Provenance union not satisfied; preserved complete first-attempt and repeat audit.'
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--partial',action='store_true');a=p.parse_args();audit(a.root.resolve(),a.out.resolve(),a.partial)
