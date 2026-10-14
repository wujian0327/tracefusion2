#!/usr/bin/env python3
"""Bind existing readonly field/version provenance to concrete JVM access sites.

No query labels enter this module. Missing reflective writes stay unknown.
The scalar/stream model remains the existing independently audited model.
"""
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import re
from service_model import derive, disassemble, methods
from infer_service_sources import infer as infer_service


def read_events(path):
    rows=[json.loads(line) for line in path.read_text().splitlines()]
    if [r['seq'] for r in rows]!=list(range(1,len(rows)+1)) or any(r['kind']=='problem' for r in rows):
        raise ValueError('Failed observations')
    return rows


def accessor_model(capture, role, entity):
    owner='works/weave/socks/'+('cart' if role=='carts' else role)+'/entities/'+entity
    file=capture/(owner.replace('/','_')+'.original.class')
    bodies=methods(disassemble(file),owner);getters={};setters={}
    for key,body in bodies.items():
        if len(body)==3 and body[0]['op']=='aload_0' and body[1]['op']=='getfield' and body[2]['op'].endswith('return'):
            match=re.fullmatch(r'Field ([^:]+):(.+)',body[1]['comment'])
            if match:
                field,desc=match.groups()
                getters[key]={'field':owner.replace('/','.')+'.'+field,'primitive':len(desc)==1,'descriptor':desc}
        if len(body)==4 and body[0]['op']=='aload_0' and body[1]['op'] in ('aload_1','iload_1','fload_1','dload_1','lload_1') and body[2]['op']=='putfield' and body[3]['op']=='return':
            match=re.fullmatch(r'Field ([^:]+):(.+)',body[2]['comment'])
            if match:setters[key]={'field':owner.replace('/','.')+'.'+match[1],'descriptor':match[2]}
    return {'owner':owner.replace('/','.'),'getters':getters,'setters':setters,
            'class_sha256':hashlib.sha256(file.read_bytes()).hexdigest()}


def signature(model,key):
    from flowdist_service_static import descriptor_types
    name,desc=key.split('(',1);returns,args=descriptor_types('('+desc)
    return '<'+model['owner']+': '+returns+' '+name+'('+','.join(args)+')>'


def storage_projection(rows, model):
    getters={signature(model,key):value for key,value in model['getters'].items()}
    last={};sinks=defaultdict(list);writes=[]
    for row in rows:
        if row['kind'] not in ('write','read'):continue
        if not row.get('access_method') or not row.get('declared_field'):
            raise ValueError('Missing exact field access metadata')
        location=(row['owner'],row['field'],row['version'])
        if row['kind']=='write':
            if location in last:raise ValueError('Duplicate observed field version')
            last[location]=row;writes.append(row);continue
        site=row['access_method'];accessor=getters.get(site)
        if not accessor:continue
        if row['declared_field']!=accessor['field']:raise ValueError('Field/method binding mismatch')
        source=last.get(location)
        intact=source is not None and source['seq']<row['seq'] and source['observed'].get('value')==row['observed'].get('value')
        intact=intact and (accessor['primitive'] or source['observed']['object']==row['observed']['object'])
        sinks[site].append({'seq':row['seq'],'owner':row['owner'],'field':row['field'],'version':row['version'],
                            'known':intact,'origin':source['access_method'] if intact else None,
                            'origin_field':source['declared_field'] if intact else None,
                            'origin_seq':source['seq'] if intact else None})
    return {'model':model,'sinks':dict(sinks),'observed_write_sites':sorted({w['access_method'] for w in writes}),
            'unresolved_read_reason':'A missing/changed write may be reflective; no equal-value source search is performed.'}


def infer(run):
    result={'storage':{},'derived_total':{},'labels_consumed':False,'source_kind':'actual field instructions, not source fixture labels'}
    for role,entity in (('carts','Item'),('shipping','Shipment')):
        capture=run/'boundary-events'/role;model=accessor_model(capture,role,entity)
        result['storage'][role]=storage_projection(read_events(capture/'events.jsonl'),model)
    capture=run/'tracefusion-events';rows=read_events(capture/'events.jsonl');model,_=derive(capture)
    service=infer_service(capture,model)
    entries={r['frame']:r for r in rows if r['kind']=='enter'};roots={}
    for row in rows:
        if row['kind']=='enter':roots[row['frame']]=roots[row['parent']] if row['parent'] else row['frame']
    snapshots={}
    for row in rows:
        if row['kind']=='rpc-exit':
            for field in row['fields']:
                key=(row['rpc'],field['path']);snapshots[key]=field
    writes={(r['owner'],r['field'],r['version']):r for r in rows if r['kind']=='write'}
    exits={r['frame']:r for r in rows if r['kind']=='exit'}
    for answer in service['answers']:
        for field in answer['fields']:
            if field['path']!='arg#total':continue
            physical=next(f for f in exits[answer['root_frame']]['fields'] if f['path']=='arg#total')
            target=writes.get((physical['owner'],physical['field'],physical['version']))
            if target is None:raise ValueError('Total has no physical write observation')
            origins=set();support=[];known=field['status']=='resolved'
            for coordinate in field['sources'] or []:
                source=snapshots[tuple(coordinate)]
                matches=[r for r in rows if r['kind']=='read' and roots.get(r['frame'])==answer['root_frame']
                         and (r['owner'],r['field'],r['version'])==(source['owner'],source['field'],source['version'])
                         and 'lambda$calculateTotal$' in entries.get(r['frame'],{}).get('method','')]
                if not matches:known=False
                for read in matches:
                    origins.add(read['access_method']);support.append({'read_seq':read['seq'],'write_seq':target['seq'],'source':list(coordinate)})
            result['derived_total'][str(answer['root_frame'])]={'target':target['access_method'],'known':known,
                'origin_read_sites':sorted(origins),'evidence':support}
    return result
