#!/usr/bin/env python3
"""Real Mongo/Spring saves, independent root-argument truth and conservative callbacks."""
import argparse,json,copy,secrets,time
from pathlib import Path
from zipfile import ZipFile
from build_distributed_plans import build
from experiment_environment import java8_target
from run_query_planner import command,JARS
from run_planned_service import ROOT,HERE,save,load
from infer_distributed_fields import Reconstruction
from infer_execution_kernel import infer_execution
import run_response_binding_revision as old

def run(out,libs,base):
    out.mkdir(parents=True,exist_ok=False);classes=out/'classes';classes.mkdir();cp=':'.join(map(str,[*JARS,*sorted(libs.glob('*.jar'))]));compile_cp=cp+':'+str(base/'tools')
    command(['javac',*java8_target()[1],'-cp',compile_cp,'-d',str(classes),str(HERE/'MongoEffectFixture.java')],out/'compile.log');jar=out/'fixture.jar'
    with ZipFile(jar,'w') as z:
        for f in classes.glob('*.class'):z.write(f,'BOOT-INF/classes/'+f.name)
    b=out/'build';build(b,{'fixture':{'jar':str(jar),'entry':'MongoEffectFixture.root(Lorg/springframework/data/mongodb/repository/MongoRepository;Ljava/lang/String;I)LMongoEffectFixture$Out;','targets':['MongoEffectFixture$Out.text'],'response_path':'/text','execution_kernel':True,'application_calls':True,'async_dependencies':True}})
    # Same immutable Mongo image as the original Sock Shop deployment.
    image=load(ROOT/'artifacts/async-dependency-revision-20261021/business-frozen-first/full-sockshop-orders-newOrder-customer-username/capture/compose.json')['services']['orders-db']['image'];spec={'services':{'mongo':{'image':image,'ports':['127.0.0.1:19827:27017']}}};save(out/'compose.json',spec)
    dep=old.CachedDeployment(argparse.Namespace(project='tf2-mongo-effects-'+secrets.token_hex(5),ready_timeout=90),out,out/'compose.json');reports={};state={'status':'failed'}
    try:
        image_state=dep.command(['docker','image','inspect',image]);(out/'image-inspect.json').write_text(image_state.stdout);dep.compose('up','-d','--pull','never',timeout=120)
        for attempt in range(60):
            r=dep.compose('exec','-T','mongo','mongo','--quiet','--eval','db.runCommand({ping:1})',check=False)
            if r.returncode==0:break
            time.sleep(1)
        else:raise RuntimeError('Control Mongo not ready')
        for mode in ('full','selective'):
            cap=out/mode;(cap/'fixture').mkdir(parents=True);command(['java','-javaagent:'+str(b/'distributed-observer.jar'),'-Dservice.plan='+str(b/'fixture/plan.json'),'-Dservice.mode='+mode,'-Dservice.events='+str(cap/'fixture/events.jsonl'),'-cp',str(classes)+':'+cp,'MongoEffectFixture','19827'],cap/'stdout.log')
            g=Reconstruction(b,cap,['fixture']);rows=g.rows['fixture'];cases=json.loads((cap/'stdout.log').read_text().splitlines()[-1]);checks=[]
            for c in cases:
                assert c['response']['text']==('FALLBACK' if c['mode']==5 else 'SAME'),c
                a=g.query(c['message'],'/text','fixture',boundary=old.BOUNDARY);known=c['mode'] in (0,5,6);assert a['known']==known,(mode,c,a)
                expected={1} if c['mode'] in (0,6) else set()
                if known:
                    root=next(r for r in rows if r['kind']=='binding-return' and r.get('message')==c['message']);assert len(a['sources'])==len(expected) and {int(s['field'].split(':')[1]) for s in a['sources']}==expected and all(s['root_frame']==root['frame'] for s in a['sources']),(mode,c,a)
                checks.append({'case':c,'answer':a,'expected_root_arguments':sorted(expected) if known else None})
            faults={};normal=next(r for r in rows if r['kind']=='mongo-save-effect' and r.get('valid'))
            for label in ('missing-save-proof','save-class-hash','save-registry','executed-handler','listener-verification','wrong-saved-entity','save-ID-version','missing-ID-write','unexpected-saved-field'):
                changed=copy.deepcopy(rows);proof=next(r for r in changed if r['seq']==normal['seq'])
                if label=='missing-save-proof':changed.remove(proof)
                elif label=='save-class-hash':proof['class_sha256']['org/springframework/data/mongodb/core/MongoTemplate']='wrong'
                elif label=='save-registry':proof['registry']['forged']=['custom']
                elif label=='executed-handler':proof['callback_invocations']=1
                elif label=='listener-verification':proof['listeners_verified']=False
                elif label=='wrong-saved-entity':proof['result']['object']='wrong-object'
                elif label=='save-ID-version':proof['id_write']['version']+=1
                elif label=='missing-ID-write':changed.remove(next(r for r in changed if r['seq']==proof['id_write']['seq']))
                else:next(f for f in proof['after'] if f['field'].endswith('.text'))['observed']['value']='DIFFERENT'
                try:infer_execution(g.plans['fixture'],changed)
                except ValueError:faults[label]=True
                else:raise AssertionError('Accepted '+label)
            reports[mode]={'targets':len(checks),'known_exact':sum(x['answer']['known'] for x in checks),'expected_unknown':sum(not x['answer']['known'] for x in checks),'faults':faults,'save_scopes_closed':True,'checks':checks};save(out/'results.json',{'all_passed':True,'modes':reports});print(mode,{k:v for k,v in reports[mode].items() if k!='checks'},flush=True)
        state['status']='completed'
    finally:
        r=dep.compose('down','--volumes','--remove-orphans',check=False);state['cleanup_returncode']=r.returncode;save(out/'cleanup.json',state)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--libs',type=Path,required=True);p.add_argument('--base-build',type=Path,required=True);a=p.parse_args();run(a.out.resolve(),a.libs.resolve(),a.base_build.resolve())
