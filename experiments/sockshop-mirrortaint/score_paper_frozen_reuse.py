"""Original task denominator and raw identity oracle, separate from predictions."""
import argparse
from collections import Counter
import csv
from pathlib import Path

from run_planned_service import load, save, sha
from audit_target_external_first import selected, business_comparison, unresolved_output_obligations
from external_transfer_oracle import raw, require_complete_raw_capture, RawFactIndex
from audit_zlt_foundation_revision import tf_pair
from native_source_protocol import validate as validate_native


def one(xs, reason):
    if len(xs)!=1: raise ValueError(reason+': '+str(len(xs)))
    return xs[0]


def physical_target(rows, wire, mode, message, pointer, value):
    if mode=='mirrortaint':
        target=one([r for r in rows if r['kind']=='target' and r.get('context',{}).get('message')==message], 'native root')
        f=one([f for r in wire if r['kind']=='http-json' and r.get('message')==message and
               r.get('direction')=='response' and r.get('phase')=='write' for f in r['fields'] if f['path']==pointer], 'native wire leaf')
        one([v for v in target['fields'] if v['path']==pointer and all(v.get(k)==f.get(k) and f.get(k)is not None for k in ('owner','field','version'))], 'native physical target')
        assert f['observed']['value']==value
    else:
        target=one([r for r in rows if r['kind']=='binding-return' and r.get('message')==message],'TF root return')
        f=one([f for f in target['fields'] if f['path']==pointer],'TF target field')
        wf=one([f for r in rows if r['kind']=='http-json' and r.get('message')==message and
                r.get('direction')=='response' and r.get('phase')=='write' for f in r['fields'] if f['path']==pointer],'TF wire field')
        assert all(f[k]==wf[k]for k in ('owner','field','version')) and f['observed']['value']==value
    return target,f


def raw_expected(rows, wire, mode, message, pointer, value, q):
    """Only actual source/target coordinates and pairing, never a graph or tags."""
    target,f=physical_target(rows,wire,mode,message,pointer,value)
    if mode=='mirrortaint':
        validate_native(rows)
        sources=[r for r in rows if r['kind']=='source' and r.get('root')==target['root'] and r.get('call')in q['source_calls']]
        wants=[(s['call'],s['ordinal'],v['path'],v['owner'],v['field'],v['version'])
               for s in sources for v in s['fields'] if all(v.get(k)==f.get(k)for k in ('owner','field','version'))]
        want=one(wants,'native actual source instance')
        source=one([s for s in sources if s['call']==want[0] and s['ordinal']==want[1]],'native source occurrence')
        pair={k:source[k]for k in ('source_call_id','caller_method','instrumented_instruction_index')}
    else:
        require_complete_raw_capture(rows); index=RawFactIndex(rows)
        sources=[s for s in index.source_family(target['frame'])if s.get('callee')in q['source_calls']]
        pairs={s['seq']:tf_pair(rows,s)for s in sources}
        wants=[(s['callee'],s['frame'],s['seq'],v['path'],v['owner'],v['field'],v['version'])
               for s in sources for v in s['fields'] if all(v.get(k)==f.get(k)for k in ('owner','field','version'))]
        want=one(wants,'TF actual source instance'); pair=pairs[want[2]]
    return {'expected':[list(want)], 'target_coordinate':{k:f[k]for k in ('owner','field','version')}, 'pair':pair}


def own_database(trial, cases, q):
    receipt=load(trial/'database-receipt.json'); assert receipt['returncode']==0
    table='post' if q['id']=='fresh-post-detail' else 'dict_type'
    rows={}
    for line in(trial/'independent-database.tsv').read_text().splitlines()[1:]:
        parts=line.split('\t')
        if len(parts)==5:rows[(parts[0],parts[1])]=parts
    checks=[]
    def walk(v):
        if isinstance(v,dict):
            idkey,namekey=('postId','postName')if table=='post'else('dictId','dictName')
            if idkey in v:
                fact=rows[(table,str(v[idkey]))]
                checks.append({'id':v[idkey], 'name_matches':v[namekey]==fact[2],
                               'own_clock_matches':v.get('createTime')==fact[3]})
            for item in v.values():walk(item)
        elif isinstance(v,list):
            for item in v:walk(item)
    for case in cases:walk(case['response'])
    assert all(c['name_matches'] and c['own_clock_matches']for c in checks)
    return checks


def score(home,out):
    from run_paper_frozen_reuse import verify
    verify(home);out.mkdir(parents=True,exist_ok=False)
    from infer_distributed_fields import Reconstruction
    from run_mirror_capability_probe import read_events,native_answer
    records=[];receipts=[];obligations=[];target_absence=[]
    for q in load(home/'task-seal.json')['tasks']['ruoyi']:
        qid=q['id'];pattern=q['target'].split('@',1)[1]
        base=load(home/'runs'/qid/'original/result.json');assert base['state']=='captured'
        original=base['cases'];assert len(original)==len(q['inputs'])
        own_database(home/'runs'/qid/'original',original,q)
        denominator=[(c,p,v)for c in original for p,v in selected(c['response'],pattern)]
        obligations.extend({'query':qid,'case':c['case'],**o} for c in original for o in unresolved_output_obligations(c,pattern))
        for case in original:
            if not selected(case['response'],pattern):
                target_absence.append({'query':qid,'case':case['case'],'declared_path':pattern,
                    'HTTP_status':case['http_status'],'response_shape':case['response'],
                    'state':'no_selected_target_leaf','not_a_correct_answer_or_empty_source':True})
        for mode in ('full','selective','mirrortaint'):
            trial=home/'runs'/qid/mode;planned=load(home/'plans'/qid/'result.json')
            rows=[];wire=[];graph=None;error=None;state=planned['state'];actual=[];native=None
            if(trial/'result.json').exists():
                run=load(trial/'result.json');state=run['state'];actual=run['cases']
                if state=='captured':
                    try:
                        own_database(trial,actual,q)
                        if mode=='mirrortaint':
                            wire=raw(trial/'capture/instances.jsonl');rows=raw(trial/'capture/native-capability.jsonl')
                            view=out/(qid+'-native-view');view.mkdir();(view/'role').symlink_to((trial/'capture').resolve(),target_is_directory=True)
                            native=read_events(view,'role');validate_native(rows)
                        else:
                            rows=raw(trial/'capture/events.jsonl');require_complete_raw_capture(rows)
                            assert not(trial/'capture/events.jsonl.invalid').exists()
                            b=out/(qid+'-'+mode)/'build/role';b.mkdir(parents=True)
                            (b/'plan.json').write_bytes((home/'plans'/qid/'plan.json').read_bytes())
                            cap=b.parents[1]/'capture/role';cap.mkdir(parents=True)
                            (cap/'events.jsonl').symlink_to((trial/'capture/events.jsonl').resolve())
                            graph=Reconstruction(b.parent,cap.parent,['role'],decoded_rows={'role':rows})
                    except Exception as e:
                        error=str(e)
                        valid=bool(rows)and rows[-1]['kind']=='metrics'and not any(r['kind']=='problem'for r in rows)and not rows[-1].get('capture_invalid')
                        state='semantic_rejected'if mode!='mirrortaint'and valid else'export_unavailable'if mode=='mirrortaint'else'evidence_invalid'
                else:error=run.get('error')
            else:error=planned.get('reason')
            business=[]
            for original_case in original:
                found=[c for c in actual if c['case']==original_case['case']]
                if len(found)==1:
                    c=found[0];comparison=business_comparison('ruoyi',original_case['response'],c['response'])
                    business.append(original_case['http_status']==c['http_status'] and comparison['task_response_equal_except_original_SQL_initialization_clock'])
            for base_case,pointer,value in denominator:
                r={'query':qid,'mode':mode,'case':base_case['case'],'path':pointer,'state':state,
                   'reason':error,'target_bound':False,'source_paired':False,'oracle_adequate':False}
                found=[c for c in actual if c['case']==base_case['case']]
                if len(found)==1 and rows:
                    c=found[0]
                    try:
                        _,f=physical_target(rows,wire,mode,c['message'],pointer,value)
                        r.update(target_bound=True,target_coordinate={k:f[k]for k in ('owner','field','version')})
                    except Exception as e:r['binding_gap']=str(e)
                    try:
                        # Freeze expected instance facts BEFORE any prediction.
                        facts=raw_expected(rows,wire,mode,c['message'],pointer,value,q)
                        r.update(facts,target_bound=True,source_paired=True,oracle_adequate=True)
                        if error is None:
                            if mode=='mirrortaint':
                                answer=native_answer(native,c['message'],pointer);known=answer['state']=='known'
                                got=set(map(tuple,answer.get('sources',[])))
                            else:
                                answer=graph.query(c['message'],pointer,'role',boundary=[{'kind':'binding-source'},{'kind':'argument'}]);known=answer['known']
                                got={(s.get('callee'),s.get('root_frame'),s['seq'],s['path'],s['owner'],s['field'],s['version'])for s in answer['sources']}
                            r['prediction']=answer;r['state']=('known_correct'if got==set(map(tuple,facts['expected']))else'known_wrong')if known else'unknown';r['reason']=None
                    except Exception as e:
                        r['oracle_gap']=str(e)
                        if error is None:r['state']='oracle_or_target_unavailable'
                records.append(r)
            receipts.append({'query':qid,'mode':mode,'targets':len(denominator),'states':dict(Counter(r['state']for r in records if r['query']==qid and r['mode']==mode)),
                             'business_requests':len(actual),'business_equal':sum(business),'first_block':error,
                             'new_deployment':bool(actual)and not trial.is_symlink(),'oracle_adequate':sum(r['oracle_adequate']for r in records if r['query']==qid and r['mode']==mode),
                             'source_declaration':q['source_calls'],'configuration':load(home/'task-seal.json').get('configuration','A0')})
    verify(home);save(out/'instances.json',records);save(out/'summary.json',{'reference':'bcdf059','queries':receipts,'additional_obligations':obligations,'target_absence':target_absence,'no_performance':True,'no_core_agent_contract_changes':True})
    with(out/'instances.csv').open('w')as f:
        fields=list(dict.fromkeys(k for r in records for k in r));w=csv.DictWriter(f,fields,lineterminator='\n');w.writeheader();w.writerows(records)
    print([{k:r[k]for k in ('query','mode','states','first_block')}for r in receipts])


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--home',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();score(a.home.resolve(),a.out.resolve())
