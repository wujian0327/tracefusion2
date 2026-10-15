#!/usr/bin/env python3
"""Independent disassembly checks and adversarial evidence controls for real-service plans."""
import argparse
import copy
import json
from pathlib import Path
import struct
import tempfile
from plan_service_observations import plan_service
from infer_planned_service import infer_service
from service_model import disassemble,methods,local
from run_planned_service import load,save,sha


def verify_bytecode(build,model,keys):
    ops={'getstatic':178,'getfield':180,'putfield':181,'ldc':18,'invokevirtual':182,'invokespecial':183,
         'invokestatic':184,'invokeinterface':185,'invokedynamic':186,'ifeq':153,'ifne':154,'ifnull':198,'ifnonnull':199,
         'goto':167,'checkcast':192,'new':187,'dup':89,'return':177,'ireturn':172,'freturn':174,'dreturn':175,
         'areturn':176,'i2f':134,'f2d':141,'d2f':144,'fmul':106,'fadd':98,'dadd':99,'fconst_0':11,
         'aconst_null':1,'athrow':191}
    decoded={};count=0
    for key in keys:
        m=model['methods'][key];owner=m['owner'];file=build/'app'/(owner+'.class')
        if owner not in decoded:decoded[owner]=methods(disassemble(file),owner)
        rows=decoded[owner][m['name']+m['desc']];code=m['instructions'];assert len(rows)==len(code)
        offsets={r['offset']:i for i,r in enumerate(rows)}
        for r,n in zip(rows,code):
            var=None
            for label,op in [('aload',25),('iload',21),('fload',23),('dload',24),('lload',22),('astore',58),('istore',54),('fstore',56)]:
                slot=local(r,label)
                if slot is not None:var=(op,slot);break
            if var is not None:assert (n['op'],n['var'])==var;continue
            assert n['op']==ops.get(r['op']),(key,r)
            if r['op'] in ('getstatic','getfield','putfield'):
                name,desc=r['comment'].removeprefix('Field ').split(':',1)
                if '.' not in name:name=owner+'.'+name
                assert (name,desc)==(n['owner']+'.'+n['name'],n['desc'])
            elif r['op'].startswith('invoke') and r['op']!='invokedynamic':
                name,desc=r['comment'].split(' ',1)[1].replace('"','').split(':',1)
                if '.' not in name:name=owner+'.'+name
                assert (name,desc)==(n['owner']+'.'+n['name'],n['desc'])
            elif r['op']=='invokedynamic':
                verbose=disassemble(file,True)
                for h in n['bootstrap_args']:
                    if isinstance(h,dict):
                        name,desc=h['handle'].split('(',1);assert 'REF_invokeStatic '+name+':('+desc in verbose
                assert 'java/lang/invoke/LambdaMetafactory.metafactory' in verbose
            elif r['op'] in ('ifnull','ifnonnull','ifeq','ifne','goto'):assert n['target']==offsets[int(r['operand'])]
            elif r['op']=='ldc':
                if n['constant_type']=='Float':assert struct.pack('f',float(r['comment'][6:].removesuffix('f')))==struct.pack('f',n['constant'])
                else:assert r['comment'].replace("\\'", "'")==('String '+n['constant']).rstrip()
            elif r['op'] in ('new','checkcast'):assert r['comment']=='class '+n['type']
        count+=len(code)
    return count


def audit(build,out):
    model=load(build/'model.json');p=load(build/'plan.json');checks={}
    assert plan_service(model,p['entry'],p['target'])==p
    checks['frozen_plan_regenerates_from_bytecode']=True
    keys=sorted(set(p['frame_methods']+p['summary_methods']))
    n=verify_bytecode(build,model,keys);checks['independent_javap_instructions_and_operands']=True
    renamed=copy.deepcopy(model);mapping={'quantity':'renamedCount','unitPrice':'renamedRate','total':'renamedAmount'}
    for cls in renamed['classes'].values():
        for f in cls['fields']:f['name']=mapping.get(f['name'],f['name'])
    for m in renamed['methods'].values():
        for i in m['instructions']:
            if i['op'] in (178,179,180,181):i['name']=mapping.get(i['name'],i['name'])
    changed=plan_service(renamed,p['entry'],p['target'].rsplit('.',1)[0]+'.renamedAmount')
    assert {f.rsplit('.',1)[1] for f in changed['mapper_fields']}=={'renamedCount','renamedRate'}
    checks['renaming_source_and_target_fields_requires_no_planner_changes']=True
    renamed=copy.deepcopy(model)
    def rename(s):return s.replace('calculateTotal','recomputedCharge')
    renamed['methods']={rename(k):dict(m,name=rename(m['name'])) for k,m in renamed['methods'].items()}
    for m in renamed['methods'].values():
        for i in m['instructions']:
            if i['op'] in (182,183,184,185):i['name']=rename(i['name'])
            if i['op']==186:
                for h in i['bootstrap_args']:
                    if isinstance(h,dict):h['handle']=rename(h['handle'])
    changed=plan_service(renamed,p['entry'],p['target']);assert 'recomputedCharge' in changed['producer_method']
    assert 'recomputedCharge' in changed['reduction']['mapper_method']
    checks['renaming_scalar_and_lambda_methods_requires_no_configuration_changes']=True
    mutated=copy.deepcopy(model);mutated['methods'][p['producer_method']]['instructions'][0]={'index':0,'op':167,'target':0}
    try:plan_service(mutated,p['entry'],p['target'])
    except ValueError:checks['unsupported_loop_rejected']=True
    else:raise AssertionError('Loop accepted')
    mutated=copy.deepcopy(model)
    next(i for i in mutated['methods'][p['reduction']['mapper_method']]['instructions'] if i['op']==182)['owner']='opaque/External'
    try:plan_service(mutated,p['entry'],p['target'])
    except ValueError:checks['unmodeled_scalar_call_rejected']=True
    else:raise AssertionError('Opaque call accepted')
    rows=[json.loads(l) for l in (out/'selective/capture/events.jsonl').read_text().splitlines()]
    baseline=infer_service(p,out/'selective/capture/events.jsonl')
    with tempfile.TemporaryDirectory(prefix='query-service-audit-') as td:
        capture=Path(td)/'events.jsonl'
        def replay(rs):capture.write_text(''.join(json.dumps(dict(r,seq=i+1))+'\n' for i,r in enumerate(rs)));return infer_service(p,capture)
        def rejected(name,rs):
            try:replay(rs)
            except ValueError:checks[name]=True
            else:raise AssertionError('Corruption accepted: '+name)
        damaged=copy.deepcopy(rows);next(r for r in damaged if r['kind']=='enter' and r['method']==p['writer_method'])['callsite']='wrong';rejected('writer_def_use_callsite_mismatch_rejected',damaged)
        damaged=copy.deepcopy(rows);next(r for r in damaged if r['kind']=='write')['version']+=1;rejected('wrong_target_version_rejected',damaged)
        damaged=copy.deepcopy(rows);next(r for r in damaged if r['kind']=='enter' and r['method']==p['reduction']['mapper_method'])['args'][0]['object']='foreign';rejected('equal_valued_foreign_member_identity_rejected',damaged)
        damaged=copy.deepcopy(rows);first=next(r for r in damaged if r['kind']=='enter' and r['method']==p['producer_method']);first['inputs'][0]['fields'].pop();rejected('missing_source_field_snapshot_rejected',damaged)
        damaged=copy.deepcopy(rows);next(r for r in damaged if r['kind']=='sum-enter')['parallel']=True;rejected('unmodeled_parallel_stream_rejected',damaged)
        damaged=copy.deepcopy(rows);next(r for r in damaged if r['kind']=='exit' and 'fields' in r)['result']['object']='replacement';rejected('repository_replacement_object_rejected',damaged)
        stripped=[{k:v for k,v in r.items() if k!='trace_id'} for r in rows];result=replay(stripped)
        canon=lambda answers:[{k:v for k,v in a.items() if k!='trace_id'} for a in answers]
        assert canon(result['answers'])==canon(baseline['answers']);checks['trace_labels_unused_for_origin_answers']=True
    comparisons=load(out/'comparison.json')
    assert all(r['exact']==r['queries'] and r['fp']==r['fn']==0 for r in comparisons['results'].values())
    checks['full_and_selected_pass_independent_business_and_field_oracles']=True
    secondary=load(out/'freeze.json').get('secondary_build')
    if secondary:
        b2=Path(secondary);m2=load(b2/'model.json');p2=load(b2/'plan.json')
        assert plan_service(m2,p2['entry'],p2['target'])==p2
        n+=verify_bytecode(b2,m2,p2['frame_methods'])
        checks['second_real_service_plan_and_javap_verified']=True
        changed=plan_service(m2,p2['entry'],p2['target'].rsplit('.',1)[0]+'.id')
        assert changed['snapshot_fields']==[p2['target'].rsplit('.',1)[0]+'.id']
        assert changed['snapshot_fields']!=p2['snapshot_fields'];checks['changing_only_shipping_target_regenerates_field_plan']=True
        assert load(out/'shipping-comparison.json')['same_collector_bytecode'];checks['same_collector_bytecode_for_both_targets']=True
        original=infer_service(p2,out/'selective/shipping-capture/events.jsonl')
        with tempfile.TemporaryDirectory(prefix='query-shipping-audit-') as td:
            path=Path(td)/'events.jsonl';rows=[json.loads(l) for l in (out/'selective/shipping-capture/events.jsonl').read_text().splitlines()]
            damaged=copy.deepcopy(rows);next(r for r in damaged if r['kind']=='exit')['fields'][0]['version']+=1
            path.write_text(''.join(json.dumps(r)+'\n' for r in damaged))
            try:infer_service(p2,path)
            except ValueError:checks['shipping_overwritten_field_version_rejected']=True
            else:raise AssertionError('Wrong field version accepted')
            damaged=copy.deepcopy(rows);next(r for r in damaged if r['kind']=='exit')['result']['object']='foreign'
            path.write_text(''.join(json.dumps(r)+'\n' for r in damaged))
            try:infer_service(p2,path)
            except ValueError:checks['shipping_equal_valued_foreign_target_rejected']=True
            else:raise AssertionError('Foreign target accepted')
    report={'checks':checks,'all_passed':all(checks.values()),'javap_instructions_checked':n,
            'scope':'Bytecode model renames are static planner checks; evidence controls replay temporary copies. Main captures use original unmodified classes.'}
    save(out/'algorithm-audit.json',report);print(json.dumps(report,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--build',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();audit(a.build.resolve(),a.out.resolve())
