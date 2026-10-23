#!/usr/bin/env python3
"""Freeze the conservative observation revision; fresh 62+29 regressions."""
import argparse,copy,subprocess,shutil,os
from pathlib import Path
from run_planned_service import ROOT,HERE,load,save,sha
from plan_capability_policy import choose
import build_distributed_plans as builder
import run_frozen_capability_acceptance as driver
import run_quota_capability_acceptance as quota

PARENT=ROOT/'artifacts/transport-observation-shared-20261023'
FIRST29=ROOT/'artifacts/heldout29-first-20261023'


def prepare(root):
    assert not(root/'algorithm-freeze.json').exists()
    assert load(root/'closure-controls/results.json')['all_passed']
    old=load(PARENT/'frozen-base/build.json');base=root/'frozen-base'
    builder.build(base,{k:v['query_config']for k,v in old['inputs'].items()})
    manifest=load(base/'build.json');freeze=load(PARENT/'algorithm-freeze.json');commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    plans=root/'frozen-plans';plans.mkdir();results=[]
    for q in driver.QUERIES:
        p,policy=choose(load(base/q['role']/'model.json'),q);previous=load(PARENT/'frozen-plans'/(q['id']+'.json'));stripped=copy.deepcopy(p);stripped.pop('execution_observation_closure',None)
        assert stripped==previous,('Execution semantics changed',q['id'])
        save(plans/(q['id']+'.json'),p);results.append({'query':q,'status':'accepted','policy':policy,'plan_sha256':sha(plans/(q['id']+'.json')),'semantic_plan_preserved':True})
    save(plans/'planning.json',results)
    queries29=load(FIRST29/'protocol-before-first.json')['queries'];extra=root/'regression29-plans';extra.mkdir()
    for q in queries29:save(extra/(q['id']+'.json'),choose(load(base/q['role']/'model.json'),q)[0])
    sources=manifest['sources']
    for f,h in sources.items():
        assert sha(Path(f))==h;dest=root/'source-snapshot'/Path(f).relative_to(ROOT);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(f,dest)
    freeze.update(commit=commit,algorithm_commit=commit,commit_at_build=commit,base_build=str(base),sources=sources,builder_sha256=sha(HERE/'build_distributed_plans.py'),planning_sha256=sha(plans/'planning.json'),original_jars={k:v['original_jar_sha256']for k,v in manifest['inputs'].items()},pair_driver_sha256=sha(HERE/'run_cart_reread_baseline_pair.py'),parent_algorithm='e78cc04',scope='Observation-only conservative closure; no new propagation semantics. Shared alias index used by every mode. New21 remain sealed until this freeze.')
    save(root/'algorithm-freeze.json',freeze);(root/'drivers').mkdir()
    for name in ('run_execution_closure_revision.py','run_frozen_capability_acceptance.py','run_quota_capability_acceptance.py','run_cart_reread_baseline_pair.py'):
        shutil.copyfile(HERE/name,root/'drivers'/('cart-pair-library-driver-at-launch.py'if name=='run_cart_reread_baseline_pair.py'else name))
    save(root/'protocol-before-business.json',{'algorithm':commit,'development_queries':62,'regression_fields':29,'new_sealed_queries':21,'not_new_unseen_evidence':'62+29','semantics_changes':False,'format_compression':False,'general_call_or_instruction_slicing_complete':False,'reduction':'Only irrelevant scalar constructor write-value observations within declared source extents; retain versions and guards. All interpreted application effects, calls, path and container obligations remain conservatively expanded.','required_known_targets':{'development_per_mode':428,'old29_per_mode':232},'unchanged_unknown_targets':{'development_per_mode':3,'old29_per_mode':12},'cost_gate':'Fresh 62+29 state/origin retention and controls before new timed trials.'})
    print({'frozen':commit,'core_sources':len(sources),'plans62':len(results),'plans29':len(queries29)},flush=True)


def regression29(root,part):
    import run_heldout29_first as first
    quota.install(root);base=root/'frozen-base';driver.QUERIES=load(FIRST29/'protocol-before-first.json')['queries'];oldplan=driver.plan
    driver.plan=lambda q:load(root/'regression29-plans'/(q['id']+'.json'))
    # The established training driver checks plan existence separately from
    # its plan() callback. Add disjoint links; never alter the 62-plan manifest.
    for q in driver.QUERIES:
        destination=root/'frozen-plans'/(q['id']+'.json');source=root/'regression29-plans'/(q['id']+'.json')
        if not destination.exists():destination.symlink_to(source)
        assert sha(destination)==sha(source)
    records=load(FIRST29/'audit-final-reviewed/audit.json')['records'];captures={}
    for r in records:
        if r['mode']!='full':continue
        p=Path(r['evaluation_file']).parent
        if not(p/'capture/run.json').exists():
            receipt=load(FIRST29/'independent-id-projection-correction/receipt.json');p=Path(next(v['source']for v in receipt['changes']if v['corrected']==r['evaluation_file'])).parent
        captures[r['query']]=p/'capture'
    driver.previous=lambda q:captures[q['id']]
    def independent(q,c,path,rows):
        if q['id']=='trainticket-route-getRouteByStartAndTerminal-data-each-id':
            start,terminal=c['request_path'].split('/')[-2:];docs=c['database_documents'];kept=[i for i,d in enumerate(docs)if start in d['stations']and terminal in d['stations']and d['stations'].index(start)<d['stations'].index(terminal)];i=kept[int(path.split('/')[2])];wanted=docs[i]['_id'];assert c['response']['data'][int(path.split('/')[2])]['id']==wanted
            rs=rows['route'];ret=next(v for v in rs if v['kind']=='binding-return'and v.get('message')==c['message']);sources=[v for v in rs if v['kind']=='binding-source'and v['frame']==ret['frame']];assert len(sources)==1;s=sources[0];fields=[f for f in s['fields']if f['path']==f'/{i}/id'and f['field']=='route/entity/Route.id'];assert len(fields)==1 and fields[0]['observed']['value']==wanted;return[driver.old.source_coord('route',s,fields[0])]
        return first.independent_tf(q,c,path,rows)
    driver.independent=independent
    if part=='orders':driver.orders(root/'regression29-orders',base)
    else:
        os.environ['TF2_CAPABILITY_PORT']='19120';driver.train(root/'regression29-train',base)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',required=True,type=Path);p.add_argument('--stage',choices=('prepare','worker62','regression29'),required=True);p.add_argument('--worker');a=p.parse_args();root=a.root.resolve()
    if a.stage=='prepare':prepare(root)
    elif a.stage=='worker62':quota.worker(root,a.worker)
    else:regression29(root,a.worker)
