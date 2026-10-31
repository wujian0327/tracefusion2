"""Actual default MyBatis/H2 path, and actual same-object publication controls."""
import argparse,copy,json
from pathlib import Path
from zipfile import ZipFile
from run_query_planner import command,JARS
from run_planned_service import ROOT,HERE,load,save
from build_distributed_plans import build
from plan_capability_policy import choose
from infer_execution_kernel import infer_execution


def run(out):
    out.mkdir(parents=True,exist_ok=False);classes=out/'classes';classes.mkdir()
    java='/usr/lib/jvm/java-8-openjdk-amd64/bin/java'
    directory=ROOT/'artifacts/portability-first-20261028/metadata/zlt-user/libs'
    deps=[p for p in directory.glob('*.jar') if p.name.startswith(('mybatis-','mybatis-plus-',
        'spring-core-','spring-beans-','spring-context-','spring-tx-','spring-jcl-','spring-jdbc-',
        'spring-expression-','slf4j-api-'))]
    deps.append(ROOT/'artifacts/portability-first-20261028/metadata/febs-system/libs/h2-1.4.200.jar')
    bootstrap=ROOT/'artifacts/zlt-completion-slice-20261031/sql-models-02/build/distributed-observer.jar'
    cp=':'.join(map(str,[bootstrap,*deps,*JARS]))
    command([java[:-4]+'javac','-cp',cp,'-d',str(classes),str(HERE/'SqlResultLocalityFixture.java')],out/'compile.log')
    jar=out/'fixture.jar'
    with ZipFile(jar,'w') as z:
        for p in classes.glob('SqlResultLocalityFixture*.class'):z.write(p,'BOOT-INF/classes/'+p.name)
        for p in deps:z.write(p,'BOOT-INF/lib/'+p.name)
    b=out/'build';build(b,{'fixture':{'jar':str(jar),'targets':['SqlResultLocalityFixture$Row.text']}})
    plan,route=choose(load(b/'fixture/model.json'),{'entry':'SqlResultLocalityFixture.root(I)LSqlResultLocalityFixture$Result;',
        'target':'SqlResultLocalityFixture$Row.text','path':'/rows/*/text',
        'source_calls':['SqlResultLocalityFixture$Store.read(Ljava/util/Map;)Ljava/util/List;']})
    assert plan['execution_kernel'].get('sql_result_locality');save(b/'fixture/plan.json',plan);save(out/'route.json',route)
    cp=':'.join(map(str,[classes,b/'distributed-observer.jar',*deps,*JARS]))
    baseline=json.loads(command([java,'-cp',cp,'SqlResultLocalityFixture'],out/'baseline.log').stdout.splitlines()[-1]);reports={}
    for mode in ('full','selective'):
        cap=out/mode;cap.mkdir()
        observed=command([java,'-javaagent:'+str(b/'distributed-observer.jar'),'-Dservice.plan='+str(b/'fixture/plan.json'),
            '-Dservice.events='+str(cap/'events.jsonl'),'-Dservice.mode='+mode,'-cp',cp,'SqlResultLocalityFixture'],cap/'stdout.log')
        assert json.loads(observed.stdout.splitlines()[-1])==baseline
        rows=[json.loads(s) for s in (cap/'events.jsonl').read_text().splitlines()]
        assert not any(r['kind']=='problem' for r in rows),[r for r in rows if r['kind']=='problem']
        result=infer_execution(plan,rows);answers=result['answers'];save(cap/'inference.json',result)
        assert len(answers)==18
        state=[]
        for expected in baseline:
            root=next(r['frame'] for r in rows if r['kind']=='binding-return' and r['message']==expected['message'])
            group=[a for a in answers if a['root_frame']==root];assert len(group)==2
            source=next(r for r in rows if r['kind']=='binding-source' and r.get('message')==expected['message'])
            for a in group:
                index=int(a['path'].split('/')[2]);should_know=expected['mode'] in (0,4,7) or expected['mode']==6 and index==1
                assert a['known']==should_know,(expected['mode'],group)
                if not should_know:continue
                origins=set(map(tuple,a['origins']))
                if expected['mode']==4 and index==0:assert not origins
                else:
                    i=next(i for i,f in enumerate(source['fields']) if f['path']=='/'+str(index)+'/text')
                    assert origins=={('field',source['seq'],i)}
            state.append({'mode':expected['mode'],'known':sum(a['known'] for a in group)})
        guards={}
        for fault in ('missing-birth','missing-handler','wrong-call','missing-close','duplicate-meta','missing-class','missing-callback','late-callback','missing-handler-state'):
            bad=copy.deepcopy(rows)
            if fault=='missing-birth':bad.remove(next(r for r in bad if r['kind']=='sql-locality-birth'))
            elif fault=='missing-handler':bad.remove(next(r for r in bad if r['kind']=='sql-locality-handler'))
            elif fault=='wrong-call':next(r for r in bad if r['kind']=='sql-locality-birth')['call_id']=-1
            elif fault=='missing-close':bad.remove(next(r for r in bad if r['kind']=='sql-locality-close'))
            elif fault=='duplicate-meta':bad.append(copy.deepcopy(next(r for r in bad if r['kind']=='sql-locality-meta')))
            elif fault=='missing-callback':bad.remove(next(r for r in bad if r['kind']=='sql-locality-callback-end'))
            elif fault=='late-callback':next(r for r in bad if r['kind']=='sql-locality-callback-end')['seq']=max(r['seq']for r in bad)
            elif fault=='missing-handler-state':bad.remove(next(r for r in bad if r['kind']=='sql-locality-handler-state'))
            else:bad=[r for r in bad if not(r['kind']=='sql-locality-class' and r['class']=='org/apache/ibatis/reflection/factory/DefaultObjectFactory')]
            try:infer_execution(plan,bad)
            except ValueError:guards[fault]=True
            else:raise AssertionError(fault)
        invalid=out/(mode+'-nested-mapping');invalid.mkdir()
        ordinary=command([java,'-Dfixture.nested.mapping=true','-cp',cp,'SqlResultLocalityFixture'],invalid/'baseline.log')
        instrumented=command([java,'-javaagent:'+str(b/'distributed-observer.jar'),'-Dfixture.nested.mapping=true','-Dservice.plan='+str(b/'fixture/plan.json'),'-Dservice.events='+str(invalid/'events.jsonl'),'-Dservice.mode='+mode,'-cp',cp,'SqlResultLocalityFixture'],invalid/'stdout.log')
        assert json.loads(ordinary.stdout.splitlines()[-1])==json.loads(instrumented.stdout.splitlines()[-1])
        invalid_rows=[json.loads(s)for s in(invalid/'events.jsonl').read_text().splitlines()]
        assert not any(r['valid']for r in invalid_rows if r['kind']=='sql-locality-end')
        from external_transfer_oracle import require_complete_raw_capture
        try:require_complete_raw_capture(invalid_rows)
        except ValueError:pass
        else:raise AssertionError('Damaged batch accepted')
        reports[mode]={'business_equal':True,'states':state,'guards':guards,'post_callback_mapping_rejected':True,'thread_state_clean':True}
    save(out/'results.json',reports);print(reports)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True)
    run(p.parse_args().out.resolve())
