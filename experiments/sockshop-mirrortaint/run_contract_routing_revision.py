#!/usr/bin/env python3
"""Matched development follow-up; immutable first new-entry results stay separate."""
import argparse,datetime,json,traceback,copy,shutil,subprocess
from pathlib import Path
from collections import Counter,defaultdict
from run_planned_service import ROOT,HERE,load,save,sha
import run_execution_closure_heldout as first
import run_frozen_capability_acceptance as tf
import run_response_binding_revision as business
from run_heldout29_first import native_configure
from run_mirror_capability_probe import read_events,native_answer

PARENT=ROOT/'artifacts/execution-closure-revision-20261023'
BUNDLE=ROOT/'artifacts/heldout29-first-20261023/native-bundle'

def prepare(root):
    root.mkdir(parents=True,exist_ok=False);(root/'logs').mkdir()
    protocol=load(PARENT/'heldout21-first/protocol-before-planning.json')
    save(root/'protocol.json',{'parent_algorithm':protocol['algorithm'],'parent_report_commit':'340c07c36082cf94615ad94edd10929769890dc9','parent_first_audit_sha256':sha(PARENT/'heldout21-first/audit-first.json'),'parent_first_protocol_sha256':sha(PARENT/'heldout21-first/protocol-before-planning.json'),'queries':[q for q in protocol['queries']if q['role']!='station'],'inputs':protocol['input_cases_by_entry'],'Station':'Retain first403; no authenticated follow-up.','classification':'All21 queries are now exposed development queries. No new unseen-query claim.','baseline_bundle':str(BUNDLE),'baseline_manifest_sha256':sha(BUNDLE/'build.json'),'native_jar_sha256':load(BUNDLE/'build.json')['native_sha256'],'truth':'Literal original copy/setter/constructor and split/parse projections from the first protocol, mapped to independently observed root argument0 fields. No TF graph or native taint output determines expected origins.','sequence':'Save protocol and original-access checks; calibrate fixed native baseline, then repair contract applicability/profile selection; freeze and run full/selective, historical capability/guards; only then widen observation slicing. No new performance rounds.','created_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()})
    save(root/'logs/00-protocol.json',{'protocol_sha256':sha(root/'protocol.json'),'first_negative_results_unchanged':True})

def native_score(d,queries,corrected=False):
    rows=read_events(d/'capture',queries[0]['role']);run=load(d/'capture/run.json');result=[]
    for q in queries:
        targets=[];na=0
        for c in run['cases']:
            leaves=business.leaves(c['response'],q['path']);na+=not bool(leaves)
            for path,value in leaves:
                answer=native_answer(rows,c['message'],path);t={'case':c['case'],'path':path,'message':c['message'],'client_value':value,'answer':answer}
                try:
                    ts=[r for r in rows if r['kind']=='target'and r['context'].get('message')==c['message']];assert len(ts)==1
                    wire=[f for f in ts[0]['wire_fields']if f['path']==path];assert len(wire)==1 and wire[0]['observed'].get('value')==value
                    preserved_id=corrected and path=='/data/id' and c['database_documents'] and (q['role']=='route' or 'createNewPriceConfig' in q['entry'])
                    sources=[r for r in rows if r['kind']=='source'and r['root']==ts[0]['root']and ('.findById(' in r['call'] if preserved_id else r['call']=='@argument:0')];assert len(sources)==1;s=sources[0]
                    field=path.split('/')[2]
                    if q['role']=='route':field={'stations':'stationList','distances':'distanceList','startStationId':'startStation','terminalStationId':'endStation'}.get(field,field)
                    fs=[f for f in s['fields']if f['path']=='/'+field];assert len(fs)==1 and fs[0]['value']==c['request_body'][field];f=fs[0]
                    expected={(s['call'],s['ordinal'],'/'+field,f.get('owner'),f.get('field'),f.get('version'))};actual={tuple(v)for v in answer.get('sources',[])}
                    t.update(expected=sorted(expected,key=str),actual=sorted(actual,key=str),state=('known_correct'if actual==expected else'known_wrong')if answer['state']=='known'else answer['state'],tp=len(actual&expected)if answer['state']=='known'else 0,fp=len(actual-expected)if answer['state']=='known'else 0,fn=len(expected-actual)if answer['state']=='known'else len(expected))
                except Exception as e:t.update(state='oracle_unavailable',oracle_error=str(e))
                targets.append(t)
        result.append({'query':q['id'],'mode':'mirrortaint','requests':len(run['cases']),'N/A_requests':na,'targets':len(targets),'states':dict(Counter(t['state']for t in targets)),'predictions':targets})
    save(d/('evaluation-corrected-oracle.json'if corrected else'evaluation.json'),result)
    witness=[json.loads(s)for s in(d/'capture'/queries[0]['role']/'native-library.jsonl').read_text().splitlines()];assert witness and all(r['sha256']=='1a33365556ca88668006a549208e136c5c20c965b7cdc8406a106ac8f5bae7f3'for r in witness)
    save(d/'native-library-audit.json',{'all_passed':True,'business_mapper_original':True,'native_propagation_changed':False})
    return [{k:v for k,v in r.items()if k!='predictions'}for r in result]

def native(root):
    p=load(root/'protocol.json');assert sha(BUNDLE/'build.json')==p['baseline_manifest_sha256'];base=PARENT/'frozen-base';groups=defaultdict(list)
    for q in p['queries']:groups[q['entry']].append(q)
    out=root/'native-first';out.mkdir();results=[]
    original_config=tf.mode_config;original_verify=business.verify_build
    try:
        for entry,queries in groups.items():
            q=queries[0];d=out/q['id'];d.mkdir();(d/'build').symlink_to(base,target_is_directory=True)
            def config(spec,name,role,cap,build,mode):
                original_config(spec,name,role,cap,build,'full');native_configure(spec,cap,base,BUNDLE,q)
            def verify(build):
                m=load(BUNDLE/'build.json');assert sha(Path(m['native_jar']))==m['native_sha256']and sha(BUNDLE/'capability.jar')==m['probe_sha256']and sha(BUNDLE/'adapter/integration-adapter.jar')==m['adapter_sha256']
            tf.mode_config=config;business.verify_build=verify
            try:first.capture(d,root,q,'mirrortaint',p['inputs'][entry]);rows=native_score(d,queries);results.extend(rows)
            except Exception as e:
                record={'entry':entry,'queries':[q['id']for q in queries],'failure':str(e)};save(d/'failure.json',{**record,'traceback':traceback.format_exc()});results.append(record)
            save(out/'results.json',{'complete':False,'results':results});print(results[-1],flush=True)
    finally:tf.mode_config=original_config;business.verify_build=original_verify
    save(out/'results.json',{'complete':True,'results':results})

def independent_tf(q,c,path,rows):
    if path=='/data/id' and c['database_documents'] and (q['role']=='route' or 'createNewPriceConfig' in q['entry']):
        rs=rows[q['role']];ret=[r for r in rs if r['kind']=='binding-return'and r.get('message')==c['message']];assert len(ret)==1
        family=tf.family(rs,ret[0]);sources=[r for r in rs if r['kind']=='binding-source'and r.get('frame')in family and '.findById('in r.get('callee','')];assert len(sources)==1
        fs=[f for f in sources[0]['fields']if f['path']=='/id'];assert len(fs)==1 and fs[0]['observed'].get('value')==c['request_body']['id']
        return [business.source_coord(q['role'],sources[0],fs[0])]
    return first.independent(q,c,path,rows)


def rescore(root):
    p=load(root/'protocol.json');groups=defaultdict(list)
    for q in p['queries']:groups[q['entry']].append(q)
    results=[]
    for queries in groups.values():results.extend(native_score(root/'native-first'/queries[0]['id'],queries,True))
    save(root/'native-first/results-corrected-oracle.json',{'complete':True,'results':results,'first_scores_unchanged':True,'oracle_correction':'For existing Route/Price-create IDs, original code preserves repository object field; root argument is not copied. Original first21 and native scores retained. Same captured inputs/native labels; no propagation edits.'})


def build(root,iteration='05'):
    import build_distributed_plans as builder
    from plan_capability_policy import choose
    base=root/('development-base-'+iteration);prior=load(PARENT/'frozen-base/build.json');builder.build(base,{k:v['query_config']for k,v in prior['inputs'].items()})
    plans=root/('development-plans-'+iteration);plans.mkdir();records=[]
    for q in load(root/'protocol.json')['queries']:
        try:
            p,policy=choose(load(base/q['role']/'model.json'),q);save(plans/(q['id']+'.json'),p);records.append({'query':q,'accepted':True,'profile':p['profile'],'policy':policy})
        except Exception as e:records.append({'query':q,'accepted':False,'failure':str(e)})
    save(plans/'planning.json',records);save(root/'development-current.json',{'base':str(base),'plans':str(plans),'iteration':iteration})


def development(root,role,smoke=False):
    current=load(root/'development-current.json');base=Path(current['base']);p=load(root/'protocol.json');out=root/(('smoke-'+role if smoke else'development-'+role)+'-'+current['iteration']);out.mkdir();tf.independent=independent_tf;records=[]
    qs=[q for q in p['queries']if q['role']==role]
    if smoke:qs=[next(q for q in qs if 'updatePriceConfig-basicPriceRate' in q['id'])]if role=='price'else qs[:1]
    for mode in ('full','selective'):
        for q in qs:
            d=out/(mode+'-'+q['id']);d.mkdir()
            try:
                business.query_build(d/'build',base,q,load(Path(current['plans'])/(q['id']+'.json')));first.capture(d,root,q,mode,p['inputs'][q['entry']]);record=tf.evaluate(d,q)
            except Exception as e:record={'query':q['id'],'mode':mode,'failure':str(e)};save(d/'failure.json',{**record,'traceback':traceback.format_exc()})
            records.append(record);save(out/'results.json',{'complete':False,'results':records});print(record,flush=True)
    save(out/'results.json',{'complete':True,'results':records})


def freeze(root):
    """Freeze new integration semantics, not an observation-only parent reuse."""
    import build_distributed_plans as builder
    from plan_capability_policy import choose
    assert not(root/'algorithm-freeze.json').exists()
    assert load(root/'application-cut-controls-direct/write-cut-audit.json')['all_passed']
    prior=load(PARENT/'frozen-base/build.json');base=root/'frozen-base'
    builder.build(base,{k:v['query_config']for k,v in prior['inputs'].items()})
    manifest=load(base/'build.json');old=load(PARENT/'algorithm-freeze.json')
    commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    assert {k:v['original_jar_sha256']for k,v in manifest['inputs'].items()}==old['original_jars']
    cohorts=[('frozen-plans',tf.QUERIES),('regression29-plans',load(ROOT/'artifacts/heldout29-first-20261023/protocol-before-first.json')['queries']),('write-plans',load(root/'protocol.json')['queries'])]
    for folder,queries in cohorts:
        out=root/folder;out.mkdir();records=[]
        for q in queries:
            try:
                p,policy=choose(load(base/q['role']/'model.json'),q);save(out/(q['id']+'.json'),p);records.append({'query':q,'status':'accepted','policy':policy,'plan_sha256':sha(out/(q['id']+'.json'))})
            except ValueError as e:records.append({'query':q,'status':'rejected','rejection':str(e)})
        save(out/'planning.json',records)
    for f,h in manifest['sources'].items():
        assert sha(Path(f))==h;dest=root/'source-snapshot'/Path(f).relative_to(ROOT);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(f,dest)
    old.update(commit=commit,algorithm_commit=commit,commit_at_build=commit,base_build=str(base),sources=manifest['sources'],builder_sha256=sha(HERE/'build_distributed_plans.py'),planning_sha256=sha(root/'frozen-plans/planning.json'),original_jars={k:v['original_jar_sha256']for k,v in manifest['inputs'].items()},pair_driver_sha256=sha(HERE/'run_cart_reread_baseline_pair.py'),parent_algorithm='dff3d48',scope='Finite library applicability, automatic replay routing and immutable field preservation; certified unused scalar application write values. All queries exposed; no new unseen-query claim.')
    save(root/'algorithm-freeze.json',old)
    for name in ('run_contract_routing_revision.py','run_frozen_capability_acceptance.py','run_quota_capability_acceptance.py','run_cart_reread_baseline_pair.py'):
        shutil.copyfile(HERE/name,root/'drivers'/('cart-pair-library-driver-at-launch.py'if name=='run_cart_reread_baseline_pair.py'else name))
    save(root/'protocol-before-business.json',{'algorithm':commit,'cohorts':{'development62':431,'exposed29':244,'write15':96},'Station':'Retain403; no auth retry','original_first_results_preserved':True,'truth_correction':'Existing Route/Price-create IDs come from actual repository return, not root argument. First expected sets and scores retained separately.','ablation':'Only application_write_values.enabled; old source-boundary cut, calls, paths and all required checks shared. No new timed cost experiment.'})
    save(root/'development-current.json',{'base':str(base),'plans':str(root/'write-plans'),'iteration':'frozen'})
    print({'algorithm_frozen':commit,'sources':len(manifest['sources']),'cohorts':[(folder,len(queries))for folder,queries in cohorts]},flush=True)


def application_off(root):
    """Same selective semantics, only disable the new write-value policy."""
    tf.HOME=root;tf.check();tf.independent=independent_tf
    p=load(root/'protocol.json');qs=[q for q in p['queries']if q['role']=='route'];out=root/'application-off';out.mkdir();records=[]
    for q in qs:
        d=out/('selective-'+q['id']);d.mkdir();plan=load(root/'write-plans'/(q['id']+'.json'));plan['execution_observation_closure']['application_write_values']['enabled']=False
        business.query_build(d/'build',root/'frozen-base',q,plan);first.capture(d,root,q,'selective',p['inputs'][q['entry']]);records.append(tf.evaluate(d,q));save(out/'results.json',{'complete':False,'results':records})
    save(out/'results.json',{'complete':True,'results':records,'only_changed':'execution_observation_closure.application_write_values.enabled','not_performance_measurements':True})


if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--root',required=True,type=Path);a.add_argument('--stage',choices=('prepare','native','native-rescore','build','smoke','development','freeze','application-off'),required=True);a.add_argument('--role',choices=('route','price'));v=a.parse_args()
    if v.stage in ('smoke','development'):development(v.root.resolve(),v.role,v.stage=='smoke')
    else:{'prepare':prepare,'native':native,'native-rescore':rescore,'build':build,'freeze':freeze,'application-off':application_off}[v.stage](v.root.resolve())
