"""Earlier callbacks can leave state used by a later factory/type-handler.

Neither callback timing nor identical final values may certify these cases.
"""
import argparse
import json
from pathlib import Path
from zipfile import ZipFile
from run_planned_service import ROOT,HERE,load,save,sha
from run_query_planner import command,JARS
from build_distributed_plans import build
from plan_capability_policy import choose
from infer_execution_kernel import infer_execution


def run(out):
    out.mkdir(parents=True,exist_ok=False);classes=out/'classes';classes.mkdir()
    directory=ROOT/'artifacts/portability-first-20261028/metadata/zlt-user/libs'
    deps=[p for p in directory.glob('*.jar')if p.name.startswith(('mybatis-','mybatis-plus-',
        'spring-core-','spring-beans-','spring-context-','spring-tx-','spring-jcl-','spring-jdbc-',
        'spring-expression-','slf4j-api-'))]
    deps.append(ROOT/'artifacts/portability-first-20261028/metadata/febs-system/libs/h2-1.4.200.jar')
    bootstrap=ROOT/'artifacts/zlt-completion-slice-20261031/final-candidate-01/historical/frozen-base/distributed-observer.jar'
    java='/usr/lib/jvm/java-8-openjdk-amd64/bin/java'
    cp=':'.join(map(str,[bootstrap,*deps,*JARS]))
    command([java[:-4]+'javac','-cp',cp,'-d',str(classes),str(HERE/'SqlPreallocationStateFixture.java')],out/'compile.log')
    jar=out/'fixture.jar'
    with ZipFile(jar,'w')as z:
        for p in classes.glob('SqlPreallocationStateFixture*.class'):z.write(p,'BOOT-INF/classes/'+p.name)
        for p in deps:z.write(p,'BOOT-INF/lib/'+p.name)
    b=out/'build';build(b,{'fixture':{'jar':str(jar),'targets':['SqlPreallocationStateFixture$Row.text']}})
    plan,route=choose(load(b/'fixture/model.json'),{'entry':'SqlPreallocationStateFixture.root(I)LSqlPreallocationStateFixture$Result;',
       'target':'SqlPreallocationStateFixture$Row.text','path':'/rows/*/text',
       'source_calls':['SqlPreallocationStateFixture$Store.read(Ljava/util/Map;)Ljava/util/List;']})
    save(b/'fixture/plan.json',plan);save(out/'route.json',route)
    cp=':'.join(map(str,[classes,b/'distributed-observer.jar',*deps,*JARS]))
    baseline=json.loads(command([java,'-Dfixture.preallocation=true','-cp',cp,'SqlPreallocationStateFixture'],out/'baseline.log').stdout.splitlines()[-1])
    modes={}
    for mode in ('full','selective'):
        cap=out/mode;cap.mkdir()
        result=command([java,'-Dfixture.preallocation=true','-javaagent:'+str(b/'distributed-observer.jar'),
          '-Dservice.plan='+str(b/'fixture/plan.json'),'-Dservice.events='+str(cap/'events.jsonl'),
          '-Dservice.mode='+mode,'-cp',cp,'SqlPreallocationStateFixture'],cap/'stdout.log')
        assert json.loads(result.stdout.splitlines()[-1])==baseline
        rows=[json.loads(s)for s in(cap/'events.jsonl').read_text().splitlines()]
        assert not any(r['kind']=='problem'for r in rows)
        inference=infer_execution(plan,rows);save(cap/'inference.json',inference)
        assert len(inference['answers'])==4 and not any(a['known']for a in inference['answers'])
        certificates=[r for r in rows if r['kind']=='sql-locality-end']
        assert len(certificates)==2 and not any(c['valid']for c in certificates)
        details=[]
        for c in certificates:
            events=[r for r in rows if r.get('ownership_id')==c['ownership_id']]
            callbacks=[r for r in events if r['kind']=='sql-locality-callback-end']
            mapping=[r for r in events if r['kind']=='sql-locality-result-begin']
            assert callbacks and mapping and max(r['seq']for r in callbacks)<min(r['seq']for r in mapping)
            details.append({'callback_completed_before_mapping':True,'valid':c['valid'],'reason':c['reason']})
        modes[mode]={'business_equal':True,'targets':4,'known':0,'unknown':4,
                     'earlier_callback_does_not_certify_later_state':details,'raw_sha256':sha(cap/'events.jsonl')}
    save(out/'results.json',{'modes':modes,'agent_sha256':sha(b/'distributed-observer.jar'),
          'observers_call_unknown_application_methods':False,'original_fixture_source_sha256':sha(HERE/'SqlPreallocationStateFixture.java')})
    print(json.dumps(modes))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);run(p.parse_args().out.resolve())
