#!/usr/bin/env python3
"""Independent frozen-business oracle and instance scoring, separate from inference."""
from collections import defaultdict
import argparse
import json
from pathlib import Path
from run_distributed_paths import check
from run_planned_service import load,save
from infer_distributed_fields import Reconstruction
from query_observation_planner import require


def one(xs,why):
    xs=list(xs);require(len(xs)==1,'Ambiguous oracle grounding: '+why+' ('+str(len(xs))+')');return xs[0]
def point(role,event,path):return (role,event['seq'],path)
def http(rows,phase,direction):return [r for r in rows if r['kind']=='http-json' and r['phase']==phase and r['direction']==direction]
def fields(event):return {f['path']:f for f in event['fields']}


def scored(case,path,a,expected,expected_nodes):
    predicted={tuple(k) for k in a['source_keys']} if a['known'] else set();expected=set(expected)
    return {'case':case,'path':path,'prediction':a,'expected_source_keys':[list(k) for k in sorted(expected,key=str)],
        'expected_sources':expected_nodes,'exact':a['known'] and predicted==expected,
        'tp':len(predicted&expected),'fp':len(predicted-expected),'fn':len(expected-predicted)}


def summary(queries):
    tp=sum(q['tp'] for q in queries);fp=sum(q['fp'] for q in queries);fn=sum(q['fn'] for q in queries)
    return {'queries':len(queries),'exact':sum(q['exact'] for q in queries),'unknown':sum(not q['prediction']['known'] for q in queries),
            'tp':tp,'fp':fp,'fn':fn,'precision':tp/(tp+fp) if tp+fp else None,'recall':tp/(tp+fn) if tp+fn else None,
            'f1':2*tp/(2*tp+fp+fn) if tp+fp+fn else None}


def sockshop(out,b):
    root=out/'sockshop';run=load(root/'run.json');require(run['status']=='business-passed','Business failed');g=Reconstruction(b,root,['orders','carts','shipping']);queries=[];no_target=0
    source_boundary={'service':'carts','kind':'http-json','phase':'write','direction':'response'}
    ship_boundary={'service':'orders','kind':'http-json','phase':'write','direction':'request'}
    source_json=http(g.rows['carts'],'write','response');client_rpcs=[r for r in g.rows['orders'] if r['kind']=='http-rpc-enter']
    outgoing=http(g.rows['orders'],'write','request');negative=[]
    for c in run['cases']:
        if not c['expected_target']:
            require(not any(k[0]=='orders' and r['message']==c['message'] and g.nodes[k]['path']=='/total' for k,r in g.json),'Declined order produced target');no_target+=1;continue
        fixture=load(root/c['case']/'fixture.json');order=load(root/c['case']/'order-response.json');uri='http://carts/carts/'+fixture['customer_id']+'/items'
        rpc=one((r for r in client_rpcs if r['uri']==uri and r['method']=='GET'),'actual cart RPC')
        source=one((r for r in source_json if r['message']==rpc['message']),'matching actual Carts response');sf=fields(source)
        index={}
        for path,f in sf.items():
            if path.endswith('/itemId'):index[f['observed']['value']]=path.rsplit('/',1)[0]
        require(set(index)==set(fixture['expected_items']),'Independent item record identities differ')
        expected_total=[];nodes=[]
        for ident in fixture['expected_items']:
            for prop in ('quantity','unitPrice'):
                path=index[ident]+'/'+prop;expected_total.append(point('carts',source,path));nodes.append(sf[path])
        a=g.query(c['message'],'/total','orders',source_boundary);queries.append(scored(c['case'],'/total',a,expected_total,nodes))
        for ident in fixture['expected_items']:
            path=index[ident]+'/itemId';negative.append({'case':c['case'],'query':'Carts.itemId -> Orders.total','expected':False,
                'predicted':list(point('carts',source,path)) in a['source_keys']})
        for i,item in enumerate(order['items']):
            for prop in ('itemId','quantity','unitPrice'):
                target='/items/'+str(i)+'/'+prop;source_path=index[item['itemId']]+'/'+prop
                a=g.query(c['message'],target,'orders',source_boundary);queries.append(scored(c['case'],target,a,[point('carts',source,source_path)],[sf[source_path]]))
        send=one((r for r in outgoing if r.get('uri')=='http://shipping/shipping' and fields(r).get('/name',{}).get('observed',{}).get('value')==fixture['customer_id']),'outbound original Shipment request')
        for prop in ('id','name'):
            target='/shipment/'+prop;a=g.query(c['message'],target,'orders',ship_boundary);queries.append(scored(c['case'],target,a,[point('orders',send,'/'+prop)],[fields(send)['/'+prop]]))
    require(all(not n['predicted'] for n in negative),'Negative itemId relation failed')
    report={'application':'Sock Shop','summary':summary(queries),'queries':queries,'no_target_checks':no_target,'negative_relations':negative,
        'query_families':{'total':summary([q for q in queries if q['path']=='/total']),
                          'returned_item_fields':summary([q for q in queries if q['path'].startswith('/items/')]),
                          'shipping_roundtrip':summary([q for q in queries if q['path'].startswith('/shipment/')])},
        'graph_stats':g.stats,'origin_oracle':'Frozen business formula, fixture record identity and actual RPC/source observation grounding; oracle does not invoke graph reachability.',
        'performance_eligible':False}
    save(root/'inference-graph.json',g.export());save(root/'field-results.json',report);return report


def trainguard(root,run):
    db=load(root/'independent-database.json');database={s['name']:s['_id'] for s in db}
    for c in run['cases']:
        if c['expected_id'] is not None:require(database[c['name']]==c['expected_id'],'Independent DB oracle differs')


def trainticket(out,b):
    root=out/'trainticket';run=load(root/'run.json');require(run['status']=='business-passed','Business failed');trainguard(root,run)
    g=Reconstruction(b,root,['station','basic','ticketinfo']);queries=[];negative=[]
    boundary={'service':'station','kind':'field-read'}
    trpc=[r for r in g.rows['ticketinfo'] if r['kind']=='http-rpc-enter'];brpc=[r for r in g.rows['basic'] if r['kind']=='http-rpc-enter'];server=http(g.rows['station'],'write','response')
    entries={r['frame']:r for r in g.rows['station'] if r['kind']=='enter'}
    exits=[r for r in g.rows['station'] if r['kind']=='exit' and 'fields' in r]
    for c in run['cases']:
        a=g.query(c['message'],'/data','ticketinfo',boundary);expected=[];expected_nodes=[]
        if c['expected_id'] is not None:
            first=one((r for r in trpc if r.get('parent_message')==c['message']),'TicketInfo child HTTP request')
            second=one((r for r in brpc if r.get('parent_message')==first['message']),'Basic child HTTP request')
            send=one((r for r in server if r['message']==second['message']),'Station response instance');f=fields(send)['/data']
            require(f['observed']['value']==c['expected_id'],'Station response differs from independent DB fact')
            returned=one((r for r in exits if r['result']['object']==f['owner']),'Station service returned wrapper object');root_frame=returned['frame']
            require(entries[root_frame]['args'][0]['value']==c['name'],'Wrong requested station')
            read=one((r for r in g.rows['station'] if r['kind']=='read' and r.get('frame')==root_frame and r['field']=='fdse/microservice/entity/Station.id'),'actual record id read')
            require(read['observed']['value']==c['expected_id'],'Decoded record differs from independent DB fact')
            expected=[('station','getter',read['seq'])];expected_nodes=[read]
            negative.append({'case':c['case'],'query':'Station.name -> TicketInfo.data','expected':False,
                'predicted':any(s.get('field')=='fdse/microservice/entity/Station.name' for s in a['sources']),
                'id_and_name_equal':c['name']==c['expected_id']})
        queries.append(scored(c['case'],'/data',a,expected,expected_nodes))
    require(all(not n['predicted'] for n in negative),'Negative name relation failed')
    report={'application':'Train Ticket','summary':summary(queries),'queries':queries,'negative_relations':negative,
            'constant_null_checks':sum(c['expected_id'] is None for c in run['cases']),'graph_stats':g.stats,
            'origin_oracle':'Frozen DB facts and public API outputs; actual request UUID parents and returned-wrapper identity ground source read instances independently of graph search.',
            'performance_eligible':False}
    save(root/'inference-graph.json',g.export());save(root/'field-results.json',report);return report


def evaluate(out,b):
    check(out,b);reports={'sockshop':sockshop(out,b),'trainticket':trainticket(out,b)}
    save(out/'comparison.json',{'results':{k:r['summary'] for k,r in reports.items()},'same_collector_and_inference_code':True,
        'source_boundaries':'Carts response fields; outbound Orders Shipment request fields; Station decoded entity fields. Database/network internal histories excluded.',
        'negative_relation_scope':'Supplementary per-execution field-role nondependence checks; not pooled as extra target-instance queries.',
        'performance_eligible':False})
    print(json.dumps({k:r['summary'] for k,r in reports.items()},indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);p.add_argument('--build',type=Path,required=True);a=p.parse_args();evaluate(a.out.resolve(),a.build.resolve())
