#!/usr/bin/env python3
"""Carts response field reads -> matched Orders response DTO -> derived total.

Message UUID and list position select edges; scalar values only validate them.
No request fixture, truth label, customer identity or B3 trace joins are used.
"""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import re
from infer_field_access_sites import accessor_model, signature, read_events
from infer_service_sources import infer as service_infer
from service_model import derive, disassemble


PROPERTIES=('itemId','quantity','unitPrice')


def bridge(server, client, model):
    getters={signature(model,key):value for key,value in model['getters'].items() if key.startswith('get')}
    candidates=defaultdict(lambda:defaultdict(dict));orders=defaultdict(lambda:defaultdict(list))
    for row in server:
        if row['kind']!='read' or not row.get('message_id'):continue
        getter=getters.get(row.get('access_method'))
        if not getter:continue
        field=row['field'];message=row['message_id'];owner=row['owner']
        if field not in PROPERTIES:continue
        if getter['field']!=row['declared_field']:raise ValueError('Getter/field declaration mismatch')
        values=candidates[message][owner].setdefault(field,[]);values.append(row)
        if owner not in orders[message][field]:orders[message][field].append(owner)
    sends={r['rpc']:r for r in client if r['kind']=='http-send' and r['method']=='GET' and '/carts/' in r['uri']}
    responses={r['rpc']:r for r in client if r['kind']=='rpc-exit'}
    if len(sends)!=sum(r['kind']=='http-send' and r['method']=='GET' and '/carts/' in r['uri'] for r in client):raise ValueError('Duplicate send ID')
    result={};unresolved=[]
    for message,send in sends.items():
        response=responses.get(message)
        if response is None or response['status']!='200':raise ValueError('Missing successful Carts reply')
        fields={f['path']:f for f in response['fields']}
        indices=sorted({int(m[1]) for path in fields if (m:=re.fullmatch(r'result#body\[(\d+)\]#quantity',path))})
        producers=orders[message]['quantity']
        if indices!=list(range(len(indices))) or len(producers)!=len(indices) or any(orders[message][p]!=producers for p in PROPERTIES):
            unresolved.append({'message':message,'reason':'Missing/ambiguous ordered response property observations'});continue
        selected={}
        for index,owner in enumerate(producers):
            for prop in PROPERTIES:
                reads=candidates[message][owner].get(prop,[]);path='result#body['+str(index)+']#'+prop;target=fields.get(path)
                if not reads or target is None or any(r['http_uri']!=send['uri'].removeprefix('http://carts') for r in reads):
                    unresolved.append({'message':message,'reason':'Incomplete exact property/URI binding'});continue
                if any(r['observed'].get('value')!=target['observed'].get('value') for r in reads):
                    unresolved.append({'message':message,'reason':'Selected field value changed; no value-based rematching'});continue
                selected[(message,path)]={'service':'carts','message':message,'item_index':index,'field':prop,
                    'access_method':reads[-1]['access_method'],'owner':owner,'read_sequences':[r['seq'] for r in reads],
                    'receiver_owner':target['owner'],'receiver_field':target['field'],'receiver_version':target['version'],
                    'receiver_rpc_exit_seq':response['seq']}
        result.update(selected)
    return result,unresolved


def infer(run):
    capture=run/'boundary-events/carts';model=accessor_model(capture,'carts','Item')
    file=capture/'works_weave_socks_cart_entities_Item.original.class'
    if 'com/fasterxml/jackson/annotation/' in disassemble(file,True):raise ValueError('Custom property annotations require a serialization model')
    server=read_events(capture/'events.jsonl');client=read_events(run/'tracefusion-events/events.jsonl')
    bindings,unknown=bridge(server,client,model)
    scalar,_=derive(run/'tracefusion-events');local=service_infer(run/'tracefusion-events',scalar)
    entries={r['frame']:r for r in client if r['kind']=='enter'};exits={r['frame']:r for r in client if r['kind']=='exit'}
    targets=[]
    for answer in local['answers']:
        total=next(f for f in answer['fields'] if f['path']=='arg#total')
        source_coordinates=[tuple(s) for s in total['sources']]
        known=total['status']=='resolved' and all(s in bindings for s in source_coordinates)
        targets.append({'root_frame':answer['root_frame'],'trace_id_for_audit_only':entries[answer['root_frame']]['trace_id'],
            'target_field':'works.weave.socks.orders.entities.CustomerOrder.total',
            'target_seq':exits[answer['root_frame']]['seq'],'known':known,
            'sources':[bindings[s] for s in source_coordinates if s in bindings],
            'unbound_local_sources':[list(s) for s in source_coordinates if s not in bindings]})
    return {'kind':'carts-http-response-fields-to-orders-total','targets':targets,
        'http_field_bindings':list(bindings.values()),'unresolved_http_messages':unknown,
        'model':model,'labels_consumed':False,'join_policy':'Explicit message UUID + response list index + audited default property name; values only validate selected edges',
        'scope':'Carts response getter reads to Orders total; excludes Carts database provenance',
        'serialization_model':'Ordered list of default Item properties; unsupported/inconsistent observations stay unresolved',
        'accuracy_eligible':False,'performance_eligible':False}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',type=Path,required=True);parser.add_argument('--out',type=Path,required=True)
    a=parser.parse_args()
    if a.out.exists():raise ValueError('Refusing to replace evidence')
    a.out.write_text(json.dumps(infer(a.run.resolve()),indent=2)+'\n')
