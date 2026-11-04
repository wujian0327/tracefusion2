"""Finite constructor-effect positives, same-value mutation and publication."""
import argparse,copy,json
from pathlib import Path
from zipfile import ZipFile
from run_planned_service import ROOT,HERE,load,save,sha
from run_query_planner import command,JARS
from build_distributed_plans import build
from plan_capability_policy import choose
from infer_execution_kernel import infer_execution


def run(out,agent):
    out.mkdir(parents=True,exist_ok=False);classes=out/'classes';classes.mkdir();java='/usr/lib/jvm/java-8-openjdk-amd64/bin/java'
    libs=sorted((ROOT/'artifacts/ruoyi-request-scope-20261104/scope-controls-02/deps').glob('*.jar'));cp=':'.join(map(str,[classes,agent,*JARS,*libs]))
    command([java[:-4]+'javac','-cp',cp,'-d',str(classes),str(HERE/'MapConstructorEffectsFixture.java')],out/'compile.log')
    jar=out/'fixture.jar'
    with ZipFile(jar,'w')as z:
        for f in classes.glob('*.class'):z.write(f,'BOOT-INF/classes/'+f.name)
    b=out/'build';build(b,{'fixture':{'jar':str(jar),'targets':['MapConstructorEffectsFixture$Box.text']}})
    plan,route=choose(load(b/'fixture/model.json'),{'entry':'MapConstructorEffectsFixture.root(LMapConstructorEffectsFixture$Store;I)LMapConstructorEffectsFixture$Wrap;','target':'MapConstructorEffectsFixture$Box.text','path':'/data/text','source_calls':['MapConstructorEffectsFixture$Store.read()LMapConstructorEffectsFixture$Box;']},deployment=load(ROOT/'artifacts/target-closure-revision-20261103/external-first-01/deployment-environment.json'))
    save(out/'plan.json',plan);save(out/'route.json',route);print('constructors',[(k,v['kind'])for k,v in plan['execution_kernel']['constructors'].items()],flush=True)
    base=json.loads(command([java,'-cp',cp,'MapConstructorEffectsFixture'],out/'baseline.log').stdout.splitlines()[-1]);reports={}
    for mode in('full','selective'):
        d=out/mode;d.mkdir();actual=json.loads(command([java,'-javaagent:'+str(agent),'-Dfixture.observe=true','-Dservice.plan='+str(out/'plan.json'),'-Dservice.mode='+mode,'-Dservice.events='+str(d/'events.jsonl'),'-cp',cp,'MapConstructorEffectsFixture'],d/'stdout.log').stdout.splitlines()[-1]);assert [{k:v for k,v in r.items()if k!='message'}for r in actual]==base
        rows=[json.loads(x)for x in(d/'events.jsonl').read_text().splitlines()];assert not any(r['kind']=='problem'for r in rows),[r for r in rows if r['kind']=='problem']
        replay=infer_execution(plan,rows);checks=[]
        from infer_distributed_fields import Reconstruction
        (d/'build/role').mkdir(parents=True);(d/'capture/role').mkdir(parents=True)
        (d/'build/role/plan.json').write_bytes((out/'plan.json').read_bytes());(d/'capture/role/events.jsonl').symlink_to((d/'events.jsonl').resolve())
        graph=Reconstruction(d/'build',d/'capture',['role'])
        for case in actual:
            ret=next(r for r in rows if r['kind']=='binding-return'and r['message']==case['message']);answer=next(a for a in replay['answers']if a['root_frame']==ret['frame']and a['path']=='/data/text');assert answer['known']==(case['mode']in(0,3)),(mode,case,answer)
            end_to_end=graph.query(case['message'],'/data/text','role',boundary=[{'kind':'binding-source'},{'kind':'argument'}]);assert end_to_end['known']==answer['known'],end_to_end
            if answer['known']:
                source=next(r for r in rows if r['kind']=='binding-source'and r.get('message')==case['message']and r['callee'].startswith('MapConstructorEffectsFixture$Store.read'));index=next(i for i,f in enumerate(source['fields'])if f['field']=='MapConstructorEffectsFixture$Box.text');assert set(map(tuple,answer['origins']))=={('field',source['seq'],index)}
            checks.append({'case':case['mode'],'known':answer['known']})
        guards=[]
        for fault in('proof-missing','class-hash','wrapper-owner','initializer-foreign','initializer-missing'):
            altered=copy.deepcopy(rows);fact=next(r for r in altered if'map_constructor_effect'in r)
            if fault=='proof-missing':fact.pop('map_constructor_effect')
            elif fault=='class-hash':fact['map_constructor_effect']['class_sha256']={}
            elif fault=='wrapper-owner':fact['map_wrappers'][0]['owner']='foreign'
            elif fault=='initializer-foreign':fact['map_constructor_effect']['initialized_helpers'][0]['seq']=-1
            else:fact['map_constructor_effect']['initialized_helpers']=[]
            try:
                changed=infer_execution(plan,altered);assert fault=='initializer-missing'and not next(a for a in changed['answers']if a['root_frame']==fact['frame'])['known']
            except ValueError:pass
            guards.append(fault)
        reports[mode]={'business_equal':True,'cases':checks,'guards':guards}
    late=[]
    for mode in('full','selective'):
        d=out/(mode+'-late');d.mkdir()
        command([java,'-javaagent:'+str(agent),'-Dfixture.observe=true','-Dfixture.late=true','-Dservice.plan='+str(out/'plan.json'),'-Dservice.mode='+mode,'-Dservice.events='+str(d/'events.jsonl'),'-cp',cp,'MapConstructorEffectsFixture'],d/'stdout.log')
        rows=[json.loads(x)for x in(d/'events.jsonl').read_text().splitlines()];assert not any(r['kind']=='problem'for r in rows)
        answers=infer_execution(plan,rows)['answers'];assert [a['known']for a in answers]==[False,False,False,True]
        late.append({'mode':mode,'first_root_unknown':True,'later_qualified_root_known':True,'complete_valid_capture':True})
    save(out/'results.json',{'agent_sha256':sha(agent),'modes':reports,'late_initialization':late});print(reports,late,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--agent',type=Path,required=True);a=p.parse_args();run(a.out.resolve(),a.agent.resolve())
