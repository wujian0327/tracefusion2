"""Real JVM wrapper observation and non-invocation/invalidity controls."""
import argparse,copy,json
from pathlib import Path
from zipfile import ZipFile
from run_planned_service import ROOT,HERE,load,save,sha
from run_query_planner import JARS,command
from build_distributed_plans import build
from plan_capability_policy import choose
from infer_map_wrapper import validate


def run(out):
    out.mkdir(parents=True,exist_ok=False);classes=out/'classes';classes.mkdir();java='/usr/lib/jvm/java-8-openjdk-amd64/bin/java'
    command([java[:-4]+'javac','-d',str(classes),str(HERE/'MapWrapperFixture.java')],out/'compile.log')
    fixture=out/'fixture.jar'
    with ZipFile(fixture,'w')as z:
        for p in classes.glob('*.class'):z.write(p,'BOOT-INF/classes/'+p.name)
    b=out/'build';build(b,{'fixture':{'jar':str(fixture),'targets':['MapWrapperFixture$DTO.text']}})
    plan,route=choose(load(b/'fixture/model.json'),{'entry':'MapWrapperFixture.root(I)LMapWrapperFixture$Wrapper;','target':'MapWrapperFixture$DTO.text','path':'/data/text'},
        deployment=load(ROOT/'artifacts/target-closure-revision-20261103/external-first-01/deployment-environment.json'))
    # This control tests physical return snapshots, not communication or origin.
    plan.pop('communication_identity',None);save(out/'plan.json',plan);save(out/'route.json',route)
    cp=':'.join(map(str,[classes,b/'distributed-observer.jar',*JARS]));results=[]
    for case in range(6):
        base=command([java,'-cp',cp,'MapWrapperFixture',str(case)],out/('original-%d.log'%case)).stdout.splitlines()[-1]
        for mode in('full','selective'):
            d=out/('%s-%d'%(mode,case));d.mkdir()
            actual=command([java,'-javaagent:'+str(b/'distributed-observer.jar'),'-Dservice.plan='+str(out/'plan.json'),'-Dservice.events='+str(d/'events.jsonl'),'-Dservice.mode='+mode,'-cp',cp,'MapWrapperFixture',str(case)],d/'stdout.log').stdout.splitlines()[-1]
            assert json.loads(base)==json.loads(actual)
            rows=[json.loads(x)for x in(d/'events.jsonl').read_text().splitlines()];bad=any(r['kind']=='problem'for r in rows)
            assert bad==(case in(2,3,4)),(mode,case)
            if case in(0,1):
                validate(plan,rows);ret=next(r for r in rows if r['kind']=='binding-return');assert any(f['path']=='/data/text'for f in ret['fields']);assert ret['map_wrappers']
                guards=[]
                for fault in('missing','hash','owner','runtime','duplicate','shape','loader','missing-class','duplicate-class'):
                    altered=copy.deepcopy(rows);r=next(r for r in altered if r['kind']=='binding-return');p=r['map_wrappers'][0]
                    if fault=='missing':r.pop('map_wrappers')
                    elif fault=='hash':p['chain'][0]['class_sha256']='wrong'
                    elif fault=='owner':p['owner']='wrong'
                    elif fault=='runtime':p['runtime']['java_runtime_version']='wrong'
                    elif fault=='duplicate':r['map_wrappers'].append(copy.deepcopy(p))
                    elif fault=='shape':p['entries']+=1
                    elif fault=='loader':p['loaders'][0]='wrong'
                    elif fault=='missing-class':altered.remove(next(e for e in altered if e['kind']=='map-wrapper-class'))
                    else:altered.append(copy.deepcopy(next(e for e in altered if e['kind']=='map-wrapper-class')))
                    try:validate(plan,altered)
                    except ValueError:guards.append(fault)
                    else:raise AssertionError(fault)
                save(d/'guards.json',guards)
            results.append({'mode':mode,'case':case,'business_equal':True,'invalid':bad,'binding_return':sum(r['kind']=='binding-return'for r in rows)})
    save(out/'results.json',{'agent_sha256':sha(b/'distributed-observer.jar'),'cases':results,'scope':'Observation/binding only, never counted as source accuracy.'});print('Map wrapper controls passed',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args();run(a.out.resolve())
