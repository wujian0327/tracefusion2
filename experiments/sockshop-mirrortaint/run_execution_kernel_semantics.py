#!/usr/bin/env python3
"""Real JVM loop/container semantics, independent position oracle and fault checks."""
import argparse
import copy
import json
from pathlib import Path
from zipfile import ZipFile
from build_distributed_plans import build
from plan_response_binding import plan_response
from run_planned_service import HERE,load,save
from run_query_planner import command
from experiment_environment import java8_target
from infer_execution_kernel import infer_execution


def run(out):
    out.mkdir(parents=True,exist_ok=False);classes=out/'classes';classes.mkdir();_,target=java8_target()
    command(['javac',*target,'-d',str(classes),str(HERE/'ExecutionKernelFixture.java')],out/'fixture-compile.log')
    jar=out/'fixture.jar'
    with ZipFile(jar,'w') as z:
        for f in classes.glob('*.class'):z.write(f,'BOOT-INF/classes/'+f.name)
    entry='ExecutionKernelFixture.filter(Ljava/util/List;Ljava/lang/String;)LExecutionKernelFixture$Output;'
    build(out/'build',{'fixture':{'jar':str(jar),'entry':entry,'targets':['ExecutionKernelFixture$Output.data'],'response_path':'/data/*','execution_kernel':True}})
    model=load(out/'build/fixture/model.json');base=load(out/'build/fixture/plan.json');reports={};cached={}
    jobs=[('filter',entry,[],[2,0,0,2,2,1],False),
          ('counted','ExecutionKernelFixture.counted(Ljava/util/List;)LExecutionKernelFixture$Output;',['counted'],[3,0,2],False),
          ('overwrite','ExecutionKernelFixture.overwrite(LExecutionKernelFixture$Item;LExecutionKernelFixture$Item;)LExecutionKernelFixture$Output;',['overwrite'],[1],False),
          ('unrelated','ExecutionKernelFixture.unrelated(LExecutionKernelFixture$Item;LExecutionKernelFixture$Item;)LExecutionKernelFixture$Output;',['unrelated'],[1],False),
          ('constant-overwrite','ExecutionKernelFixture.constantOverwrite(LExecutionKernelFixture$Item;)LExecutionKernelFixture$Output;',['constant-overwrite'],[1],False),
          ('opaque','ExecutionKernelFixture.opaqueResult(Ljava/util/List;)LExecutionKernelFixture$Output;',['opaque'],[1],True)]
    for name,key,arguments,lengths,unknown in jobs:
        plan=plan_response(model,key,'ExecutionKernelFixture$Output.data','/data/*',execution_kernel=True);p=out/(name+'.plan.json');save(p,plan)
        for mode in ('full','selective'):
            log=out/(name+'-'+mode+'.events.jsonl')
            command(['java','-javaagent:'+str(out/'build/distributed-observer.jar'),'-Dservice.plan='+str(p),'-Dservice.mode='+mode,'-Dservice.events='+str(log),'-cp',str(classes),'ExecutionKernelFixture',*arguments],out/(name+'-'+mode+'.stdout.log'))
            rows=[json.loads(s) for s in log.read_text().splitlines()];assert [r['seq'] for r in rows]==list(range(1,len(rows)+1));assert sum(r['kind']=='metrics' for r in rows)==1;assert not any(r['kind']=='problem' for r in rows)
            result=infer_execution(plan,rows);save(out/(name+'-'+mode+'.answers.json'),result)
            normal=[r for r in result['roots'] if r['completion']=='normal'];assert [r['answers'] for r in normal]==lengths
            assert all(a['known']!=unknown for a in result['answers'])
            source={(r['seq'],i):f for r in rows if r['kind'] in ('binding-input','binding-source') for i,f in enumerate(r['fields'])}
            # Literal oracle: original input positions selected by fixture source,
            # independent of reconstructed state and branches.
            wanted={'filter':[['/0/label','/2/label'],[],[],['/0/label','/1/label'],['/0/label','/2/label'],['/1/label']],
                    'counted':[['/0/label','/1/label','/2/label'],[],['/0/label','/1/label']]}
            if not unknown:
                for root_index,root in enumerate(normal):
                    answers=[a for a in result['answers'] if a['root_frame']==root['frame']]
                    if name in wanted:
                        for a,path in zip(answers,wanted[name][root_index]):
                            assert len(a['origins'])==1
                            assert source[tuple(a['origins'][0])]['path']==path
                            assert source[tuple(a['origins'][0])]['field']=='ExecutionKernelFixture$Item.label'
                    elif name=='constant-overwrite':assert all(not a['origins'] for a in answers)
                    else:
                        expected=next(r for r in rows if r['kind']=='binding-input' and r['frame']==root['frame'] and r['argument']==1)
                        label=next(i for i,f in enumerate(expected['fields']) if f['field']=='ExecutionKernelFixture$Item.label')
                        assert all(a['origins']==[[expected['seq'],label]] for a in answers)
            reports[name+'-'+mode]={'known':sum(a['known'] for a in result['answers']),'unknown':sum(not a['known'] for a in result['answers']),'normal_roots':len(normal),'aborted_roots':sum(r['completion']=='aborted' for r in result['roots']),'independent_position_oracle':not unknown}
            if name=='filter':cached[mode]=(plan,rows)
    # Evidence alterations must fail replay rather than cause a wrong known answer.
    faults={}
    for mode,(plan,rows) in cached.items():
        variants={}
        x=copy.deepcopy(rows);victim=next(r for r in x if r['kind']=='collection-call-exit' and r.get('result_type')=='java.util.ArrayList$Itr');victim['result_type']='custom.Iterator';variants['iterator-type']=x
        x=copy.deepcopy(rows);victim=next(r for r in x if r['kind']=='collection-call-enter' and r['callee'].endswith('.next()Ljava/lang/Object;'));victim['receiver']['object']='wrong-same-value-object';variants['iterator-owner']=x
        x=copy.deepcopy(rows);victim=next(r for r in x if r['kind']=='collection-call-exit' and r.get('collection_after') and r['collection_after'][0].get('value')=='same');victim['collection_after'][0]['value']='changed';variants['list-post-state']=x
        x=copy.deepcopy(rows);x.remove(next(r for r in x if r['kind']=='collection-call-exit'));variants['missing-call-completion']=x
        x=copy.deepcopy(rows);victim=next(r for r in x if r['kind']=='branch');victim['taken']=not victim['taken'];variants['branch']=x
        x=copy.deepcopy(rows);victim=next(r for r in x if r['kind']=='execution-runtime');victim['class_sha256']['java/util/ArrayList$Itr']='0'*64;variants['runtime-pin']=x
        for name,altered in variants.items():
            try:infer_execution(plan,altered)
            except (ValueError,IndexError):faults[mode+'-'+name]=True
            else:raise AssertionError('Necessary fault accepted: '+mode+'-'+name)
        for name in ('missing-source','ambiguous-source'):
            altered=copy.deepcopy(rows)
            for row in altered:
                if row['kind']=='binding-input':
                    fields=[f for f in row['fields'] if f['field']=='ExecutionKernelFixture$Item.label']
                    if name=='missing-source':row['fields']=[f for f in row['fields'] if f not in fields]
                    else:row['fields']+=copy.deepcopy(fields)
            answer=infer_execution(plan,altered)
            assert len(answer['answers'])==7 and all(not a['known'] for a in answer['answers'])
            faults[mode+'-'+name]=True
    save(out/'results.json',{'all_passed':True,'reports':reports,'faults':faults,'scope':'Controlled JVM semantics; not original application coverage or performance'})
    print(json.dumps(reports,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',required=True,type=Path);a=p.parse_args();run(a.out.resolve())
