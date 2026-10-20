#!/usr/bin/env python3
"""Build and audit the COMPLETE sealed per-query/per-input capability matrix.

Prediction and independently reviewed original-business projections remain in
separate functions. This audit does not run applications or change TF code.
"""
import argparse
from collections import Counter,defaultdict
import csv
import hashlib
import json
from pathlib import Path
import shutil
from run_planned_service import ROOT,HERE,load,save,sha
import run_response_binding_revision as old
import run_mirror_read_capabilities as reads
import run_mirror_sock_capabilities as sock
import run_mirror_extra_capabilities as extra
from infer_distributed_fields import Reconstruction


def native_location(root,qs):
    q=qs[0];ident=q['id']
    if q['role']=='orders':return root/'matched-orders08-final/native/capture',sock.evaluate
    if q['role']=='carts':
        p=root/('matched-cart08-final' if (root/'inventory-first'/ident/'plan.json').exists() else 'refused-cart08')/ident/'native/capture'
        return p,sock.evaluate
    if q['role']=='price' and '.findAllPriceConfig(' in q['entry']:return root/'uuid-price-calibrated09/capture',None
    if q['role'] in ('basic','ticketinfo') or any(v in q['http'] for v in ('{start}','namelist','idlist')):
        return root/'extra-entries-calibrated07'/ident/'capture',extra.evaluate
    return root/'read-entries-calibrated'/ident/'capture',None


def tf_location(root,q,primary_id):
    if q['role']=='orders':return root/'matched-orders08-final'/('tf-'+q['id'])
    if q['role']=='carts':return root/'matched-cart08-final'/primary_id/('tf-'+q['id'])
    if q['role']=='basic':return root/'matched-basic'/q['id']
    return root/'read-entries-first'/('tf-'+q['id'])


def response_value(case):
    value=case['response']
    if case['http_status']>=400 and isinstance(value,dict):return {k:v for k,v in value.items() if k!='timestamp'}
    return value


def matched_inputs(native,tf,q):
    a=load(native/'run.json')['cases'];b=load(tf/'capture/run.json')['cases'];assert len(a)==len(b)
    audits=[]
    for left,right in zip(a,b):
        assert left['case']==right['case'] and left['http_status']==right['http_status']
        for key in ('database_documents','fixture','request_path'):
            assert left.get(key)==right.get(key),(q['id'],left['case'],key)
        assert left.get('request_body',left.get('body'))==right.get('request_body',right.get('body')),(q['id'],left['case'],'request body')
        assert old.leaves(left['response'],q['path'])==old.leaves(right['response'],q['path']),(q['id'],left['case'],'target values')
        if q['application']=='trainticket':assert response_value(left)==response_value(right),(q['id'],left['case'],'business response')
        audits.append({'case':left['case'],'same_inputs':True,'same_target_values':True})
    if q['role']=='basic':
        for role in ('station','train','route','price'):
            assert load(native/('db-'+role)/'database-input.json')==load(tf/'capture'/('db-'+role)/'database-input.json')
    return audits


def tf_state(prediction):
    if 'expected' not in prediction:return 'oracle_unavailable'
    if prediction['status']=='known':
        actual={tuple(s) for s in prediction['actual']};expected={tuple(s) for s in prediction['expected']}
        return 'known_correct' if actual==expected else 'known_wrong'
    return {'evidence-invalid':'evidence_invalid'}.get(prediction['status'],prediction['status'])


def supplement(root):
    native=root/'cart-create-calibrated07';prior=ROOT/'artifacts/call-lifecycle-revision-20261020/cart-create-guard'
    from run_mirror_capability_probe import read_events,native_answer
    nr=read_events(native/'capture','carts');native_run=load(native/'capture/run.json');tf_run=load(prior/'capture/run.json')
    graph=Reconstruction(prior/'build',prior/'capture',['carts']);rows=graph.rows['carts'];records=[]
    for i,(a,b) in enumerate(zip(native_run['cases'],tf_run['cases'])):
        assert a['message']==b['message'] and a['response']==b['response']
        message=a['message'];ret=next(r for r in rows if r['kind']=='binding-return' and r.get('message')==message)
        calls=[r for r in rows if r['kind']=='binding-call-enter' and r['frame']==ret['frame'] and r['callee'].startswith('works/weave/socks/cart/repositories/CartRepository.findByCustomerId(')]
        assert len(calls)==(2 if i==0 else 1)
        source=[r for r in rows if r['kind']=='binding-source' and r.get('frame')==ret['frame']][-1]
        field=next(f for f in source['fields'] if f['path']=='/0/customerId')
        assert any(all(f[k]==field[k] for k in ('owner','field','version')) for f in ret['fields'])
        expected={old.source_coord('carts',source,field)}
        tf=graph.query(message,'/customerId','carts',boundary=old.BOUNDARY)
        actual={old.predicted_coord(s) for s in tf['sources']}
        baseline=native_answer(nr,message,'/customerId');assert baseline['state']=='known'
        # Independent original CartResource.lambda$value$24 projection: actual
        # post-save second repository return, not the historical arg0 assertion.
        target=next(r for r in nr if r['kind']=='target' and r['context'].get('message')==message)
        providers=[r for r in nr if r['kind']=='source' and r['root']==target['root'] and '.findByCustomerId(' in r['call']]
        assert len(providers)==(2 if i==0 else 1);provider=providers[-1];nf=next(f for f in provider['fields'] if f['path']=='/0/customerId')
        ne={(provider['call'],provider['ordinal'],nf['path'],nf.get('owner'),nf.get('field'),nf.get('version'))}
        assert {tuple(v) for v in baseline['sources']}==ne
        records.append({'query':'sockshop-carts-get-customerId','application':'sockshop','case':'first-create' if i==0 else 'second-read','path':'/customerId','client_value':a['response']['customerId'],
            'tf_state':('known_correct' if actual==expected else 'known_wrong') if tf['known'] else 'unknown','baseline_state':'known_correct','baseline_conservative_state':'known_correct',
            'tf_expected':[list(v) for v in expected],'tf_actual':[list(v) for v in actual],
            'baseline_expected':[list(v) for v in ne],'baseline_actual':baseline['sources'],'baseline_empty_ids':False,
            'source_set_size':1,'supplementary':True,'matched_inputs':True,'tf_executed':True,'tf_capture':str(prior/'capture'),'baseline_capture':str(native/'capture')})
    return records


def audit(root,out):
    out.mkdir(parents=True,exist_ok=False);seal=HERE/'capability-comparison-62-20261020.json';qs=load(seal)['queries'];assert len(qs)==62
    groups=defaultdict(list)
    for q in qs:groups[q['entry']].append(q)
    inventory=load(root/'inventory-first/inventory.json');plans={q['id']:q for q in inventory['queries']}
    records=[];families=[];case_audits=[];source_receipts={}
    for entry,group in groups.items():
        native,scorer=native_location(root,group);assert load(native/'run.json')['status']=='business-completed'
        name=group[0]['id'];dest=out/'rescored'/name;dest.mkdir(parents=True);(dest/'capture').symlink_to(native,target_is_directory=True)
        if scorer is None:evaluations=reads.native_evaluate(dest,group)
        else:evaluations=scorer(dest/'capture',group)
        run=load(native/'run.json');evs={e['id']:e for e in evaluations}
        source_receipts[str(native)]=sha(native/'run.json')
        for q in group:
            ev=evs[q['id']];tf=None;tf_predictions={};audits=[]
            if plans[q['id']]['planning']=='accepted':
                tf=tf_location(root,q,name);assert load(tf/'capture/run.json')['status']=='business-completed'
                audits=matched_inputs(native,tf,q);case_audits.append({'query':q['id'],'passed':True,'checks':audits,'excluded_generated_nonquery_fields':['HTTP error timestamp']})
                tr=load(tf/'capture/evaluation.json');tf_predictions={(p['case'],p['path']):p for p in tr['predictions']}
                assert len(tf_predictions)==tr['target_instances']==len(ev['targets'])
                source_receipts[str(tf/'capture/evaluation.json')]=sha(tf/'capture/evaluation.json')
            counts=Counter();before=len(records)
            for p in ev['targets']:
                assert 'expected' in p,('Independent oracle unavailable',q['id'],p['case'],p.get('oracle_error'))
                if p.get('oracle_error'):raise ValueError((q['id'],p['case'],p['oracle_error']))
                answer=p['answer'];state=p['state'];assert state in ('known_correct','known_wrong','unknown','evidence_invalid')
                ids=answer.get('native_target',{}).get('native_ids',[]);empty=answer.get('state')=='known' and not ids
                conservative='unknown' if empty else state
                tp=tf_predictions.get((p['case'],p['path']));ts=tf_state(tp) if tf is not None else 'planning_refused'
                assert ts in ('known_correct','known_wrong','unknown','evidence_invalid','planning_refused')
                if tp:assert len(tp['expected'])==len(p['expected']),(q['id'],p['case'],'Truth cardinality differs')
                r={'query':q['id'],'application':q['application'],'case':p['case'],'path':p['path'],'client_value':p['client_value'],
                    'tf_state':ts,'baseline_state':state,'baseline_conservative_state':conservative,'baseline_empty_ids':empty,
                    'source_set_size':len(p['expected']),'baseline_expected':p['expected'],'baseline_actual':answer.get('sources',[]),
                    'tf_expected':tp.get('expected') if tp else None,'tf_actual':tp.get('actual',[]) if tp else None,
                    'baseline_capture':str(native),'tf_capture':str(tf/'capture') if tf else None,
                    'matched_inputs':True if tf is not None else 'N/A-planning-refused','tf_executed':tf is not None,'supplementary':False}
                records.append(r);counts['targets']+=1;counts['tf_'+ts]+=1;counts['baseline_'+state]+=1
            assert len(records)-before==len(ev['targets'])
            # Every query-request stays represented, including no-target cases.
            for c in run['cases']:
                if not old.leaves(c['response'],q['path']) or c['http_status'] not in (200,201):
                    case_audits.append({'query':q['id'],'case':c['case'],'state':'N/A','business_generated_target':False,'tf_planning':plans[q['id']]['planning']})
            families.append({'id':q['id'],'application':q['application'],'entry':entry,'planning':plans[q['id']]['planning'],
                'planning_reason':plans[q['id']].get('planning_reason'),'requests':len(run['cases']),'tf_executed_requests':len(run['cases']) if tf else 0,'N/A_requests':ev['N/A_requests'],'counts':dict(counts),
                'baseline_capture':str(native),'tf_capture':str(tf/'capture') if tf else None})
    main=list(records);added=supplement(root);records+=added
    source_receipts['supplement_original_checks']=sha(ROOT/'artifacts/call-lifecycle-revision-20261020/cart-create-guard/checks.json')
    freeze=load(ROOT/'artifacts/call-lifecycle-revision-20261020/algorithm-freeze.json')
    assert len(freeze['core_sources'])==26 and all(sha(ROOT/p)==h for p,h in freeze['core_sources'].items())
    base=ROOT/'artifacts/call-lifecycle-revision-20261020/base-build'
    assert len(freeze['original_jars'])==9 and all(sha(base/role/'original.jar')==h for role,h in freeze['original_jars'].items())
    for name in list(source_receipts):
        p=Path(name)
        directory=p if p.is_dir() else p.parent if p.is_file() and p.name=='evaluation.json' else None
        if directory:
            for raw in directory.glob('*/*.jsonl'):source_receipts[str(raw)]=sha(raw)
    def summarize(rows):
        pairs=Counter((r['tf_state'],r['baseline_state']) for r in rows);tf=Counter(r['tf_state'] for r in rows);mt=Counter(r['baseline_state'] for r in rows)
        good=[r for r in rows if r['baseline_state']=='known_correct'];joint=[r for r in good if r['tf_state']=='known_correct'];gaps=[r for r in good if r['tf_state']!='known_correct']
        strong=[r for r in rows if r['baseline_conservative_state']=='known_correct'];strong_joint=[r for r in strong if r['tf_state']=='known_correct']
        def relations(tool):
            total=Counter()
            for r in rows:
                expected={tuple(v) for v in (r['tf_expected'] if tool=='tf' and r['tf_expected'] is not None else r['baseline_expected'])}
                actual={tuple(v) for v in r[tool+'_actual']} if r[tool+'_state'] in ('known_correct','known_wrong') else set()
                # A refused TF query has no own coordinate trace. Count its
                # independent truth cardinality as FN; never compare IDs across tools.
                total['tp']+=len(actual&expected);total['fp']+=len(actual-expected);total['fn']+=len(expected-actual)
            return dict(total)
        return {'targets':len(rows),'tf_states':dict(tf),'baseline_states':dict(mt),'pairs':[{'tf':a,'baseline':b,'targets':n} for (a,b),n in sorted(pairs.items())],
            'baseline_correct':len(good),'tf_correct_on_baseline_correct':len(joint),'capability_gaps':len(gaps),'retention':len(joint)/len(good),
            'nonempty_certified_baseline_correct':len(strong),'tf_correct_on_nonempty_baseline_correct':len(strong_joint),'nonempty_capability_gaps':len(strong)-len(strong_joint),
            'empty_native_output_targets':sum(r['baseline_empty_ids'] for r in rows),'relations_including_unanswered':{'tf':relations('tf'),'baseline':relations('baseline')},'acceptance_passed':not gaps and not tf['known_wrong']}
    summary={'selected_families':62,'applications':dict(Counter(q['application'] for q in qs)),'distinct_entries':len(groups),
        'tf_planning':dict(Counter(q['planning'] for q in plans.values())),
        'main':summarize(main),'with_first_creation_challenge':summarize(records),'N/A_query_requests':sum(f['N/A_requests'] for f in families),
        'input_audits':len([a for a in case_audits if a.get('passed')]),'tf_core_files_unchanged':26,'new_performance_measurements':False,
        'remaining_candidates_untested':29,'baseline_kind':'Pinned MirrorTaint + disclosed compatibility, boundary-source, native-export and instance-binding adapters',
        'empty_policy':'Main score grades the actual native source-ID set, including empty sets. Conservative sensitivity treats every empty native tag as unknown, never a certified empty dependency set. Both must be shown.',
        'first_create_oracle_erratum':'Original first GET saves and then returns a second repository read. Historical arg0 expectation corrected from actual original bytecode/call evidence. Old raw files and counts preserved.'}
    gaps=[r for r in records if r['baseline_state']=='known_correct' and r['tf_state']!='known_correct']
    save(out/'summary.json',summary);save(out/'families.json',families);save(out/'instances.json',records);save(out/'capability-gaps.json',gaps);save(out/'input-and-NA-audit.json',case_audits)
    save(out/'provenance.json',{'query_seal_sha256':sha(seal),'sources_sha256':source_receipts,'auditor_sha256':sha(Path(__file__)),'core_commit':freeze['algorithm_commit'],'no_prediction_reads_expected':True})
    columns=['query','application','case','path','client_value','tf_state','baseline_state','baseline_conservative_state','baseline_empty_ids','source_set_size','matched_inputs','tf_executed','supplementary','baseline_capture','tf_capture']
    with (out/'instances.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=columns,extrasaction='ignore',lineterminator='\n');w.writeheader();w.writerows(records)
    with (out/'families.csv').open('w') as f:
        w=csv.writer(f,lineterminator='\n');w.writerow(['query','application','planning','requests','N/A_requests','targets','tf_correct','tf_unknown','baseline_correct','baseline_wrong','baseline_unknown','reason'])
        for r in families:
            c=r['counts'];w.writerow([r['id'],r['application'],r['planning'],r['requests'],r['N/A_requests'],c.get('targets',0),c.get('tf_known_correct',0),c.get('tf_unknown',0),c.get('baseline_known_correct',0),c.get('baseline_known_wrong',0),c.get('baseline_unknown',0),r['planning_reason']])
    print(json.dumps(summary,ensure_ascii=False,indent=2),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();audit(a.root.resolve(),a.out.resolve())
