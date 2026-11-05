"""Fixed task scoring plus separate raw framework/Redis evidence inventories."""
import argparse,collections,csv,json
from pathlib import Path
from run_planned_service import ROOT,load,save,sha
from run_ruoyi_before_advice_revision import evaluate
from audit_zlt_foundation_revision import tf_pair

def run(home,out):
    out.mkdir(parents=True,exist_ok=False);online=load(home/'algorithm-freeze.json')
    freeze_path=next((home/n for n in ('offline-final-freeze.json','offline-freeze.json')if(home/n).exists()),None)
    freeze=load(freeze_path)if freeze_path else online
    for name,digest in freeze['sources'].items():assert sha(Path(name))==digest,name
    for name,digest in load(home/'protocol-before-change.json')['old_files'].items():assert sha(ROOT/name)==digest,name
    assert sha(home/'candidate/distributed-observer.jar')==online['agent_sha256']
    all_rows=[];receipts=[];before=[];redis=[];capture_hashes={}
    for q in ('ruoyi-2','ruoyi-3','ruoyi-1'):
        target=out/q;evaluate(home,'final-C1',q,target)
        all_rows.extend(load(target/'instances.json'));receipts.extend(load(target/'receipts.json'))
        for mode in ('full','selective'):
            path=home/'final-C1/runs'/q/mode/'capture/events.jsonl';capture_hashes[str(path)]=sha(path)
            rows=[json.loads(s)for s in path.read_text().splitlines()];by_seq={r['seq']:r for r in rows}
            for r in rows:
                if r['kind']=='execution-direct-dispatch'and r.get('before_only'):
                    steps=[by_seq[s]for s in r['before_steps']]
                    before.append({'query':q,'mode':mode,'frame':r['frame'],'call_id':r['call_id'],
                        'target':r['target'],'target_type':r['target_type'],'dispatch_seq':r['seq'],'chain':r['chain'],
                        'actual_advice_methods':sorted({s['advice_method']for s in steps if s.get('advice_method')}),
                        'steps':steps,'all_steps_precede_target_dispatch':all(s['seq']<r['seq']for s in steps)})
            if q=='ruoyi-3':
                for source in rows:
                    if source['kind']!='binding-source'or source['callee']!='org/springframework/data/redis/core/ValueOperations.get(Ljava/lang/Object;)Ljava/lang/Object;':continue
                    proofs=[by_seq[s]for s in source.get('json_tree_proofs',[])]
                    if not proofs:continue
                    tf_pair(rows,source)
                    redis.append({'mode':mode,'source_seq':source['seq'],'frame':source['frame'],
                        'source_call_id':source['source_call_id'],'source_caller_method':source['source_caller_method'],
                        'source_pc':source['source_pc'],'source_scope':source['source_scope'],'fields':source['fields'],
                        'json_containers':proofs,'source_pair_complete':True,
                        'capture_invalid':any(r['kind']=='problem'or r['kind']=='metrics'and r.get('capture_invalid')for r in rows)})
    with(ROOT/'experiments/sockshop-mirrortaint/ruoyi-removeif-paired-20261105.csv').open()as f:
        previous={(r['query'],r['mode'],int(r['case']),r['path']):r for r in csv.DictReader(f)}
    for row in all_rows:
        old=previous[(row['query'],row['mode'],row['case'],row['path'])]
        row['previous_TF_state']=old['state'];row['historical_MT_state']=old['historical_MT_state']
    logical=lambda r:(r['query'],r['case'],r['path'],r['state'],sorted((s[0],s[3],s[5],s[6])for s in r.get('predicted',[])))
    assert sorted(logical(r)for r in all_rows if r['mode']=='full')==sorted(logical(r)for r in all_rows if r['mode']=='selective')
    assert all(r['business_preserved']==r['business_requests']==6 for r in receipts)
    assert all(r['state']=='known_correct'for r in all_rows if r['query']=='ruoyi-1')
    assert all(sha(Path(n))==v for n,v in capture_hashes.items())
    summary={'online_freeze':online['commit'],'offline_freeze':freeze['commit'],'agent_sha256':online['agent_sha256'],
        'states':{q:{m:dict(collections.Counter(r['state']for r in all_rows if r['query']==q and r['mode']==m))for m in('full','selective')}for q in('ruoyi-1','ruoyi-2','ruoyi-3')},
        'fact_counts':{q:{m:{key:sum(bool(r[key])for r in all_rows if r['query']==q and r['mode']==m)for key in('target_bound','capture_integrity_valid','declared_source_paired','raw_identity_rule_matches','oracle_adequate')}for m in('full','selective')}for q in('ruoyi-1','ruoyi-2','ruoyi-3')},
        'business_receipts':receipts,'before_certificates':len(before),
        'Redis_JSON_read_calls':dict(collections.Counter(r['mode']for r in redis)),
        'full_selective_states_and_logical_sources_equal':True,'old_reference_hashes_unchanged':True,
        'raw_capture_hashes':capture_hashes,'scope':'Three exposed C1 tasks, not all five tasks or historical/new-app capability; no performance measurement.'}
    save(out/'summary.json',summary);save(out/'instances.json',all_rows)
    save(out/'before-proxy-evidence.json',before);save(out/'redis-source-facts.json',redis)
    with(out/'instances.csv').open('w')as f:
        names=list(dict.fromkeys(k for r in all_rows for k in r));w=csv.DictWriter(f,names,lineterminator='\n');w.writeheader();w.writerows(all_rows)
    print(summary['states'],summary['Redis_JSON_read_calls'])

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--home',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();run(a.home.resolve(),a.out.resolve())
