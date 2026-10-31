import argparse,copy,json
from pathlib import Path
from zipfile import ZipFile
from run_planned_service import ROOT,HERE,load,save
from run_query_planner import command,JARS
from build_distributed_plans import build
from infer_execution_kernel import infer_execution


def run(out):
    out.mkdir(parents=True,exist_ok=False);classes=out/'classes';classes.mkdir()
    java='/usr/lib/jvm/java-8-openjdk-amd64/bin/java';agent=ROOT/'artifacts/zlt-completion-slice-20261031/body-controls-02/build/distributed-observer.jar'
    command([java[:-4]+'javac','-cp',':'.join(map(str,[agent,*JARS])),'-d',str(classes),str(HERE/'LongValueFixture.java')],out/'compile.log')
    jar=out/'fixture.jar'
    with ZipFile(jar,'w') as z:
        for p in classes.glob('*.class'):z.write(p,'BOOT-INF/classes/'+p.name)
    b=out/'build';build(b,{'fixture':{'jar':str(jar),'entry':'LongValueFixture.root(JJ)LLongValueFixture$Result;',
        'targets':['LongValueFixture$Result.first'],'response_path':'/first','execution_kernel':True,'application_calls':True}})
    plan=load(b/'fixture/plan.json');cp=':'.join(map(str,[classes,b/'distributed-observer.jar',*JARS]))
    baseline=json.loads(command([java,'-cp',cp,'LongValueFixture'],out/'baseline.log').stdout.splitlines()[-1]);assert all(c['same_box']for c in baseline[:4])
    reports={}
    from plan_response_binding import plan_response
    model=load(b/'fixture/model.json')
    for mode in ('full','selective'):
        guards={};count=0
        for field in ('first','second','unboxed'):
            plan=plan_response(model,'LongValueFixture.root(JJ)LLongValueFixture$Result;','LongValueFixture$Result.'+field,'/'+field,execution_kernel=True,application_calls=True)
            cap=out/(mode+'-'+field);cap.mkdir();save(cap/'plan.json',plan)
            actual=command([java,'-javaagent:'+str(b/'distributed-observer.jar'),'-Dservice.plan='+str(cap/'plan.json'),'-Dservice.events='+str(cap/'events.jsonl'),'-Dservice.mode='+mode,'-cp',cp,'LongValueFixture'],cap/'stdout.log')
            assert json.loads(actual.stdout.splitlines()[-1])==baseline
            rows=[json.loads(s)for s in(cap/'events.jsonl').read_text().splitlines()];assert not any(r['kind']=='problem'for r in rows)
            answers=infer_execution(plan,rows)['answers'];assert len(answers)==6 and all(a['known']for a in answers)
            for a in answers:assert set(map(tuple,a['origins']))=={('argument',a['root_frame'],0 if field=='first'else 1)},a
            count+=len(answers)
            for fault in ('wrong-box-value','wrong-unbox-value','missing-proof'):
                bad=copy.deepcopy(rows);row=next(r for r in bad if r.get('sequence_value',{}).get('callee')==('java/lang/Long.longValue()J'if fault=='wrong-unbox-value'else'java/lang/Long.valueOf(J)Ljava/lang/Long;'))
                if fault=='missing-proof':row.pop('sequence_value')
                else:row['result']['value']+=1
                try:infer_execution(plan,bad)
                except ValueError:guards[field+'-'+fault]=True
                else:raise AssertionError(fault)
        reports[mode]={'business_equal':True,'known_positional_matches':count,'same_cached_box_different_argument_origins':True,'extreme_values':True,'guards':guards}
    save(out/'results.json',reports);print(reports)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);run(p.parse_args().out.resolve())
