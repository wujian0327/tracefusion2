"""Literal data/selection expectations from raw source facts, frozen TF binary."""
import argparse, copy, json
from pathlib import Path
from zipfile import ZipFile
from run_planned_service import ROOT,HERE,load,save,sha
from run_query_planner import command,JARS
from run_generic_observation_rules import metadata_build,AGENT
from plan_capability_policy import choose
from tf_static_baseline import configure
from infer_execution_kernel import infer_execution
from raw_source_call_facts import RawSourceCallFacts
from audit_zlt_foundation_revision import tf_pair


def run(out,direct=False):
    out.mkdir(parents=True,exist_ok=False)
    old=ROOT/'artifacts/galette-static-baselines-20261111'
    java=str(old/'runtime-base/java-8-openjdk-amd64/bin/java')
    freeze=load(old/'protocol-before-calibration.json')
    for p,d in freeze['core_sources'].items():assert sha(Path(p))==d,p
    classes=out/'classes';classes.mkdir()
    deps=sorted((ROOT/'artifacts/ruoyi-request-scope-20261104/scope-controls-02/deps').glob('*.jar'))
    cp=':'.join(map(str,[classes,AGENT,*JARS,*deps]))
    fixture='DirectSelectionFixture' if direct else 'NonemptySelectionFixture'
    command([java[:-4]+'javac','-cp',cp,'-d',str(classes),str(HERE/(fixture+'.java'))],out/'compile.log')
    jar=out/'fixture.jar'
    with ZipFile(jar,'w') as z:
        for f in classes.glob('*.class'):z.write(f,'BOOT-INF/classes/'+f.name)
    metadata_build(out/'build',{'fixture':{'jar':str(jar),'targets':[fixture+'$Box.text']}})
    plan,route=choose(load(out/'build/fixture/model.json'),{
        'entry':fixture+'.root(L'+fixture+'$Store;L'+fixture+'$Gate;ILjava/util/function/Predicate;)L'+fixture+'$Out;',
        'target':fixture+'$Box.text','path':'/items/*/text',
        'source_calls':[fixture+'$Store.read(I)L'+fixture+'$Box;',fixture+'$Gate.read(I)L'+fixture+'$Choice;']},
        deployment=load(ROOT/'artifacts/target-closure-revision-20261103/external-first-01/deployment-environment.json'))
    save(out/'plan.json',plan);plan=load(out/'plan.json');save(out/'route.json',route)
    baseline=json.loads(command([java,'-cp',cp,fixture],out/'original.log').stdout.splitlines()[-1])
    normalized={};results={}
    for mode in ('full','static','selective'):
        d=out/mode;d.mkdir();policy=configure(plan,mode);save(d/'policy.json',policy)
        cmd=[java,'-javaagent:'+str(AGENT),'-Dfixture.observe=true','-Dservice.plan='+str(out/'plan.json'),'-Dservice.events='+str(d/'events.jsonl'),*policy['jvm_options'],'-cp',cp,fixture]
        save(d/'command.json',cmd)
        actual=json.loads(command(cmd,d/'stdout.log').stdout.splitlines()[-1])
        assert [{k:v for k,v in c.items()if k!='message'}for c in actual]==[{k:v for k,v in c.items()if k!='message'}for c in baseline]
        rows=[json.loads(l)for l in(d/'events.jsonl').read_text().splitlines()]
        assert not any(r['kind']=='problem'or r['kind']=='metrics'and r.get('capture_invalid')for r in rows)
        facts=RawSourceCallFacts(rows);truth=[]
        for c in actual:
            sources=[r for r in rows if r['kind']=='binding-source'and r.get('message')==c['message']]
            stores=[r for r in sources if '$Store.read' in r['callee']];gates=[r for r in sources if '$Gate.read' in r['callee']]
            assert len(stores)==2 and len(gates)==1
            for s in sources:tf_pair(facts.matching(rows,s),s)
            def field(s,name,path=None):
                fields=[(i,f)for i,f in enumerate(s['fields'])if f['field'].endswith('.'+name)and(path is None or f['path']==path)]
                assert len(fields)==1;i,f=fields[0]
                return ['field',s['seq'],i],{'owner':f['owner'],'field':f['field'],'version':f['version'],'source_call_id':s['source_call_id'],'path':f['path']}
            text=[field(s,'text')for s in stores];assert text[0][1]['owner']!=text[1][1]['owner']
            choices=[field(gates[0],'drop','/flags/'+str(i)+'/drop')for i in range(2)]if direct else[field(gates[0],'index')]
            ids=[]if direct else[field(s,'id')for s in stores]
            expected=None if c['case']==2 else {'origins':[text[c['case']][0]],'selectors':[x[0]for x in choices]+([]if direct else[ids[0][0],ids[1][0]])}
            truth.append({'case':c['case'],'message':c['message'],'expected':expected,'raw_text_fields':text,'raw_id_fields':ids,'raw_choice_fields':choices})
        save(d/'truth-before-prediction.json',truth)
        replay=infer_execution(plan,rows);checks=[];norm=[]
        for t in truth:
            ret=next(r for r in rows if r['kind']=='binding-return'and r['message']==t['message'])
            answers=[a for a in replay['answers']if a['root_frame']==ret['frame']and a['field']==fixture+'$Box.text']
            if t['expected'] is None:
                assert len(answers)==2 and all(not a['known']for a in answers)
                norm.extend([{'case':t['case'],'known':False}for a in answers])
            else:
                assert len(answers)==1;a=answers[0];want=t['expected']
                data_ok=a['known']and set(map(tuple,a['origins']))==set(map(tuple,want['origins']))
                selection_ok=set(map(tuple,a['selectors']))==set(map(tuple,want['selectors']))
                version_ok=a['owner']==t['raw_text_fields'][t['case']][1]['owner']and a['version']==t['raw_text_fields'][t['case']][1]['version']
                roles={tuple(x[0]):'Store.read[%d].text'%i for i,x in enumerate(t['raw_text_fields'])}
                roles.update({tuple(x[0]):'Store.read[%d].id'%i for i,x in enumerate(t['raw_id_fields'])})
                roles.update({tuple(x[0]):'Gate.read.choice[%d]'%i for i,x in enumerate(t['raw_choice_fields'])})
                norm.append({'case':t['case'],'known':a['known'],'version':a['version'],
                    'actual_data_roles':sorted(roles[tuple(x)]for x in a['origins']),
                    'actual_selector_roles':sorted(roles[tuple(x)]for x in a['selectors']),
                    'data_correct':data_ok,'selection_correct':selection_ok,'version_correct':version_ok})
            checks.append({'case':t['case'],'answers':answers,'expected':t['expected']})
        guards=[]
        for fault in ('missing-predicate-frame','duplicate-predicate-frame','wrong-predicate-object','missing-choice-source-field'):
            changed=copy.deepcopy(rows);call=next(r for r in changed if r['kind']=='collection-call-enter'and r.get('remove_if_start'))
            frame=next(r for r in changed if r['kind']=='enter'and r.get('callback_call_id')==call['call_id'])
            if fault=='missing-predicate-frame':changed.remove(frame)
            elif fault=='duplicate-predicate-frame':changed.insert(changed.index(frame),copy.deepcopy(frame))
            elif fault=='wrong-predicate-object':call['remove_if_start']['predicate']={'object':'wrong'}
            else:
                source=next(r for r in changed if r['kind']=='binding-source'and '$Gate.read' in r['callee']);source['fields']=[f for f in source['fields']if f['path']!='/flags/0/drop']if direct else[f for f in source['fields']if not f['field'].endswith('.index')]
            try:bad=infer_execution(plan,changed)
            except (ValueError,KeyError):guards.append({'fault':fault,'state':'rejected'})
            else:
                root=next(r for r in changed if r['kind']=='binding-return'and r.get('message')==truth[0]['message'])['frame']
                guarded=all(not a['known']for a in bad['answers']if a['root_frame']==root)
                guards.append({'fault':fault,'state':'unknown'if guarded else'incorrect_known_answer','answers':[a for a in bad['answers']if a['root_frame']==root]})
        positive=[n for n in norm if n['case']!=2]
        normalized[mode]=norm;results[mode]={'business_preserved':True,'positive_targets':2,
            'data_correct':sum(n['data_correct']for n in positive),
            'version_correct':sum(n['version_correct']for n in positive),
            'expected_nonempty_selector_targets':2,'correct_nonempty_selector_targets':sum(n['selection_correct']for n in positive),
            'required_unknown_targets':2,'checks':checks,'guards':guards,
            'correctness_gate_passed':all(n['data_correct']and n['version_correct']and n['selection_correct']for n in positive)and not any(g['state']=='incorrect_known_answer'for g in guards)}
        save(d/'checks.json',results[mode])
    assert normalized['full']==normalized['static']==normalized['selective']
    save(out/'normalized.json',normalized)
    save(out/'results.json',{'fixture':fixture,'Agent_sha256':sha(AGENT),'plan_sha256':sha(out/'plan.json'),'modes':results,'normalized_equal':True,'correctness_gate_passed':all(r['correctness_gate_passed']for r in results.values()),'original_expected_selectors_not_relaxed':True,'static_label':'fixed-permission/body-off','new_business_coverage':False,'body_reduction_claim':False})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--direct-predicate',action='store_true');a=p.parse_args();run(a.out.resolve(),a.direct_predicate)
