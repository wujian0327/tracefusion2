#!/usr/bin/env python3
"""Recompute concrete read-instance truth into a new directory; keep captures immutable."""
import argparse,copy,csv,json
from pathlib import Path
from run_planned_service import ROOT,HERE,load,save,sha
from plan_response_binding import plan_response
from infer_execution_kernel import infer_execution
from audit_application_call_revision import class_hashes
from run_execution_kernel_pilot import independent
import run_response_binding_revision as old

def audit(root,out):
    out.mkdir(parents=True,exist_ok=False);freeze=load(root/'algorithm-freeze.json');base=root/'final-base-build';agent=class_hashes(base/'distributed-observer.jar');raw={}
    assert all(sha(Path(p))==v for p,v in freeze['sources'].items())
    assert all(sha(base/r/'original.jar')==v for r,v in freeze['original_jars'].items())
    assert sha(HERE/'cart-reread-protocol-20261021.json')==freeze['protocol_sha256']
    assert sha(HERE/'execution-kernel-protocol-20261020.json')==freeze['reserved_protocol_sha256'] and len(load(HERE/'execution-kernel-protocol-20261020.json')['unexamined_candidates'])==29
    def record(p):raw[str(p.relative_to(ROOT))]=sha(p)
    def replay(build,cap,role):
        p=load(build/role/'plan.json');fresh=plan_response(load(build/role/'model.json'),p['entry'],p['target'],p['response_binding']['path'],execution_kernel=True,application_calls=True)
        assert fresh==p and class_hashes(build/'distributed-observer.jar')==agent
        record(cap/role/'events.jsonl');return old.Reconstruction(build,cap,[role])
    instances=[];business={}
    for mode in ('full','selective'):
        d=root/'business-frozen'/mode;cap=d/'capture';g=replay(d/'build',cap,'carts');rows=g.rows['carts'];run=load(cap/'run.json');assert run['status']=='business-completed';faults={}
        for c in run['cases']:
            ret=next(r for r in rows if r['kind']=='binding-return' and r.get('message')==c['message']);family={ret['frame']}
            while True:
                new=family|{r['frame'] for r in rows if r['kind']=='enter' and r.get('parent') in family}
                if new==family:break
                family=new
            sources=[r for r in rows if r['kind']=='binding-source' and r.get('frame') in family and '.findByCustomerId(' in r['callee']];assert len(sources)==1;source=sources[0]
            f=next(f for f in source['fields'] if f['path']=='/0/customerId');target=next(f for f in ret['fields'] if f['path']=='/customerId');assert f['owner']==target['owner'] and f['version']==target['version'] and f['observed']['value']==c['customerId']
            calls=[r for r in rows if r['kind']=='collection-call-enter' and r.get('frame') in family and r['callee']==source['callee']];ordinal=2 if c['created'] else 1;assert len(calls)==ordinal
            call=calls[-1];completion=next(r for r in rows if r['kind']=='collection-call-exit' and r.get('call_id')==call['call_id']);assert call['seq']<source['seq']<completion['seq']
            a=g.query(c['message'],'/customerId','carts',boundary=old.BOUNDARY);assert a['known'] and {old.predicted_coord(s) for s in a['sources']}=={old.source_coord('carts',source,f)}
            if c['created']:
                save_calls=[r for r in rows if r['kind']=='collection-call-exit' and r.get('frame') in family and '.save(' in r['callee']];assert len(save_calls)==1
                birth=next(r for r in rows if r['kind']=='execution-object-birth' and r['object']==f['owner']);assert save_calls[0]['seq']<call['seq']<birth['seq']<source['seq']
                saved=save_calls[0]['result']['object'];assert saved!=f['owner'],'Saved and reread entities must be distinct in this protocol'
            instances.append({'mode':mode,'request':c['index'],'created':c['created'],'scope':'original-challenge' if c['index']<2 else 'extra-guard','status':'correct','read_ordinal':ordinal,'expected':old.source_coord('carts',source,f),'answer':a})
        # The first-created target loses its certainty if allocation evidence is
        # absent. Existing-cart target remains answerable in its separate root.
        c=run['cases'][0];ret=next(r for r in rows if r['kind']=='binding-return' and r.get('message')==c['message']);owner=next(f for f in ret['fields'] if f['path']=='/customerId')['owner']
        for label in ('missing-birth','wrong-birth-owner','wrong-birth-frame','wrong-birth-hash','duplicate-birth','missing-reread-source','ambiguous-reread-source'):
            changed=copy.deepcopy(rows);birth=next(r for r in changed if r['kind']=='execution-object-birth' and r['object']==owner)
            if label=='missing-birth':changed.remove(birth)
            elif label=='wrong-birth-owner':birth['object']='same-value-wrong-object'
            elif label=='wrong-birth-frame':birth['frame']='wrong-frame'
            elif label=='wrong-birth-hash':birth['class_sha256']='wrong'
            elif label=='duplicate-birth':changed.insert(changed.index(birth)+1,dict(birth))
            else:
                source=next(r for r in changed if r['kind']=='binding-source' and any(f['owner']==owner for f in r['fields']))
                if label=='missing-reread-source':changed.remove(source)
                else:changed.insert(changed.index(source)+1,copy.deepcopy(source))
            try:
                answers=infer_execution(g.plans['carts'],changed)['answers'];assert not next(a for a in answers if a['seq']==ret['seq'] and a['path']=='/customerId')['known'];faults[label]='unknown'
            except (ValueError,KeyError):faults[label]='refused'
        business[mode]={'targets':len(run['cases']),'known_exact':len(run['cases']),'unknown':0,'wrong':0,'evidence_invalid':0,'oracle_unavailable':0,'tp':len(run['cases']),'fp':0,'fn':0,'creation_requests':sum(c['created'] for c in run['cases']),'faults':faults}
    loops={m:0 for m in ('full','selective')}
    for d in sorted((root/'loop-frozen').glob('*-trainticket-*')):
        q=load(d/'query.json');cap=d/'capture';g=replay(d/'build',cap,q['role']);run=load(cap/'run.json');assert run['status']=='business-completed'
        for c in run['cases']:
            for path,value in old.leaves(c['response'],q['path']):
                a=g.query(c['message'],path,q['role'],boundary=old.BOUNDARY);assert a['known'] and {old.predicted_coord(s) for s in a['sources']}==independent(q,c,path,g.rows[q['role']]);loops[run['mode']]+=1
    assert loops=={'full':60,'selective':60}
    carts={m:0 for m in ('full','selective')}
    for d in sorted((root/'cart-gaps-frozen').glob('*-sockshop-*')):
        q=load(d/'configuration-freeze.json')['query'];cap=d/'capture';g=replay(d/'build',cap,'carts');rows=g.rows['carts'];mode=load(d/'evaluation.json')['mode']
        for c in load(cap/'run.json')['cases']:
            if c['http_status']!=200:continue
            ret=next(r for r in rows if r['kind']=='binding-return' and r.get('message')==c['message']);family={ret['frame']}
            for _ in range(30):family.update(r['frame'] for r in rows if r['kind']=='enter' and r.get('parent') in family)
            source=next(r for r in rows if r['kind']=='binding-source' and r.get('frame') in family and '.findByCustomerId(' in r['callee']);index=next(i for i,x in enumerate(c['fixture']['fixture_read_items']) if x['itemId']==c['request_path'].rsplit('/',1)[-1])
            for path,value in old.leaves(c['response'],q['path']):
                f=next(f for f in source['fields'] if f['path']=='/0/items/'+str(index)+path);a=g.query(c['message'],path,'carts',boundary=old.BOUNDARY);assert a['known'] and {old.predicted_coord(s) for s in a['sources']}=={old.source_coord('carts',source,f)};carts[mode]+=1
    assert carts=={'full':15,'selective':15}
    ticket={m:0 for m in ('full','selective')}
    for d in sorted((root/'ticketinfo-frozen').glob('*-trainticket-*')):
        cap=d/'capture';g=replay(d/'build',cap,'ticketinfo');q=load(d/'configuration.json')['query'];mode=load(d/'configuration.json')['mode'];rows=g.rows['ticketinfo']
        for c in load(cap/'run.json')['cases']:
            for path,value in old.leaves(c['response'],q['path']) if c['http_status']==200 else []:
                reads=[r for r in rows if r['kind']=='http-json' and r.get('phase')=='read' and r.get('direction')=='response' and r.get('parent_message')==c['message']];assert len(reads)==1;f=next(f for f in reads[0]['fields'] if f['path']==path);a=g.query(c['message'],path,'ticketinfo',boundary=[{'kind':'http-json','phase':'read','direction':'response'}]);assert a['known'] and {(s['seq'],s['path'],s['owner'],s['field'],s['version'],s['message']) for s in a['sources']}=={(reads[0]['seq'],path,f['owner'],f['field'],f['version'],reads[0]['message'])};ticket[mode]+=1
    assert ticket=={'full':21,'selective':21}
    restore=load(root/'cart-restore-frozen/results.json');assert restore['complete'] and all(r['exact']==6 and r['unknown']==0 for r in restore['results'])
    controls={}
    for name in ('semantics-frozen','application-frozen','constructor-frozen'):
        report=load(root/name/'results.json');assert report['all_passed'];controls[name]={}
        for mode,row in report['modes'].items():
            cap=root/name/mode;record(cap/'fixture/events.jsonl');g=old.Reconstruction(root/name/'build',cap,['fixture']);assert class_hashes(root/name/'build/distributed-observer.jar')==agent;assert all(row['faults'].values());controls[name][mode]={k:v for k,v in row.items() if k!='checks'}
    legacy=load(root/'legacy-offline-frozen/results.json');assert legacy['states']=={'known_correct':213,'unknown':88}
    summary={'all_passed':True,'algorithm_commit':freeze['commit'],'cart_reread':business,'loop60':loops,'cart15':carts,'ticketinfo21':ticket,'cart6_restore':restore['results'],'controls':controls,'legacy_offline':legacy,'new_real_baseline_repairs':1,'cumulative_development_repairs':97,'remaining_baseline_gaps':72,'reserved_candidates':29,'whole_62_full_selective_acceptance':False,'new_performance':False,'scope':'Cart source is actual second repository read after opaque save. No save purity, Orders or unseen-query claim.'}
    save(out/'audit.json',summary);save(out/'raw-sha256.json',raw);save(out/'instances.json',instances);save(HERE/'cart-reread-results-20261021.json',summary)
    with (HERE/'cart-reread-instances-20261021.csv').open('w',newline='') as f:
        keys=['mode','request','created','scope','status','read_ordinal'];w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows({k:r[k] for k in keys} for r in instances)
    print(json.dumps({'all_passed':True,'cart':business,'repairs':1,'remaining':72},indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();audit(a.root.resolve(),a.out.resolve())
