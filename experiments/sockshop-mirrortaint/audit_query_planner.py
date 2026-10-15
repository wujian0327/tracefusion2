#!/usr/bin/env python3
"""Independent certificate checks, evidence perturbations and native collision witness."""
import argparse
import copy
import itertools
import json
from pathlib import Path
import re
import struct
import tempfile

from query_observation_planner import plan,verify,projected_trace
from infer_query_observations import infer
from run_query_planner import load,save,sha,JARS,command
from service_model import disassemble,methods,local


def verify_bytecode(build,model,keys):
    decoded={};total=0
    ops={'getstatic':178,'getfield':180,'putfield':181,'ldc':18,'invokevirtual':182,'invokespecial':183,
         'invokestatic':184,'invokeinterface':185,'ifeq':153,'ifne':154,'goto':167,'checkcast':192,
         'new':187,'dup':89,'return':177,'ireturn':172,'freturn':174,'areturn':176,'i2f':134,
         'fmul':106,'fadd':98,'iadd':96,'fconst_0':11}
    for key in keys:
        method=model['methods'][key];owner=method['owner']
        if owner not in decoded:decoded[owner]=methods(disassemble(build/'app'/(owner+'.class')),owner)
        actual=decoded[owner][method['name']+method['desc']];code=method['instructions']
        assert len(actual)==len(code),'Model instruction count differs from javap'
        offsets={row['offset']:i for i,row in enumerate(actual)}
        for n,row in zip(code,actual):
            variable=None
            for label,op in [('aload',25),('iload',21),('fload',23),('astore',58),('istore',54),('fstore',56)]:
                slot=local(row,label)
                if slot is not None:variable=(op,slot);break
            if variable is not None:
                assert (n['op'],n['var'])==variable;continue
            assert n['op']==ops.get(row['op']),row
            if row['op'] in ('getstatic','getfield','putfield'):
                name,desc=row['comment'].removeprefix('Field ').split(':',1)
                if '.' not in name:name=owner+'.'+name
                assert name==n['owner']+'.'+n['name'] and desc==n['desc']
            elif row['op'].startswith('invoke'):
                name,desc=row['comment'].split(' ',1)[1].replace('"','').split(':',1)
                if '.' not in name:name=owner+'.'+name
                assert name==n['owner']+'.'+n['name'] and desc==n['desc']
            elif row['op'] in ('ifeq','ifne','goto'):assert n['target']==offsets[int(row['operand'])]
            elif row['op']=='ldc':
                if row['comment'].startswith('float '):assert struct.pack('f',float(row['comment'][6:].removesuffix('f')))==struct.pack('f',n['constant'])
                else:assert row['comment']=='String '+n['constant']
            elif row['op'] in ('new','checkcast'):assert row['comment']=='class '+n['type']
        total+=len(code)
    return total


def audit(build,out):
    model=load(build/'model.json');original=load(build/'total.plan.json');checks=[]
    instructions=verify_bytecode(build,model,original['reachable_methods'])
    checks.append({'test':'model-independently-matches-javap','passed':True,'instructions':instructions})
    for name in ('total','name','payload','total-name','all'):
        p=load(build/(name+'.plan.json'));verify(p,model);selected=set(p['selected_sites'])
        for left,right in itertools.combinations(p['path_candidates'],2):
            if projected_trace({'trace':left['trace']},selected)==projected_trace({'trace':right['trace']},selected):
                assert left['answer']==right['answer']
    checks.append({'test':'all-evidence-equivalence-classes-have-one-answer','passed':True})
    assert len(original['selected_branch_sites'])==1
    assert not load(build/'name.plan.json')['selected_branch_sites']
    checks.append({'test':'changing-only-target-changes-plan','passed':True})
    altered=copy.deepcopy(original);altered['selected_branch_sites']=[]
    try:verify(altered,model)
    except ValueError:checks.append({'test':'tampered-certificate-rejected','passed':True})
    else:raise AssertionError('Tampered certificate accepted')
    renamed=copy.deepcopy(model)
    mapping={'quantity':'countRenamed','unitPrice':'priceRenamed','total':'sumRenamed'}
    for cls in renamed['classes'].values():
        for field in cls['fields']:field['name']=mapping.get(field['name'],field['name'])
    for method in renamed['methods'].values():
        for n in method['instructions']:
            if n['op'] in (178,179,180,181):n['name']=mapping.get(n['name'],n['name'])
    changed=plan(renamed,original['entry'],['Orders.sumRenamed'])
    assert any('countRenamed' in f for f in changed['snapshot_fields']) and any('priceRenamed' in f for f in changed['snapshot_fields'])
    assert not any('quantity' in f or 'unitPrice' in f for f in changed['snapshot_fields'])
    checks.append({'test':'source-and-target-field-renaming-needs-no-algorithm-change','passed':True})
    for query in load(build/'name.plan.json')['path_candidates']:
        assert query['answer'][0]['sources']==[['arg:0','QueryPlannerFixture$Source.name']]
        assert query['answer'][0]['version_offset']==2
    checks.append({'test':'last-write-kills-prior-field-origin','passed':True})
    loop=copy.deepcopy(model);loop['methods'][original['entry']]['instructions'][0]={'index':0,'op':167,'target':0}
    try:plan(loop,original['entry'],['Orders.total'])
    except ValueError as error:
        assert 'Loop' in str(error);checks.append({'test':'unsupported-loop-rejected','passed':True})
    else:raise AssertionError('Loop accepted')
    effect=copy.deepcopy(model)
    next(n for n in effect['methods'][original['entry']]['instructions'] if n['op']==184)['owner']='unmodelled/External'
    try:plan(effect,original['entry'],['Orders.total'])
    except ValueError as error:
        assert 'Missing external effect' in str(error);checks.append({'test':'unmodelled-external-effect-rejected','passed':True})
    else:raise AssertionError('Unknown effect accepted')
    with tempfile.TemporaryDirectory(prefix='tf2-query-audit-') as temporary:
        capture=Path(temporary)/'events.jsonl';rows=[json.loads(l) for l in (out/'total-selective/events.jsonl').read_text().splitlines()]
        index=next(i for i,r in enumerate(rows) if r['kind']=='branch');rows.pop(index)
        capture.write_text(''.join(json.dumps(dict(r,seq=i+1))+'\n' for i,r in enumerate(rows)))
        try:infer(original,capture)
        except ValueError as error:
            assert 'No modeled execution' in str(error);checks.append({'test':'missing-selected-observation-rejected','passed':True})
        else:raise AssertionError('Missing evidence accepted')
        rows=[json.loads(l) for l in (out/'total-selective/events.jsonl').read_text().splitlines()]
        next(r for r in rows if r['kind']=='enter')['request_id']='different-display-label'
        capture.write_text(''.join(json.dumps(r)+'\n' for r in rows))
        before=infer(original,out/'total-selective/events.jsonl');after=infer(original,capture)
        assert [a['sources'] for a in before['answers']]==[a['sources'] for a in after['answers']]
        checks.append({'test':'request-label-does-not-select-origins','passed':True})
        rows=[json.loads(l) for l in (out/'total-selective/events.jsonl').read_text().splitlines()]
        field=next(r for r in rows if r['kind']=='exit')['arguments'][2]['fields'][0];field['version']+=1
        capture.write_text(''.join(json.dumps(r)+'\n' for r in rows))
        try:infer(original,capture)
        except ValueError:checks.append({'test':'target-version-corruption-rejected','passed':True})
        else:raise AssertionError('Corrupted target version accepted')
    full=infer(original,out/'total-full/events.jsonl');selected=infer(original,out/'total-selective/events.jsonl');fixed=infer(original,out/'total-fixed/events.jsonl')
    assert {a['request_id'] for a in fixed['answers'] if a['known']}=={'alias-left','alias-right'}
    checks.append({'test':'equal-value-distinct-objects-stay-ambiguous-without-required-branch','passed':True})
    for result in (full,selected):
        a=next(a for a in result['answers'] if a['request_id']=='repeat-left')
        b=next(a for a in result['answers'] if a['request_id']=='repeat-right')
        assert a['owner']==b['owner'] and a['version']==2 and b['version']==4
        assert all(v[3]==1 for v in a['sources']) and all(v[3]==2 for v in b['sources'])
    checks.append({'test':'repeated-objects-preserve-source-and-target-versions','passed':True})
    value={'passed':True,'checks':checks,'raw_captures_modified':False};save(out/'algorithm-audit.json',value);return value


def semantic_evidence(path):
    rows=[json.loads(l) for l in path.read_text().splitlines()]
    enter=next(r for r in rows if r['kind']=='enter');aliases={a['object']:'arg:'+str(a['argument']) for a in enter['arguments']}
    result=[]
    for row in rows:
        kind=row['kind']
        if kind in ('enter','exit'):
            result.append({'kind':kind,'arguments':[{'argument':a['argument'],'owner':aliases[a['object']],
                'fields':[{'field':f['field'],'version':f['version'],'value':f['observed']['value']} for f in a.get('fields',[])]} for a in row['arguments']]})
        elif kind in ('read','write'):
            result.append({'kind':kind,'site':row['site'],'owner':aliases[row['owner']],'field':row['field'],
                           'version':row['version'],'value':row['observed']['value']})
        elif kind=='branch':result.append({'kind':kind,'site':row['site'],'taken':row['taken']})
    return result


def collision(build,out):
    out.mkdir(parents=True,exist_ok=False);p=load(build/'total.plan.json');results={}
    for pick in (False,True):
        label='right' if not pick else 'left';case=dict(id='collision',aq=4,bq=4,price=2.5,an='SAME',bn='SAME',ap='SAME',bp='SAME',pick=pick,noise=False,alias=False)
        cases=out/(label+'.cases.json');save(cases,[case]);results[label]={}
        for mode in ('fixed','selective'):
            run=out/(label+'-'+mode);run.mkdir()
            cmd=['java','-Xms32m','-Xmx256m','-javaagent:'+str(build/'query-observer.jar'),'-Dquery.plan='+str(build/'total.plan.json'),
                 '-Dquery.mode='+mode,'-Dquery.events='+str(run/'events.jsonl'),'-cp',str(build/'app')+':'+':'.join(map(str,JARS)),
                 'QueryPlannerFixture',str(cases),str(run/'business.json')]
            command(cmd,run/'console.log');r=infer(p,run/'events.jsonl');save(run/'predictions.json',r);results[label][mode]=r
    left,right=semantic_evidence(out/'left-fixed/events.jsonl'),semantic_evidence(out/'right-fixed/events.jsonl')
    assert left==right
    assert load(out/'left-fixed/business.json')==load(out/'right-fixed/business.json')
    assert all(not results[label]['fixed']['answers'][0]['known'] for label in results)
    normalized={}
    for label in results:
        rows=[json.loads(l) for l in (out/(label+'-selective/events.jsonl')).read_text().splitlines()];entry=next(r for r in rows if r['kind']=='enter')
        owner_to_arg={v['object']:v['argument'] for v in entry['arguments']}
        answer=results[label]['selective']['answers'][0];assert answer['known']
        normalized[label]=sorted((owner_to_arg[o],field) for _,o,field,_ in answer['sources'])
    assert normalized['left']!=normalized['right']
    result={'passed':True,'fixed_semantic_evidence_equal':True,'business_outputs_equal':True,
            'selected_origins_differ_and_are_known':True,'origins':normalized,
            'normalization':'Alpha-rename root object identities by argument position; omit JVM thread/frame labels and boxed value object identities, which do not select field origins. Retain field values, versions, target writes and sites.',
            'same_evidence':left,'scope':'Concrete counterexample for removing the selected branch under this bounded field-origin evidence model.'}
    save(out/'collision.json',result);return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--build',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--collision',action='store_true');a=p.parse_args()
    r=collision(a.build.resolve(),a.out.resolve()) if a.collision else audit(a.build.resolve(),a.out.resolve())
    print(json.dumps(r if not a.collision else {k:v for k,v in r.items() if k!='same_evidence'},indent=2))
