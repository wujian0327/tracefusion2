#!/usr/bin/env python3
"""Audit frozen raw facts in a new directory; never replace original predictions."""
import argparse,copy,csv,json
from pathlib import Path
from run_planned_service import ROOT,HERE,load,save,sha
from infer_distributed_fields import Reconstruction
from infer_execution_kernel import infer_execution
from plan_response_binding import plan_response
from audit_application_call_revision import class_hashes
import run_response_binding_revision as old
from run_execution_kernel_pilot import independent
from run_ticketinfo_wrapper_revision import BASELINE,BOUNDARY

def audit(root,out):
    out.mkdir(parents=True,exist_ok=False);freeze=load(root/'algorithm-freeze.json');base=root/'final-base-build';agent=class_hashes(base/'distributed-observer.jar');raw={};reuse=[]
    assert all(sha(Path(p))==v for p,v in freeze['sources'].items()),'Frozen source changed'
    assert sha(HERE/'ticketinfo-wrapper-protocol-20261020.json')==freeze['protocol_sha256']
    assert sha(HERE/'execution-kernel-protocol-20261020.json')==freeze['reserved_protocol_sha256']
    assert len(load(HERE/'execution-kernel-protocol-20261020.json')['unexamined_candidates'])==29
    assert all(sha(base/r/'original.jar')==v for r,v in freeze['original_jars'].items())
    def record(p):raw[str(p.relative_to(ROOT))]=sha(p)
    def same_plan(build,role):
        p=load(build/role/'plan.json');new=plan_response(load(base/role/'model.json'),p['entry'],p['target'],p['response_binding']['path'],execution_kernel=True,application_calls=True)
        assert p==new and class_hashes(build/'distributed-observer.jar')==agent
        reuse.append({'build':str(build.relative_to(ROOT)),'role':role,'same_generated_plan':True,'same_all_agent_classes':True});return p
    protocol=load(HERE/'ticketinfo-wrapper-protocol-20261020.json');instances=[];totals={}
    original_instances=load(ROOT/'artifacts/baseline-capability-20261020/audit-final-v3/instances.json')
    for mode in ('full','selective'):
        records=[]
        for q in protocol['queries']:
            d=root/'ticketinfo-final'/(mode+'-'+q['id']);cap=d/'capture';plan=same_plan(d/'build','ticketinfo');record(cap/'ticketinfo/events.jsonl');run=load(cap/'run.json');assert run['status']=='business-completed' and run['cleanup_returncode']==0
            assert load(cap/'travel-inputs/database-fixtures.json')==load(BASELINE.parent/'travel-inputs/database-fixtures.json')
            graph=Reconstruction(d/'build',cap,['ticketinfo']);rows=graph.rows['ticketinfo'];checks=[]
            for c,before in zip(run['cases'],load(BASELINE)['cases']):
                assert all(c[k]==before[k] for k in ('case','request_path','request_body','http_status'))
                if c['http_status']==200:assert c['response']==before['response']
                else:assert {k:v for k,v in c['response'].items() if k!='timestamp'}=={k:v for k,v in before['response'].items() if k!='timestamp'}
                for path,value in old.leaves(c['response'],q['path']) if c['http_status']==200 else []:
                    reads=[r for r in rows if r['kind']=='http-json' and r.get('phase')=='read' and r.get('direction')=='response' and r.get('parent_message')==c['message']];assert len(reads)==1
                    read=reads[0];field=next(f for f in read['fields'] if f['path']==path);assert field['field'].startswith('@map:') and field['observed']['value']==value
                    prior=next(x for x in original_instances if x['query']==q['id'] and x['case']==c['case'] and x['path']==path)
                    assert prior['baseline_state']=='known_correct' and not prior['tf_executed'] and prior['client_value']==value
                    expected={('ticketinfo',read['seq'],path,field['owner'],field['field'],field['version'],read['message'])};answer=graph.query(c['message'],path,'ticketinfo',boundary=BOUNDARY)
                    actual={(s['service'],s['seq'],s['path'],s['owner'],s['field'],s['version'],s['message']) for s in answer['sources']};assert answer['known'] and actual==expected
                    check={'query':q['id'],'mode':mode,'case':c['case'],'path':path,'status':'known_correct','declared_target':q['target'],'actual_field':field['field'],'expected':list(next(iter(expected))),'answer':answer};instances.append(check);checks.append(check)
            assert len(checks)==7
            # Actual business evidence must fail closed, not only fixture rows.
            faults={}
            for label in ('class-literal','rpc-body','rpc-parent','getbody','missing-read','ambiguous-read','converter-version'):
                changed=copy.deepcopy(rows);read=next(r for r in changed if r['kind']=='http-json' and r.get('phase')=='read' and r.get('direction')=='response');ret=next(r for r in changed if r.get('framework_contract',{}).get('kind')=='rest-exchange')
                if label=='class-literal':next(r for r in changed if r['kind']=='execution-class-literal')['descriptor']='Ljava/lang/Object;'
                elif label=='rpc-body':ret['framework_contract']['body']['object']='same-value-wrong-response'
                elif label=='rpc-parent':read['parent_message']='wrong-request'
                elif label=='getbody':next(r for r in changed if r.get('framework_contract',{}).get('kind')=='http-entity-body')['framework_contract']['body']['object']='wrong-body'
                elif label=='missing-read':changed.remove(read)
                elif label=='ambiguous-read':changed.insert(changed.index(read),copy.deepcopy(read))
                else:ret['framework_contract']['class_sha256']['org/springframework/http/converter/xml/Jaxb2RootElementHttpMessageConverter']='wrong-version'
                try:infer_execution(plan,changed)
                except (ValueError,KeyError):faults[label]=True
                else:raise AssertionError('Invalid real TicketInfo evidence accepted: '+label)
            report=load(d/'evaluation.json');assert report['correct']==report['targets']==7 and report['wrong']==report['unknown']==0
            records.append({'query':q['id'],'targets':7,'correct':7,'tp':7,'fp':0,'fn':0,'unknown':0,'requests':8,'N/A_requests':1,'faults':faults});save(out/(mode+'-'+q['id']+'.json'),checks)
        totals[mode]={'queries':3,'entries':1,'targets':21,'correct':21,'tp':21,'fp':0,'fn':0,'unknown':0,'query_requests':24,'N/A_query_requests':3,'per_query':records}
    # Existing real business regressions, with independently authored raw-source oracles.
    loop={m:0 for m in ('full','selective')}
    for d in sorted((root/'loop-final').glob('*-trainticket-*')):
        q=load(d/'query.json');cap=d/'capture';same_plan(d/'build',q['role']);record(cap/q['role']/'events.jsonl');run=load(cap/'run.json');assert run['status']=='business-completed' and run['cleanup_returncode']==0;g=Reconstruction(d/'build',cap,[q['role']]);checks=[]
        for case in run['cases']:
            for path,value in old.leaves(case['response'],q['path']):
                a=g.query(case['message'],path,q['role'],boundary=old.BOUNDARY);expected=independent(q,case,path,g.rows[q['role']]);assert a['known'] and {old.predicted_coord(s) for s in a['sources']}==expected;checks.append(a)
        loop[run['mode']]+=len(checks)
    assert loop=={'full':60,'selective':60}
    carts={m:0 for m in ('full','selective')}
    for d in sorted((root/'cart-gaps-frozen').glob('*-sockshop-*')):
        q=load(d/'configuration-freeze.json')['query'];cap=d/'capture';same_plan(d/'build','carts');record(cap/'carts/events.jsonl');g=Reconstruction(d/'build',cap,['carts']);rows=g.rows['carts'];mode=load(d/'evaluation.json')['mode'];run=load(cap/'run.json');assert run['status']=='business-completed'
        for c in run['cases']:
            if c['http_status']!=200:continue
            ret=next(r for r in rows if r['kind']=='binding-return' and r.get('message')==c['message']);family={ret['frame']}
            for _ in range(30):family.update(r['frame'] for r in rows if r['kind']=='enter' and r.get('parent') in family)
            sources=[r for r in rows if r['kind']=='binding-source' and r.get('frame') in family and '.findByCustomerId(' in r['callee']];assert len(sources)==1
            item=c['request_path'].rsplit('/',1)[-1];index=next(i for i,x in enumerate(c['fixture']['fixture_read_items']) if x['itemId']==item)
            for path,value in old.leaves(c['response'],q['path']):
                f=next(f for f in sources[0]['fields'] if f['path']=='/0/items/'+str(index)+path);a=g.query(c['message'],path,'carts',boundary=old.BOUNDARY);assert f['observed']['value']==value and a['known'] and {old.predicted_coord(s) for s in a['sources']}=={old.source_coord('carts',sources[0],f)};carts[mode]+=1
    assert carts=={'full':15,'selective':15}
    restoration=load(root/'cart-restore-final/results.json');assert restoration['complete'] and all(r['exact']==r['known']==r['targets']==6 for r in restoration['results'])
    for mode in ('full','selective'):same_plan(root/'cart-restore-final'/mode/'build','carts');record(root/'cart-restore-final'/mode/'capture/carts/events.jsonl')
    controls={}
    for name in ('semantics-final','application-semantics-frozen','constructor-development','contracts-development'):
        d=root/name;report=load(d/'results.json');assert report['all_passed'];assert class_hashes(d/'build/distributed-observer.jar')==agent
        p=load(d/'build/fixture/plan.json');fresh=plan_response(load(d/'build/fixture/model.json'),p['entry'],p['target'],p['response_binding']['path'],execution_kernel=True,application_calls=True);assert p==fresh
        for mode in ('full','selective'):
            record(d/mode/'fixture/events.jsonl');Reconstruction(d/'build',d/mode,['fixture']);r=report['modes'][mode];assert all(r['faults'].values());controls[name+'-'+mode]={k:v for k,v in r.items() if k!='checks'}
        if name.endswith('development'):reuse.append({'capture':str(d.relative_to(ROOT)),'same_generated_plan':True,'same_all_agent_classes':True,'offline_replayed_after_final_freeze':True})
    for name in ('binding-frozen','lifecycle-frozen','collection-frozen'):assert load(root/name/'results.json')['all_passed']
    legacy=load(root/'legacy-offline-frozen/results.json');assert legacy['states']=={'known_correct':213,'unknown':88}
    bad=root/'constructor-write-control';badrows=[json.loads(s) for s in (bad/'events.jsonl').read_text().splitlines()]
    try:infer_execution(load(bad/'plan.json'),badrows)
    except ValueError as e:assert 'constructor write' in str(e)
    else:raise AssertionError('Permanent missing constructor write accepted')
    summary={'all_passed':True,'algorithm_commit':freeze['commit'],'first_algorithm_commit':load(root/'algorithm-freeze-first.json')['commit'],'ticketinfo':totals,'loop60':loop,'cart15':carts,'cart6_restore':restoration['results'],'controls':controls,'legacy_offline':legacy,'constructor_write_refused':True,'newly_fixed_baseline_gaps':21,'previously_fixed':75,'cumulative_development_repairs':96,'remaining_baseline_gaps':73,'reserved_candidates':29,'whole_62_full_selective_acceptance':False,'goal_382_of_431_met':False,'new_performance':False,'first_frozen_full':'21 unknown, no wrong; original Boot JAXB converter not yet in pinned set','source_boundary':'Actual RPC decoded response fields, unchanged task boundary; target return snapshot is never a source','replay_proof':reuse}
    save(out/'instances.json',instances);save(out/'audit.json',summary);save(out/'raw-sha256.json',raw)
    save(HERE/'ticketinfo-wrapper-results-20261020.json',summary)
    with (HERE/'ticketinfo-wrapper-instances-20261020.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['query','mode','case','path','status','declared_target','actual_field']);w.writeheader();w.writerows({k:r[k] for k in w.fieldnames} for r in instances)
    print(json.dumps({'all_passed':True,'ticketinfo':{k:v['correct'] for k,v in totals.items()},'loop60':loop,'cart15':carts,'new_repairs':21,'remaining':73,'algorithm':freeze['commit']},indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();audit(a.root.resolve(),a.out.resolve())
