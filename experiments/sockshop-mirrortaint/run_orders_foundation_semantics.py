#!/usr/bin/env python3
"""Actual JVM effects, independent parameter-field truth and conservative failures."""
import argparse,copy,json
from pathlib import Path
from zipfile import ZipFile
from build_distributed_plans import build
from experiment_environment import java8_target
from run_query_planner import command,JARS
from run_planned_service import ROOT,HERE,load,save
from infer_distributed_fields import Reconstruction
from infer_execution_kernel import infer_execution
import run_response_binding_revision as old

def run(out):
    out.mkdir(parents=True,exist_ok=False);classes=out/'classes';classes.mkdir();base=ROOT/'artifacts/call-lifecycle-revision-20261020/base-build'
    command(['javac',*java8_target()[1],'-cp',':'.join(map(str,[base/'tools',*JARS])),'-d',str(classes),str(HERE/'OrdersFoundationFixture.java')],out/'compile.log');jar=out/'fixture.jar'
    with ZipFile(jar,'w') as z:
        for f in classes.glob('*.class'):z.write(f,'BOOT-INF/classes/'+f.name)
    b=out/'build';build(b,{'fixture':{'jar':str(jar),'entry':'OrdersFoundationFixture.root(LOrdersFoundationFixture$Item;LOrdersFoundationFixture$Item;I)LOrdersFoundationFixture$Out;','targets':['OrdersFoundationFixture$Out.text'],'response_path':'/text','execution_kernel':True,'application_calls':True}})
    p=load(b/'fixture/plan.json');expected={0:[0,1],1:[0],2:None,3:[0],4:[],5:[],6:None,7:None,8:[],9:None,11:[],12:[0],13:None,14:None,15:[0]};reports={}
    inner=next(v for k,v in p['execution_kernel']['constructors'].items() if '$Inner.<init>' in k);assert inner['kind']=='opaque' and 'Pre-initialization' in inner['reason']
    for mode in ('full','selective'):
        cap=out/mode;(cap/'fixture').mkdir(parents=True);command(['java','-javaagent:'+str(b/'distributed-observer.jar'),'-Dservice.plan='+str(b/'fixture/plan.json'),'-Dservice.mode='+mode,'-Dservice.events='+str(cap/'fixture/events.jsonl'),'-cp',str(classes)+':'+':'.join(map(str,JARS)),'OrdersFoundationFixture'],cap/'stdout.json')
        cases=json.loads((cap/'stdout.json').read_text().splitlines()[-1]);g=Reconstruction(b,cap,['fixture']);rows=g.rows['fixture'];checks=[]
        for c in cases:
            if c['status']=='aborted':continue
            a=g.query(c['message'],'/text','fixture',boundary=old.BOUNDARY);want=expected[c['mode']];assert a['known']==(want is not None),(mode,c,a)
            truth=set()
            if want is not None:
                for index in want:
                    source=next(r for r in rows if r['kind']=='binding-input' and r.get('message')==c['message'] and r['argument']==index);f=next(f for f in source['fields'] if f['field']=='OrdersFoundationFixture$Item.text');truth.add(old.source_coord('fixture',source,f))
                assert {old.predicted_coord(s) for s in a['sources']}==truth,(mode,c,a,truth)
            checks.append({'case':c,'expected_arguments':want,'truth':sorted(truth,key=str),'answer':a})
        faults={}
        for label in ('missing-constructor-begin','wrong-constructor-id','wrong-constructor-argument','missing-constructor-throw','wrong-static-field','builder-runtime-hash','wrong-builder-return','missing-render-frame','wrong-render-argument'):
            changed=copy.deepcopy(rows)
            if label=='missing-constructor-begin':changed.remove(next(r for r in changed if r['kind']=='execution-constructor-enter'))
            elif label=='wrong-constructor-id':next(r for r in changed if r['kind']=='execution-constructed')['constructor_id']=-1
            elif label=='wrong-constructor-argument':next(r for r in changed if r['kind']=='execution-constructor-enter' and r['args'] and 'Mutator' in r['callee'])['args'][0]['object']='same-value-wrong-object'
            elif label=='missing-constructor-throw':changed.remove(next(r for r in changed if r['kind']=='execution-constructor-throw'))
            elif label=='wrong-static-field':next(r for r in changed if r['kind']=='execution-static-read')['field']='wrong-field'
            elif label=='builder-runtime-hash':next(r for r in changed if r.get('scalar_contract'))['scalar_contract']['class_sha256']['java/lang/StringBuilder']='wrong'
            elif label=='wrong-builder-return':next(r for r in changed if r.get('scalar_contract') and r['scalar_contract']['returns_receiver'])['result']['object']='wrong-builder'
            elif label=='missing-render-frame':changed.remove(next(r for r in changed if r['kind']=='enter' and '$View.toString' in r['method']))
            else:next(r for r in changed if r['kind']=='collection-call-enter' and r['callee']=='java/lang/StringBuilder.append(Ljava/lang/Object;)Ljava/lang/StringBuilder;')['args'][0]['object']='wrong-view'
            try:infer_execution(p,changed)
            except ValueError:faults[label]=True
            else:raise AssertionError('Evidence accepted: '+label)
        reports[mode]={'targets':len(checks),'known_exact':sum(c['answer']['known'] for c in checks),'expected_unknown':sum(not c['answer']['known'] for c in checks),'aborted':sum(c['status']=='aborted' for c in cases),'faults':faults,'checks':checks};save(out/'results.json',{'all_passed':True,'modes':reports});print(mode,{k:v for k,v in reports[mode].items() if k!='checks'},flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args();run(a.out.resolve())
