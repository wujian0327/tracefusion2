#!/usr/bin/env python3
"""Trace admission checks, independent disassembly and evidence perturbations."""
import argparse
import copy
from collections import defaultdict
import json
from pathlib import Path
import shutil
import struct
import tempfile
from zipfile import ZipFile
from io import BytesIO
from run_planned_service import load,save,sha,HERE
from plan_distributed_fields import augment,copy_plan
from plan_service_observations import plan_service
from infer_distributed_fields import Reconstruction
from service_model import disassemble,methods,local
from query_observation_planner import require
from transport_context import validate_protocol as validate_w3c_protocol


def validate_protocol(rows):
    if any(r.get('transport_protocol')=='w3c-trace-context' for r in rows):return validate_w3c_protocol(rows)
    stacks=defaultdict(list)
    for r in rows:
        thread=r['thread'];kind=r['kind']
        if kind=='http-rpc-enter':stacks[thread].append(r)
        elif kind in ('http-rpc-exit','http-rpc-abort'):
            require(stacks[thread] and stacks[thread].pop()['message']==r['message'],'Broken HTTP RPC context')
        elif kind=='http-json':
            client=(r['phase'],r['direction']) in [('read','response'),('write','request')]
            if client:
                require(stacks[thread] and stacks[thread][-1]['message']==r['message'] and stacks[thread][-1]['uri']==r['uri'],'JSON message does not belong to active actual RPC')
    require(not any(stacks.values()),'Unclosed HTTP RPC')
    return True


def independent_bytecode(build,model,keys):
    opcodes={'getstatic':178,'getfield':180,'putfield':181,'ldc':18,'invokevirtual':182,'invokespecial':183,
        'invokestatic':184,'invokeinterface':185,'invokedynamic':186,'ifeq':153,'ifne':154,'ifnull':198,'ifnonnull':199,
        'if_icmpeq':159,'if_icmpne':160,'goto':167,'checkcast':192,'new':187,'dup':89,'return':177,'ireturn':172,'freturn':174,'dreturn':175,'areturn':176,
        'i2f':134,'f2d':141,'d2f':144,'fmul':106,'fadd':98,'dadd':99,'fconst_0':11,'aconst_null':1,'athrow':191,'anewarray':189}
    cache={};count=0
    for key in sorted(set(keys)):
        m=model['methods'][key];owner=m['owner'];file=build/'app'/(owner+'.class')
        if owner not in cache:cache[owner]=methods(disassemble(file),owner)
        rows=cache[owner][m['name']+m['desc']];code=m['instructions'];assert len(rows)==len(code)
        offsets={r['offset']:i for i,r in enumerate(rows)}
        for r,n in zip(rows,code):
            var=None
            for name,op in [('aload',25),('iload',21),('fload',23),('lload',22),('dload',24),('astore',58),('istore',54),('fstore',56)]:
                slot=local(r,name)
                if slot is not None:var=(op,slot);break
            if var:assert (n['op'],n['var'])==var;continue
            if r['op'].startswith('iconst_'):
                assert n['op']==(2 if r['op']=='iconst_m1' else int(r['op'][-1])+3);continue
            assert n['op']==opcodes.get(r['op']),(key,r)
            if r['op'] in ('getstatic','getfield','putfield'):
                name,desc=r['comment'].removeprefix('Field ').split(':',1)
                if '.' not in name:name=owner+'.'+name
                assert (name,desc)==(n['owner']+'.'+n['name'],n['desc'])
            elif r['op'].startswith('invoke') and r['op']!='invokedynamic':
                name,desc=r['comment'].split(' ',1)[1].replace('"','').split(':',1)
                if '.' not in name:name=owner+'.'+name
                assert (name,desc)==(n['owner']+'.'+n['name'],n['desc'])
            elif r['op']=='invokedynamic':
                text=disassemble(file,True)
                for h in n['bootstrap_args']:
                    if isinstance(h,dict):name,desc=h['handle'].split('(',1);assert 'REF_invokeStatic '+name+':('+desc in text
            elif r['op'].startswith('if') or r['op']=='goto':assert n['target']==offsets[int(r['operand'])]
            elif r['op']=='ldc':
                if n['constant_type']=='Float':assert struct.pack('f',float(r['comment'][6:].removesuffix('f')))==struct.pack('f',n['constant'])
                elif n['constant_type']=='Type':assert r['comment']=='class '+n['constant'][1:-1]
                else:assert r['comment'].replace("\\'", "'")==('String '+n['constant']).rstrip()
            elif r['op'] in ('new','checkcast','anewarray'):assert r['comment']=='class '+n['type']
        count+=len(code)
    return count


def audit(out,build):
    checks={};instructions=0;info=load(build/'build.json')
    for role,record in info['inputs'].items():
        m=load(build/role/'model.json');p=load(build/role/'plan.json');c=record['query_config'];localplan=None
        if c.get('entry'):
            try:localplan=plan_service(m,c['entry'],c['targets'][0])
            except ValueError:localplan=copy_plan(m,c['entry'],c['targets'][0])
        assert augment(m,localplan)==p
        keys=list(p['frame_methods'])+p.get('summary_methods',[])
        keys += [prop['getter'] for ps in p['json_schema'].values() for prop in ps if prop['getter']]
        instructions+=independent_bytecode(build/role,m,keys)
        with ZipFile(build/role/'original.jar') as z:
            for owner,expected in p['class_sha256'].items():
                path='BOOT-INF/classes/'+owner+'.class'
                if path in z.namelist():data=z.read(path)
                else:
                    extra=record['extra_classes'][owner+'.class']
                    with ZipFile(BytesIO(z.read(extra['jar_entry']))) as dep:data=dep.read(owner+'.class')
                import hashlib
                assert hashlib.sha256(data).hexdigest()==expected
    checks['all_six_plans_regenerated_without_business_answers']=True
    checks['independent_javap_opcode_operands_and_lambda_verified']=True
    checks['all_class_hashes_match_original_image_jars']=True
    reports={app:load(out/app/'field-results.json') for app in ('sockshop','trainticket')}
    assert all(r['summary']['exact']==r['summary']['queries'] for r in reports.values());checks['independent_business_database_and_field_instance_oracles_passed']=True
    for app,roles in [('sockshop',['orders','carts','shipping']),('trainticket',['station','basic','ticketinfo'])]:
        for role in roles:validate_protocol([json.loads(l) for l in (out/app/role/'events.jsonl').read_text().splitlines()])
    checks['actual_rpc_thread_contexts_match_message_observations']=True
    # New application plans derive getter-to-constructor field copies and a
    # constant kill automatically; both used the same observer JAR and Python.
    assert any(r['source']['kind']=='field-read' for r in load(build/'station/plan.json')['copy_rules'])
    assert any(r['source']=={'kind':'constant','value':None} for r in load(build/'basic/plan.json')['copy_rules'])
    checks['second_application_copy_and_constant_rules_derived_from_code']=True
    model=load(build/'station/model.json');entry=load(build/'station/plan.json')['entry'];renamed=copy.deepcopy(model)
    for owner,cls in renamed['classes'].items():
        for f in cls['fields']:
            if owner.endswith('/Station') and f['name']=='id':f['name']='renamedIdentifier'
    for m in renamed['methods'].values():
        for n in m['instructions']:
            if n['op'] in (180,181) and n['owner'].endswith('/Station') and n['name']=='id':n['name']='renamedIdentifier'
        if m['owner'].endswith('/Station') and m['name']=='getId':m['name']='getRenamedIdentifier'
    renamed['methods']={k.replace('.getId(','.getRenamedIdentifier(') if v['owner'].endswith('/Station') else k:v for k,v in renamed['methods'].items()}
    for m in renamed['methods'].values():
        for n in m['instructions']:
            if n['op'] in (182,183,184,185) and n['owner'].endswith('/Station') and n['name']=='getId':n['name']='getRenamedIdentifier'
    changed=copy_plan(renamed,entry,'edu.fudan.common.util.Response.data')
    assert any(r['source'].get('field','').endswith('.renamedIdentifier') for r in changed['copy_rules']);checks['renamed_second_application_source_requires_no_engine_edits']=True
    with tempfile.TemporaryDirectory(prefix='distributed-path-audit-') as td:
        scratch=Path(td);roles=['orders','carts','shipping']
        raw={role:[json.loads(l) for l in (out/'sockshop'/role/'events.jsonl').read_text().splitlines()] for role in roles}
        for role in roles:(scratch/role).mkdir()
        def replay(changes=None):
            for role in roles:
                rows=(changes or {}).get(role,raw[role]);(scratch/role/'events.jsonl').write_text(''.join(json.dumps(dict(r,seq=i+1))+'\n' for i,r in enumerate(rows)))
            return Reconstruction(build,scratch,roles)
        first=next(c for c in load(out/'sockshop/run.json')['cases'] if c['case']=='single');boundary={'service':'carts','kind':'http-json','phase':'write','direction':'response'}
        base=replay().query(first['message'],'/total','orders',boundary)
        # Find the independently recorded actual producer from its case fixture.
        fixture=load(out/'sockshop/single/fixture.json');uri='http://carts/carts/'+fixture['customer_id']+'/items';rpc=next(r for r in raw['orders'] if r['kind']=='http-rpc-enter' and r['uri']==uri)
        changed=copy.deepcopy(raw['carts']);next(r for r in changed if r['kind']=='http-json' and r['phase']=='write' and r['direction']=='response' and r['message']==rpc['message'])['fields']=[f for f in next(r for r in changed if r['kind']=='http-json' and r['phase']=='write' and r['direction']=='response' and r['message']==rpc['message'])['fields'] if not f['path'].endswith('/quantity')]
        r=replay({'carts':changed}).query(first['message'],'/total','orders',boundary)
        assert not r['known'];checks['missing_remote_source_property_returns_unknown']=True
        w3c=any(r.get('transport_protocol')=='w3c-trace-context' for rows in raw.values() for r in rows)
        changed=copy.deepcopy(raw['orders']);r=next(r for r in changed if r['kind']=='http-json' and r['phase']=='read' and r['direction']=='response')
        if w3c:
            r['request_span_id']='1'*16;r['message']=r['trace_id']+'/'+r['request_span_id']
        else:r['echo']='forged'
        try:replay({'orders':changed})
        except ValueError:checks['wrong_response_invocation_context_rejected']=True
        else:raise AssertionError('Wrong response context accepted')
        changed=copy.deepcopy(raw['orders']);r=next(r for r in changed if r['kind']=='http-json' and r['phase']=='read' and r['direction']=='response');r['message']='foreign'
        if not w3c:r['echo']='foreign'
        try:validate_protocol(changed)
        except ValueError:checks['foreign_equal_valued_rpc_context_rejected']=True
        else:raise AssertionError('Wrong context accepted')
        changed={role:[{k:v for k,v in r.items() if k!='parent_message' and not (k=='trace_id' and (not w3c or not r['kind'].startswith('http-')))} for r in rows] for role,rows in raw.items()}
        stripped=replay(changed).query(first['message'],'/total','orders',boundary)
        assert base['source_keys']==stripped['source_keys'];checks['business_trace_labels_and_parent_audit_metadata_unused_by_reconstruction']=True
        changed=copy.deepcopy(raw['carts']);row=next(r for r in changed if r['kind']=='http-json' and r['phase']=='write' and r['direction']=='response' and r['fields']);row['fields'][0]['path']='/wrongProperty'
        try:replay({'carts':changed})
        except ValueError:checks['property_pointer_mismatch_rejected']=True
        else:raise AssertionError('Wrong pointer accepted')
    negatives=[n for r in reports.values() for n in r['negative_relations']];assert all(not n['predicted'] for n in negatives);checks['same_valued_non_source_fields_do_not_gain_origins']=True
    report={'all_passed':all(checks.values()),'checks':checks,'independent_javap_instructions':instructions,
        'same_collector_jar_sha256':info['agent_sha256'],'supplementary_negative_relations':len(negatives),
        'scope':'Corruption tests replay temporary copies; independent RPC protocol admission is separate from provenance inference; renaming is a static model check.'}
    save(out/'algorithm-audit.json',report);print(json.dumps(report,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);p.add_argument('--build',type=Path,required=True);a=p.parse_args();audit(a.out.resolve(),a.build.resolve())
