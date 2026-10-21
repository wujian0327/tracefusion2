#!/usr/bin/env python3
"""Independent instance rescoring and exact capture reuse; no raw evidence writes."""
import argparse,collections,csv,json
from pathlib import Path
from run_planned_service import ROOT,HERE,load,save,sha
from plan_response_binding import plan_response
from infer_execution_kernel import infer_execution
from audit_application_call_revision import class_hashes
from run_execution_kernel_pilot import independent
import run_response_binding_revision as old
import run_sockshop_model_revision as source_model

def audit(root,out):
    out.mkdir(parents=True,exist_ok=False);freeze=load(root/'algorithm-freeze.json');base=root/'final-validation-build';agent=class_hashes(base/'distributed-observer.jar');raw={};capture_reuse={}
    assert all(sha(Path(p))==v for p,v in freeze['sources'].items());assert all(sha(base/r/'original.jar')==v for r,v in freeze['original_jars'].items())
    assert sha(HERE/'orders-foundation-protocol-20261021.json')==freeze['protocol_sha256'] and sha(HERE/'execution-kernel-protocol-20261020.json')==freeze['reserved_protocol_sha256'];assert len(load(HERE/'execution-kernel-protocol-20261020.json')['unexamined_candidates'])==29
    def record(p):raw[str(p.relative_to(ROOT))]=sha(p)
    def graph(build,cap,role):
        p=load(build/role/'plan.json');cfg=load(build/'build.json')['inputs'][role]['query_config'];fresh=plan_response(load(build/role/'model.json'),p['entry'],p['target'],p['response_binding']['path'],cfg.get('source_calls'),False,True,True)
        if p.get('source_evidence'):fresh['source_evidence']=True
        assert fresh==p and class_hashes(build/'distributed-observer.jar')==agent;record(cap/role/'events.jsonl');capture_reuse[str(build.relative_to(ROOT))]={'plan_equal':True,'all_agent_class_hashes_equal':True,'capture_build_sha256':sha(build/'build.json'),'plan_sha256':sha(build/role/'plan.json'),'scope':'Actual capture build retained; final offline-only correction replay, not another deployment.'};return old.Reconstruction(build,cap,[role])
    instances=[];orders={};blockers=[];fixtures=None
    for d in sorted((root/'business-frozen').glob('*-sockshop-*')):
        config=load(d/'configuration.json');q=config['query'];mode=config['mode'];cap=d/'capture';run=load(cap/'run.json');assert run['status']=='business-completed';current=[(c['fixture'],c['request_body'],c['message']) for c in run['cases']]
        if fixtures is None:fixtures=current
        else:assert fixtures==current
        g=graph(d/'build',cap,'orders');rows=g.rows['orders'];known=unknown=tp=fp=fn=0
        for c in run['cases']:
            if q['path']=='/date':
                from datetime import datetime,timezone
                ret=next(r for r in rows if r['kind']=='binding-return' and r.get('message')==c['message']);f=next(f for f in ret['fields'] if f['path']=='/date');calls={r['call_id']:r for r in rows if r['kind']=='collection-call-enter' and r.get('frame')==ret['frame']};clock=[r for r in rows if r['kind']=='collection-call-exit' and r.get('call_id') in calls and calls[r['call_id']]['callee']=='java/util/Calendar.getTime()Ljava/util/Date;'];assert len(clock)==1 and clock[0]['result']==f['observed'];t=datetime.strptime(c['response']['date'],'%Y-%m-%dT%H:%M:%S.%f%z');delta=t.astimezone(timezone.utc)-datetime(1970,1,1,tzinfo=timezone.utc);assert delta.days*86400000+delta.seconds*1000+t.microsecond//1000==f['observed']['date_epoch_ms'];want=set()
            else:want={tuple(x) for x in source_model.oracle(q,c,q['path'],{'orders':rows})}
            a=g.query(c['message'],q['path'],'orders',boundary=old.BOUNDARY);actual={old.predicted_coord(s) for s in a['sources']} if a['known'] else set()
            if a['known']:assert actual==want;known+=1
            else:unknown+=1
            tp+=len(actual&want);fp+=len(actual-want);fn+=len(want-actual)
            instances.append({'query':q['id'],'mode':mode,'case':c['case'],'path':q['path'],'status':'correct' if a['known'] else 'unknown','expected':sorted(want,key=str),'answer':a})
        counts=collections.Counter(call['callee'] for r in g.local_queries['orders']['roots'] for call in r.get('opaque_calls',[]));blockers.append({'query':q['id'],'mode':mode,'executed_opaque_calls':dict(counts),'scope':'Executed opaque effects, not a minimal causal slice.'});orders[mode+'-'+q['id']]={'targets':len(run['cases']),'known_exact':known,'unknown':unknown,'wrong':0,'evidence_invalid':0,'oracle_unavailable':0,'answerability':known/len(run['cases']),'known_exact_rate':1.0 if known else None,'tp':tp,'fp':fp,'fn_including_unknown_positive':fn}
    assert len(orders)==4 and all(r['targets']==6 for r in orders.values())
    assert load(root/'business-frozen/cleanup.json')['status']=='completed' and load(root/'business-frozen/cleanup.json')['cleanup_returncode']==0
    pair={}
    for mode in ('full','selective'):
        d=root/'cart-pair-frozen'/mode;cap=d/'capture';g=graph(d/'build',cap,'carts');rows=g.rows['carts'];cases=load(cap/'run.json')['cases'];assert len(cases)==2
        for index,c in enumerate(cases):
            assert c['customerId']=='56e8f576709b70d0ace01fb0' and c['created']==(index==0);ret=next(r for r in rows if r['kind']=='binding-return' and r.get('message')==c['message']);family={ret['frame']}
            for _ in range(40):family.update(r['frame'] for r in rows if r['kind']=='enter' and r.get('parent') in family)
            sources=[r for r in rows if r['kind']=='binding-source' and r.get('frame') in family and '.findByCustomerId(' in r['callee']];assert len(sources)==1;source=sources[0];f=next(f for f in source['fields'] if f['path']=='/0/customerId');calls=[r for r in rows if r['kind']=='collection-call-enter' and r.get('frame') in family and r['callee']==source['callee']];assert len(calls)==(2 if index==0 else 1);end=next(r for r in rows if r['kind']=='collection-call-exit' and r.get('call_id')==calls[-1]['call_id']);assert calls[-1]['seq']<source['seq']<end['seq'];a=g.query(c['message'],'/customerId','carts',boundary=old.BOUNDARY);assert a['known'] and {old.predicted_coord(s) for s in a['sources']}=={old.source_coord('carts',source,f)}
        pair[mode]=2
    loops={m:0 for m in pair}
    for d in sorted((root/'loop-frozen').glob('*-trainticket-*')):
        q=load(d/'query.json');cap=d/'capture';g=graph(d/'build',cap,q['role']);run=load(cap/'run.json')
        for c in run['cases']:
            for path,value in old.leaves(c['response'],q['path']):
                a=g.query(c['message'],path,q['role'],boundary=old.BOUNDARY);assert a['known'] and {old.predicted_coord(s) for s in a['sources']}==independent(q,c,path,g.rows[q['role']]);loops[run['mode']]+=1
    assert loops=={'full':60,'selective':60}
    carts={m:0 for m in pair}
    for d in sorted((root/'cart-gaps-frozen-final').glob('*-sockshop-*')):
        q=load(d/'configuration-freeze.json')['query'];cap=d/'capture';g=graph(d/'build',cap,'carts');rows=g.rows['carts'];mode=load(d/'evaluation.json')['mode']
        for c in load(cap/'run.json')['cases']:
            if c['http_status']!=200:continue
            ret=next(r for r in rows if r['kind']=='binding-return' and r.get('message')==c['message']);family={ret['frame']}
            for _ in range(40):family.update(r['frame'] for r in rows if r['kind']=='enter' and r.get('parent') in family)
            sources=[r for r in rows if r['kind']=='binding-source' and r.get('frame') in family and '.findByCustomerId(' in r['callee']];assert len(sources)==1;source=sources[0];index=next(i for i,x in enumerate(c['fixture']['fixture_read_items']) if x['itemId']==c['request_path'].rsplit('/',1)[-1])
            for path,value in old.leaves(c['response'],q['path']):
                f=next(f for f in source['fields'] if f['path']=='/0/items/'+str(index)+path);a=g.query(c['message'],path,'carts',boundary=old.BOUNDARY);assert a['known'] and {old.predicted_coord(s) for s in a['sources']}=={old.source_coord('carts',source,f)};carts[mode]+=1
    assert carts=={'full':15,'selective':15}
    restore={m:0 for m in pair}
    for mode in pair:
        d=root/'cart-restore-frozen'/mode;cap=d/'capture';g=graph(d/'build',cap,'carts');rows=g.rows['carts'];q=load(d/'configuration-freeze.json')['query']
        for c in load(cap/'run.json')['cases']:
            source=next(r for r in rows if r['kind']=='binding-source' and r.get('message')==c['message'] and '.findByCustomerId(' in r['callee'])
            for path,value in old.leaves(c['response'],q['path']):
                f=next(f for f in source['fields'] if f['path']=='/0/items'+path);a=g.query(c['message'],path,'carts',boundary=old.BOUNDARY);assert a['known'] and {old.predicted_coord(s) for s in a['sources']}=={old.source_coord('carts',source,f)};restore[mode]+=1
    assert restore=={'full':6,'selective':6}
    ticket={m:0 for m in pair}
    for d in sorted((root/'ticketinfo-frozen').glob('*-trainticket-*')):
        config=load(d/'configuration.json');q=config['query'];mode=config['mode'];cap=d/'capture';g=graph(d/'build',cap,'ticketinfo');rows=g.rows['ticketinfo']
        for c in load(cap/'run.json')['cases']:
            for path,value in old.leaves(c['response'],q['path']) if c['http_status']==200 else []:
                reads=[r for r in rows if r['kind']=='http-json' and r.get('phase')=='read' and r.get('direction')=='response' and r.get('parent_message')==c['message']];assert len(reads)==1;f=next(f for f in reads[0]['fields'] if f['path']==path);a=g.query(c['message'],path,'ticketinfo',boundary=[{'kind':'http-json','phase':'read','direction':'response'}]);assert a['known'] and {(s['seq'],s['path'],s['owner'],s['field'],s['version'],s['message']) for s in a['sources']}=={(reads[0]['seq'],path,f['owner'],f['field'],f['version'],reads[0]['message'])};ticket[mode]+=1
    assert ticket=={'full':21,'selective':21}
    controls={}
    for name in ('semantics-development-07','reread-development','date-development','opaque-date-final','application-frozen','constructor-frozen'):
        report=load(root/name/'results.json');assert report['all_passed'];controls[name]={}
        for mode,row in report['modes'].items():
            cap=root/name/mode;g=graph(root/name/'build',cap,'fixture');rows=g.rows['fixture']
            for c in row['checks']:
                target=c['answer']['target'] if 'answer' in c else None
                if target is None:continue
                a=g.query(target['message'],target['path'],'fixture',boundary=old.BOUNDARY)
                if name=='semantics-development-07':
                    want=c['expected_arguments'];assert a['known']==(want is not None)
                    if want is not None:
                        truth=set()
                        for index in want:
                            source=next(r for r in rows if r['kind']=='binding-input' and r.get('message')==target['message'] and r['argument']==index);f=next(f for f in source['fields'] if f['field']=='OrdersFoundationFixture$Item.text');truth.add(old.source_coord('fixture',source,f))
                        assert {old.predicted_coord(s) for s in a['sources']}==truth
                elif name=='opaque-date-final':
                    assert a['known']==c['expected_known']
                    if a['known']:assert len(a['sources'])==1 and a['sources'][0]['field']=='@argument:0' and a['sources'][0]['observed']['date_epoch_ms']==1000
                else:assert a['known']==c['answer']['known'] and {old.predicted_coord(s) for s in a['sources']}=={old.predicted_coord(s) for s in c['answer']['sources']}
            assert all(row.get('faults',{'none':True}).values());controls[name][mode]={k:v for k,v in row.items() if k!='checks'}
    collection=load(root/'collection-frozen/results.json');assert collection['all_passed'];legacy=load(root/'legacy-offline-final/results.json');assert legacy['states']=={'known_correct':213,'unknown':88};reuse=load(root/'control-reuse.json');assert all(v['plan_equal'] and v['all_agent_classes_equal'] for v in reuse.values())
    witness=root/'constructor-write-control';record(witness/'events.jsonl')
    try:infer_execution(load(witness/'plan.json'),[json.loads(s) for s in (witness/'events.jsonl').read_text().splitlines()])
    except ValueError as e:assert 'constructor write' in str(e)
    else:raise AssertionError('Permanent missing constructor write accepted')
    summary={'all_passed':True,'algorithm_commit':freeze['commit'],'capture_commit':freeze['capture_commit'],'orders':orders,'cart_original_pair':pair,'cart15':carts,'cart6_restore':restore,'loop60':loops,'ticketinfo21':ticket,'controls':controls,'collection_controls':collection['profiles'],'control_reuse':reuse,'legacy_offline':legacy,'new_real_baseline_repairs':0,'cumulative_development_repairs':97,'remaining_baseline_gaps':72,'reserved_candidates':29,'whole_62_full_selective_acceptance':False,'new_performance':False,'evaluator_sha256':sha(Path(__file__))}
    save(out/'audit.json',summary);save(out/'raw-sha256.json',raw);save(out/'capture-reuse.json',capture_reuse);save(out/'orders-instances.json',instances);save(out/'executed-opaque-calls.json',blockers);save(HERE/'orders-foundation-results-20261021.json',summary)
    with (HERE/'orders-foundation-instances-20261021.csv').open('w',newline='') as f:
        keys=['query','mode','case','path','status'];w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows({k:r[k] for k in keys} for r in instances)
    print(json.dumps({'all_passed':True,'orders':orders,'new_repairs':0,'remaining':72},indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();audit(a.root.resolve(),a.out.resolve())
