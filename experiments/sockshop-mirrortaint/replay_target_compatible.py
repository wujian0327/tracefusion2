"""Reconstruct compatible captures; reuse only their independent oracle cache.

Prior predictions/graphs are not an oracle. Expected coordinates came from
already frozen independent rules and the SAME immutable JVM capture. New or
changed-plan executions must instead run the normal independent scoring driver.
"""
import argparse
from collections import Counter
from pathlib import Path
from run_planned_service import ROOT,load,save,sha


def replay(root,reference,out):
    out.mkdir(parents=True,exist_ok=False)
    from infer_distributed_fields import Reconstruction
    import run_response_binding_revision as old
    from normalize_orders_origins import source_coordinate
    from audit_application_call_revision import class_hashes
    expected_agent=class_hashes(root/'historical/frozen-base/distributed-observer.jar')
    folders=['all62-orders-serial','all62-reads','all62-route','all62-travel','all62-cart',
             'regression29-orders','regression29-train','development-route-frozen','development-price-frozen']
    rows=[];receipts=[]
    for folder in folders:
        for ev_path in sorted((reference/'historical'/folder).glob('*/evaluation.json')):
            ev=load(ev_path)
            if not isinstance(ev,dict)or not ev.get('predictions'):continue
            d=ev_path.parent;qid=ev['query'];qsets=['frozen-plans','regression29-plans','write-plans']
            candidates=[root/'historical'/s/(qid+'.json')for s in qsets if(root/'historical'/s/(qid+'.json')).exists()]
            assert candidates
            role=next(p.parent.name for p in(d/'build').glob('*/plan.json')if load(p).get('entry')==load(candidates[0])['entry']and load(p).get('target')==load(candidates[0])['target'])
            before_plan=d/'build'/role/'plan.json';after_plan=candidates[0]
            if sha(before_plan)!=sha(after_plan):
                receipts.append({'evaluation':str(ev_path),'compatible':False,'requires_new_capture':True});continue
            assert class_hashes(d/'build/distributed-observer.jar')==expected_agent
            cap=d/'capture'/role/'events.jsonl';digest=sha(cap)
            # Materialize an oracle-only cache: do not copy answer, actual,
            # inferred edges, or native tags into it.
            truth=[{k:t[k]for k in('case','path','message','expected','oracle_error')if k in t}for t in ev['predictions']]
            stem=folder+'--'+d.name;save(out/(stem+'-independent-oracle-cache.json'),truth)
            g=Reconstruction(d/'build',d/'capture',[role]);current=[]
            for t,w in zip(ev['predictions'],truth):
                a=g.query(w['message'],w['path'],role,boundary=old.BOUNDARY)
                want=set(map(tuple,w['expected']))if w.get('expected')is not None else None
                got={source_coordinate(role,s,g.rows[role])if role=='orders'else old.predicted_coord(s)for s in a['sources']}
                state=('known_correct'if got==want else'known_wrong')if a['known']and want is not None else'known_unchecked'if a['known']else'unknown'
                assert state==t['state'],(qid,ev['mode'],w['case'],w['path'],t['state'],state)
                if state=='known_correct':assert got==set(map(tuple,t['expected']))
                current.append({'cohort':folder,'query':qid,'mode':ev['mode'],'case':w['case'],'path':w['path'],'state':state,
                                'sources':sorted(got,key=str),'expected':sorted(want,key=str)if want is not None else None})
            assert sha(cap)==digest
            save(out/(stem+'-instances.json'),current);rows.extend(current)
            receipts.append({'evaluation':str(ev_path),'evaluation_sha256':sha(ev_path),'compatible':True,
                             'raw_sha256':digest,'plan_sha256':sha(before_plan),'targets':len(current),
                             'oracle_scope':'Previously independent oracle, exact same raw capture and input; no predictions used as truth.'})
    save(out/'instances.json',rows);save(out/'summary.json',{'passed':True,'receipts':receipts,
        'states':{mode:dict(Counter(r['state']for r in rows if r['mode']==mode))for mode in('full','selective')},
        'unchanged_only':True,'new_Agent_deployments':False,'affected_plans_require_new_capture':True})
    print('Compatible normal reconstruction targets',len(rows))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--reference',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();replay(a.root.resolve(),a.reference.resolve(),a.out.resolve())
