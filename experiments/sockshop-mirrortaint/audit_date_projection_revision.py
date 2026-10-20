#!/usr/bin/env python3
"""New-directory audit of Date state, conservative business answers and compatibility."""
import argparse,copy,csv,json
from pathlib import Path
from datetime import datetime,timezone
from run_planned_service import ROOT,HERE,load,save,sha
from infer_distributed_fields import Reconstruction
from infer_execution_kernel import infer_execution
from plan_response_binding import plan_response
from audit_application_call_revision import class_hashes
from run_execution_kernel_pilot import independent
import run_response_binding_revision as old

def audit(root,out):
    out.mkdir(parents=True,exist_ok=False);freeze=load(root/'algorithm-freeze.json');base=root/'final-base-build';agent=class_hashes(base/'distributed-observer.jar');raw={}
    assert all(sha(Path(p))==v for p,v in freeze['sources'].items())
    assert all(sha(base/r/'original.jar')==v for r,v in freeze['original_jars'].items())
    assert sha(HERE/'date-projection-protocol-20261020.json')==freeze['protocol_sha256']
    assert sha(HERE/'execution-kernel-protocol-20261020.json')==freeze['reserved_protocol_sha256'] and len(load(HERE/'execution-kernel-protocol-20261020.json')['unexamined_candidates'])==29
    def record(p):raw[str(p.relative_to(ROOT))]=sha(p)
    def plan_equal(build,role,kernel=True):
        p=load(build/role/'plan.json');model=load(build/role/'model.json');fresh=plan_response(model,p['entry'],p['target'],p['response_binding']['path'],execution_kernel=kernel,application_calls=kernel)
        assert p==fresh and class_hashes(build/'distributed-observer.jar')==agent;return p
    q=load(HERE/'date-projection-protocol-20261020.json')['query'];orders={};instances=[];blockers=[]
    for mode in ('full','selective'):
        d=root/'orders-frozen'/mode;plan=plan_equal(d/'build','orders',False);cap=d/'capture';record(cap/'orders/events.jsonl');g=Reconstruction(d/'build',cap,['orders']);rows=g.rows['orders'];cases=load(cap/'run.json')['cases'];checks=[]
        for case in cases:
            ret=next(r for r in rows if r['kind']=='binding-return' and r.get('message')==case['message']);field=next(f for f in ret['fields'] if f['path']=='/date');observed=field['observed'];clock=[r for r in rows if r['kind']=='date-call' and r.get('frame')==ret['frame'] and r['callee']=='java/util/Calendar.getTime()Ljava/util/Date;'];assert len(clock)==1 and clock[0]['result']==observed
            # The initializer and explicit date constructor argument are distinct
            # actual writes. The latter must win, even within the same millisecond.
            writes=[r for r in rows if r['kind']=='write' and r.get('frame')==ret['frame'] and r['owner']==field['owner'] and r['field']==field['field']];assert len(writes)==2 and [w['version'] for w in writes]==[1,2] and writes[-1]['observed']==observed and writes[0]['observed']['object']!=observed['object']
            instant=datetime.strptime(case['response']['date'],'%Y-%m-%dT%H:%M:%S.%f%z');delta=instant.astimezone(timezone.utc)-datetime(1970,1,1,tzinfo=timezone.utc);assert delta.days*86400000+delta.seconds*1000+instant.microsecond//1000==observed['date_epoch_ms']
            a=g.query(case['message'],'/date','orders',boundary=old.BOUNDARY);assert not a['known'];summary=next(r for r in rows if r['kind']=='binding-call-summary' and r.get('frame')==ret['frame']);assert not summary['root_effects_verified']
            touched=[{'seq':r['seq'],'callee':r['callee'],'mode':r['mode']} for r in rows if r.get('frame')==ret['frame'] and r['kind']=='binding-call-exit' and not r['valid'] and any(f['owner']==field['owner'] and f['field']==field['field'] for f in r['detail'].get('effect_fields',[]))]
            assert any('.save(' in v['callee'] for v in touched) and any('.toString(' in v['callee'] for v in touched)
            entry={'query':q['id'],'mode':mode,'case':case['case'],'path':'/date','status':'unknown','expected_field_sources':[],'environment_producer':clock[0]['seq'],'target':field,'answer':a};checks.append(entry);instances.append(entry);blockers.append({'mode':mode,'case':case['case'],'first_unresolved_target_touch':touched[0],'unresolved_target_effects':touched})
        assert len(checks)==6
        # Missing Date runtime or inconsistent serialization must still invalidate.
        faults={}
        for label in ('runtime','wire','serializer','same-epoch-other-object','root-proof'):
            changed=copy.deepcopy(rows)
            if label=='runtime':next(r for r in changed if r['kind']=='date-runtime')['class_sha256']={}
            elif label=='wire':next(r for r in changed if r['kind']=='date-serialization')['wire_value']='1970-01-01T00:00:00.000+0000'
            elif label=='serializer':next(r for r in changed if r['kind']=='date-serialization')['class_sha256']={}
            elif label=='same-epoch-other-object':next(r for r in changed if r['kind']=='binding-return')['fields'][0]['observed']['object']='wrong-date-same-time'
            else:next(r for r in changed if r['kind']=='binding-call-summary')['root_effects_verified']=True
            from infer_date_projection import validate_date_serialization
            from infer_response_binding import audit_read_effects,bind_outputs
            try:
                validate_date_serialization(plan,changed);audit_read_effects(changed,plan)
                if label=='same-epoch-other-object':
                    # The full graph uses decoded_rows so sequence and closed capture
                    # still apply; no source values are guessed after perturbation.
                    Reconstruction(d/'build',cap,['orders'],decoded_rows={'orders':changed})
            except (ValueError,KeyError):faults[label]=True
            else:raise AssertionError('Date business evidence not protected: '+label)
        orders[mode]={'targets':6,'known':0,'unknown':6,'evidence_invalid':0,'oracle_unavailable':0,'N/A_requests':0,'answerability':0,'known_exact_rate':None,'relationship_metrics':None,'faults':faults};save(out/('orders-'+mode+'.json'),checks)
    a=load(root/'orders-frozen/full/capture/run.json')['cases'];b=load(root/'orders-frozen/selective/capture/run.json')['cases'];assert all(x['fixture']==y['fixture'] and x['request_body']==y['request_body'] and x['message']==y['message'] for x,y in zip(a,b))
    assert load(root/'orders-frozen/cleanup.json')['status']=='completed' and load(root/'orders-frozen/cleanup.json')['cleanup_returncode']==0
    semantics={}
    for name in ('semantics-frozen','arguments-frozen','forward-frozen'):
        d=root/name;report=load(d/'results.json');assert report['all_passed'];plan=load(d/'build/fixture/plan.json');plan_equal(d/'build','fixture',name!='forward-frozen')
        for mode,r in report['modes'].items():
            cap=d/mode;record(cap/'fixture/events.jsonl');g=Reconstruction(d/'build',cap,['fixture']);rows=g.rows['fixture']
            for c in r['checks']:
                case=c['case'];answer=g.query(case['message'],'/date','fixture',boundary=old.BOUNDARY)
                if name=='semantics-frozen':
                    want=c['expected'];assert answer['known']==(want is not None)
                    if want is not None:
                        expected=set()
                        if want:
                            source=next(x for x in rows if x['kind']=='binding-input' and x.get('message')==case['message'] and x['argument']==want[0]);f=next(f for f in source['fields'] if f['field']=='DateProjectionFixture$Input.'+want[1]);expected={old.source_coord('fixture',source,f)}
                        assert {old.predicted_coord(s) for s in answer['sources']}==expected
                elif name=='arguments-frozen':assert answer['known'] and len(answer['sources'])==1 and answer['sources'][0]['field']=='@argument:'+str(case['argument'])
                else:assert answer['known']==(case['mode']==0)
            if 'faults' in r:assert all(r['faults'].values())
            semantics[name+'-'+mode]={k:v for k,v in r.items() if k!='checks'}
        if name=='semantics-frozen':assert all(report['custom_serialization_refused'].values())
    loop={m:0 for m in ('full','selective')}
    for d in sorted((root/'loop-frozen').glob('*-trainticket-*')):
        ql=load(d/'query.json');cap=d/'capture';plan_equal(d/'build',ql['role']);record(cap/ql['role']/'events.jsonl');run=load(cap/'run.json');assert run['status']=='business-completed';g=Reconstruction(d/'build',cap,[ql['role']])
        for c in run['cases']:
            for path,value in old.leaves(c['response'],ql['path']):
                answer=g.query(c['message'],path,ql['role'],boundary=old.BOUNDARY);assert answer['known'] and {old.predicted_coord(s) for s in answer['sources']}==independent(ql,c,path,g.rows[ql['role']]);loop[run['mode']]+=1
    assert loop=={'full':60,'selective':60}
    carts={m:0 for m in ('full','selective')}
    for d in sorted((root/'cart-gaps-frozen').glob('*-sockshop-*')):
        qc=load(d/'configuration-freeze.json')['query'];cap=d/'capture';plan_equal(d/'build','carts');record(cap/'carts/events.jsonl');run=load(cap/'run.json');g=Reconstruction(d/'build',cap,['carts']);rows=g.rows['carts'];mode=load(d/'evaluation.json')['mode']
        for c in run['cases']:
            if c['http_status']!=200:continue
            ret=next(r for r in rows if r['kind']=='binding-return' and r.get('message')==c['message']);family={ret['frame']}
            for _ in range(30):family.update(r['frame'] for r in rows if r['kind']=='enter' and r.get('parent') in family)
            sources=[r for r in rows if r['kind']=='binding-source' and r.get('frame') in family and '.findByCustomerId(' in r['callee']];assert len(sources)==1;index=next(i for i,x in enumerate(c['fixture']['fixture_read_items']) if x['itemId']==c['request_path'].rsplit('/',1)[-1])
            for path,value in old.leaves(c['response'],qc['path']):
                f=next(f for f in sources[0]['fields'] if f['path']=='/0/items/'+str(index)+path);answer=g.query(c['message'],path,'carts',boundary=old.BOUNDARY);assert answer['known'] and {old.predicted_coord(s) for s in answer['sources']}=={old.source_coord('carts',sources[0],f)};carts[mode]+=1
    assert carts=={'full':15,'selective':15}
    ticket={m:0 for m in ('full','selective')}
    for d in sorted((root/'ticketinfo-frozen').glob('*-trainticket-*')):
        cap=d/'capture';plan_equal(d/'build','ticketinfo');record(cap/'ticketinfo/events.jsonl');g=Reconstruction(d/'build',cap,['ticketinfo']);q=load(d/'configuration.json')['query'];mode=load(d/'configuration.json')['mode']
        for c in load(cap/'run.json')['cases']:
            for path,value in old.leaves(c['response'],q['path']) if c['http_status']==200 else []:
                reads=[r for r in g.rows['ticketinfo'] if r['kind']=='http-json' and r.get('phase')=='read' and r.get('direction')=='response' and r.get('parent_message')==c['message']];assert len(reads)==1;f=next(f for f in reads[0]['fields'] if f['path']==path);a=g.query(c['message'],path,'ticketinfo',boundary=[{'kind':'http-json','direction':'response','phase':'read'}]);assert a['known'] and len(a['sources'])==1 and all(a['sources'][0][k]==f[k] for k in ('owner','field','version')) and a['sources'][0]['seq']==reads[0]['seq'];ticket[mode]+=1
    assert ticket=={'full':21,'selective':21}
    restore=load(root/'cart-restore-frozen/results.json');assert restore['complete'] and all(r['exact']==r['known']==r['targets']==6 for r in restore['results'])
    for mode in ('full','selective'):plan_equal(root/'cart-restore-frozen'/mode/'build','carts');record(root/'cart-restore-frozen'/mode/'capture/carts/events.jsonl')
    controls={}
    for name in ('constructor-frozen','contracts-frozen','application-frozen','binding-frozen','lifecycle-frozen'):
        r=load(root/name/'results.json');assert r['all_passed'];controls[name]={k:v for k,v in r.items() if k not in ('cases','modes')}
    legacy=load(root/'legacy-offline-frozen/results.json');assert legacy['states']=={'known_correct':213,'unknown':88}
    witness=root/'constructor-write-control';record(witness/'events.jsonl');badrows=[json.loads(s) for s in (witness/'events.jsonl').read_text().splitlines()]
    try:infer_execution(load(witness/'plan.json'),badrows)
    except ValueError as e:assert 'constructor write' in str(e)
    else:raise AssertionError('Historical missing constructor write accepted')
    summary={'all_passed':True,'algorithm_commit':freeze['commit'],'date_business':orders,'date_semantics':semantics,'loop60':loop,'cart15':carts,'ticketinfo21':ticket,'cart6_restore':restore['results'],'legacy_offline':legacy,'legacy_controls':controls,'new_real_baseline_repairs':0,'cumulative_development_repairs':96,'remaining_baseline_gaps':73,'reserved_candidates':29,'whole_62_full_selective_acceptance':False,'new_performance':False,'date_boundary':'Empty field-source projection for original clock-generated date; not constant or a complete environmental provenance answer. Unknown targets are not correct empty answers.','input_identity':'New legal IDs per frozen suite; same actual inputs between modes; original six business structures and item values retained.'}
    save(out/'audit.json',summary);save(out/'raw-sha256.json',raw);save(out/'date-instances.json',instances);save(out/'date-blockers.json',blockers);save(HERE/'date-projection-results-20261020.json',summary)
    with (HERE/'date-projection-instances-20261020.csv').open('w',newline='') as f:
        keys=['query','mode','case','path','status'];w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows({k:r[k] for k in keys} for r in instances)
    print(json.dumps({'all_passed':True,'date':orders,'loop':loop,'cart':carts,'ticketinfo':ticket,'new_real_repairs':0,'remaining':73},indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();audit(a.root.resolve(),a.out.resolve())
