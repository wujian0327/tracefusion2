"""Separate business, physical binding, integrity and semantic answer states."""
import argparse,collections,csv,json
from pathlib import Path
from run_planned_service import ROOT,load,save,sha
from audit_target_external_first import selected,business_comparison
from analysis_status import AnalysisLimit


def run(home,out,modes=('full','selective')):
    out.mkdir(parents=True,exist_ok=False)
    protocol=load(home/'task-seal.json');original=load(ROOT/'artifacts/target-closure-revision-20261103/ruoyi-original-03/sealed-original-requests/results.json')['cases']
    import external_transfer_oracle as oracle
    from infer_distributed_fields import Reconstruction
    from infer_map_wrapper import validate
    from audit_zlt_foundation_revision import tf_pair
    results=[];receipts=[]
    for q in protocol['tasks']['ruoyi']:
        path=q['target'].split('@')[1]
        for mode in modes:
            trial=home/'runs'/q['id']/mode;rows=oracle.raw(trial/'capture/events.jsonl');plan=load(home/'plans'/q['id']/'plan.json')
            problems=[r for r in rows if r['kind']=='problem'];footers=[r for r in rows if r['kind']=='metrics']
            complete=[r['seq']for r in rows]==list(range(1,len(rows)+1))and len(footers)==1
            valid=complete and not problems and not footers[0].get('capture_invalid')and not(trial/'capture/events.jsonl.invalid').exists()
            index=oracle.RawFactIndex(rows);graph=None;error=None;category=None
            view=out/(q['id']+'-'+mode);(view/'build/role').mkdir(parents=True);(view/'capture/role').mkdir(parents=True)
            (view/'build/role/plan.json').write_bytes((home/'plans'/q['id']/'plan.json').read_bytes());(view/'capture/role/events.jsonl').symlink_to((trial/'capture/events.jsonl').resolve())
            try:validate(plan,rows);graph=Reconstruction(view/'build',view/'capture',['role'],decoded_rows={'role':rows})
            except AnalysisLimit as e:error=str(e);category='analysis_limited'
            except Exception as e:error=str(e);category='validation_rejected'if valid else'evidence_invalid'
            cases=load(trial/'result.json')['cases'];matched=[];times=[]
            if(trial/'independent-db-times-receipt.json').exists()and load(trial/'independent-db-times-receipt.json')['returncode']==0:
                table={1:('sys_dept','deptId'),2:('sys_dept','deptId'),3:('sys_dict_data','dictCode'),4:('sys_config','configId'),5:('sys_post','postId')}[int(q['id'].split('-')[-1])]
                db={}
                for line in(trial/'independent-db-times.tsv').read_text().splitlines()[1:]:
                    parts=line.split('\t')
                    if len(parts)==3:db[(parts[0],parts[1])]=parts[2]
                def clock(v):
                    if isinstance(v,dict):
                        if table[1]in v and isinstance(v.get('createTime'),str):times.append({'id':str(v[table[1]]),'wire':v['createTime'],'DB':db.get((table[0],str(v[table[1]]))), 'equal':v['createTime']==db.get((table[0],str(v[table[1]])))})
                        for x in v.values():clock(x)
                    elif isinstance(v,list):
                        for x in v:clock(x)
                for c in cases:clock(c['response'])
            for base in(c for c in original if c['query']==q['id']):
                actual=next(c for c in cases if c['case']==base['case']);business=business_comparison('ruoyi',base['response'],actual['response'])
                matched.append(base['http_status']==actual['http_status']and business['task_response_equal_except_original_SQL_initialization_clock'])
                for pointer,value in selected(base['response'],path):
                    r={'query':q['id'],'mode':mode,'case':base['case'],'path':pointer,'business_preserved_except_seed_clock':matched[-1],
                       'capture_closed':complete,'raw_capture_no_problem':valid,'capture_integrity_valid':valid and graph is not None,'target_bound':False,'declared_source_paired':False,'raw_identity_rule_matches':False,'oracle_adequate':False,'state':category or'unknown','reason':error}
                    returns=index.returns.get(actual['message'],[])
                    if len(returns)==1:
                        ret=returns[0];fields=[f for f in ret['fields']if f['path']==pointer]
                        wire=[f for e in rows if e['kind']=='http-json'and e.get('message')==actual['message']and e.get('direction')=='response'and e.get('phase')=='write'for f in e['fields']if f['path']==pointer]
                        if len(fields)==len(wire)==1:
                            f=fields[0];r['target_bound']=all(f.get(k)==wire[0].get(k)for k in('owner','field','version'))and f['observed']['value']==value
                            sources=[s for s in index.source_family(ret['frame'])if s.get('callee')in q['source_calls']]
                            try:
                                for source in sources:tf_pair(rows,source)
                                r['declared_source_paired']=bool(sources)
                            except Exception as e:r['source_pair_error']=str(e)
                            wants=[(s['callee'],s['frame'],s['seq'],v['path'],v['owner'],v['field'],v['version'])for s in sources for v in s['fields']if all(v.get(k)==f.get(k)for k in('owner','field','version'))]
                            if r['target_bound']and r['declared_source_paired']and len(wants)==1:
                                r['raw_identity_rule_matches']=True;r['oracle_adequate']=valid;r['expected']=wants
                                if graph is not None and valid:
                                    answer=graph.query(actual['message'],pointer,'role',boundary=[{'kind':'binding-source'},{'kind':'argument'}]);got={(s.get('callee'),s.get('root_frame'),s['seq'],s.get('path'),s['owner'],s['field'],s['version'])for s in answer['sources']}
                                    r.update(state=('known_correct'if got==set(wants)else'known_wrong')if answer['known']else'unknown',reason=None)
                    results.append(r)
            receipts.append({'query':q['id'],'mode':mode,'business_requests':len(cases),'business_preserved':sum(matched),'closed':complete,'raw_no_problem':valid,'integrity_and_reconstruction_validated':valid and graph is not None,
                'first_problem':problems[0]if problems else None,'problem_count':len(problems),'root_returns':sum(r['kind']=='binding-return'for r in rows),
                'semantic_error_type':category,'semantic_error':error,'own_DB_clock_checks':times,'own_DB_clock_all_equal':all(t['equal']for t in times)if times else None,
                'original_capture_sha256':sha(trial/'capture/events.jsonl')})
    save(out/'instances.json',results);save(out/'receipts.json',receipts)
    save(out/'summary.json',{'states':{m:dict(collections.Counter(r['state']for r in results if r['mode']==m))for m in modes},
        'facts':{m:{k:sum(bool(r[k])for r in results if r['mode']==m)for k in('target_bound','capture_integrity_valid','declared_source_paired','raw_identity_rule_matches','oracle_adequate')}for m in modes},
        'scope':'Exposed five-query return tasks; independent identity-copy source rule. Physical facts do not certify answers on damaged captures. C2 mapper calibration remains separate.'})
    with(out/'instances.csv').open('w')as f:
        fields=list(dict.fromkeys(k for r in results for k in r));w=csv.DictWriter(f,fields,lineterminator='\n');w.writeheader();w.writerows(results)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--home',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();run(a.home.resolve(),a.out.resolve())
