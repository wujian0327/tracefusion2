#!/usr/bin/env python3
"""First common distributed field-type pilot: Carts response -> Orders total.

FlowDist: original process-clock candidate + original per-JVM graph queries +
explicit default JSON property model. TF: message-instance reconstruction,
projected to the same aggregate field types. Never feed UUID joins to FlowDist.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import re
import shutil
from infer_field_access_sites import accessor_model, signature
from service_model import disassemble
from compare_field_accesses import one, summarize
from audit_flowdist_coverage import coverage, canonical_rows
from flowdist_query import query as method_query
import flowdist_preflight as tool


def freeze(tf,graphs,out):
    out.mkdir(parents=True,exist_ok=False)
    models={role:accessor_model(tf/('boundary-events/carts' if role=='carts' else 'tracefusion-events'),role,'Item') for role in ('carts','orders')}
    rows={role:(root/'work/ServiceGraph/stmtids.out').read_text().splitlines() for role,root in graphs.items()}
    sink=[(i,r) for i,r in enumerate(rows['orders']) if 'CustomerOrder: void <init>(' in r.split(' - ')[0] and ': float total> =' in r]
    if len(sink)!=1:raise ValueError('Unique total field write required')
    for role in models:
        capture=tf/('boundary-events/carts' if role=='carts' else 'tracefusion-events')
        owner=models[role]['owner'].replace('.','_')
        if 'com/fasterxml/jackson/annotation/' in disassemble(capture/(owner+'.original.class'),True):raise ValueError('Custom Jackson property mapping unsupported')
    queries=[]
    for prop,getter,expected in (('quantity','getQuantity',True),('unitPrice','getUnitPrice',True),('itemId','getItemId',False)):
        endpoints={}
        for role,model in models.items():
            methods=[(key,value) for key,value in model['getters'].items() if key.startswith(getter+'(')]
            if len(methods)!=1:raise ValueError('Unique direct field getter required')
            key,value=methods[0];method=signature(model,key);site=one(rows[role],method,value['field'],False)
            returns=[(i,r) for i,r in enumerate(rows[role]) if r.startswith(method+' - return ')]
            if len(returns)!=1:raise ValueError('Unique getter return required')
            endpoints[role]={'method':method,'field':value['field'],'type':value['descriptor'],'read_id':site[0],
                             'read':site[1],'return':returns[0][1]}
        if endpoints['carts']['type']!=endpoints['orders']['type']:raise ValueError('Different property types')
        queries.append({'id':prop+'-to-total','property':prop,'expected_dependency':expected,'endpoints':endpoints,
                        'sink':sink[0][1],'sink_id':sink[0][0]})
    tool.save(out/'frozen-queries.json',{'queries':queries,'scope':'Aggregate field-type value dependence across Carts HTTP response and Orders total',
        'shared_transport_model':'Default Item JSON property name/type, ordered list body; no custom property annotations',
        'oracle':'Independent business formula: sum of quantity*unitPrice plus constant shipping cost; itemId is not consumed by formula',
        'freeze_status':'Endpoint qualification observations available; queries frozen before composite predictions; calibration, not blinded benchmark',
        'request_instance_scoring':False,'models':models,
        'statement_sha256':{role:hashlib.sha256((root/'work/ServiceGraph/stmtids.out').read_bytes()).hexdigest() for role,root in graphs.items()}})


def local_query(repo,run,static,template,out,source,sink,stream=None):
    graph=static/'work/ServiceGraph'
    # Soot signatures use dotted packages; determine the role from declaring class.
    role='carts' if 'works.weave.socks.cart.' in source else 'orders';runtime=run/'runtime'/role
    rows=(graph/'stmtids.out').read_text().splitlines()
    if canonical_rows(rows)!=canonical_rows((runtime/'stmtids.out').read_text().splitlines()):raise ValueError('Mismatched runtime indices')
    mapping=[set(map(int,r.split())) for r in (runtime/'entitystmt.out.branch').read_text().splitlines()]
    _,covered=coverage(runtime/'stmtCoverage1.out',mapping,len(rows))
    if rows.index(source) not in covered or rows.index(sink) not in covered:raise ValueError('Unobserved query endpoint')
    work=out/'work';work.mkdir(parents=True);shutil.copytree(graph,work/'graph');shutil.copytree(template/'launcher',work/'launcher')
    if (work/'launcher/disttaint/DynTransferGraph.class').exists():raise ValueError('Original engine class required for all-query baseline')
    for name in ('methodList.out','coveredMethods.txt'):shutil.copyfile(static/'work'/name,work/name)
    shutil.copyfile(static/'work/methodList.out',work/'methodsInPair.out');(work/'traces').mkdir()
    for trace in runtime.glob('Local*.em'):shutil.copyfile(trace,work/'traces'/trace.name)
    (work/'query.txt').write_text(source+'; '+sink+'\n')
    (work/'graph/stmtCoverageOT1.out').write_text(' '.join(map(str,sorted(covered)))+'\n');(work/'graph/stmtCoverage1.out').unlink(missing_ok=True)
    arguments=['-Xmx1g','-ea','-cp','/work/launcher:'+tool.CP,'FlowDistFieldDecision','/work/query.txt','/work/traces','/work/graph','--all-query-matching']
    if stream:
        shutil.copyfile(stream,work/'stream-model.tsv');arguments.append('/work/stream-model.tsv')
    tool.execute(repo,out,'field-query',arguments)
    raw=(out/'field-query.log').read_text();flags=json.loads(re.search(r'FLOWDIST_ORIGINAL_FLAGS=(\{[^\n]+\})',raw)[1])
    if flags['source_nodes']!=1 or flags['sink_nodes']!=1:raise ValueError('Ambiguous physical field endpoint')
    if flags['is_local']:return True,flags
    if flags['no_dependency']:return False,flags
    return None,flags


def evaluate(repo,fd,tf,graphs,template,stream,qualification,reconstruction,out):
    contract=json.loads((out/'frozen-queries.json').read_text());control=json.loads((qualification/'result.json').read_text())
    if not control['all_passed'] or len(control['controls'])!=11:raise ValueError('Native framework stages unqualified')
    left=json.loads((fd/'result.json').read_text());right=json.loads((tf/'result.json').read_text())
    for report in (left,right):
        if report['status']!='business-passed' or report['frontend_errors'] or not all(c['business_passed'] for c in report['cases']):raise ValueError('Business collection failed')
    if json.loads((fd/'protocol.json').read_text())!=json.loads((tf/'protocol.json').read_text()):raise ValueError('Unequal common protocol')
    image_sets=[{s:v['image'] for s,v in json.loads((run/'compose.lock.json').read_text())['services'].items()} for run in (fd,tf)]
    if image_sets[0]!=image_sets[1]:raise ValueError('Unequal business images')
    for role,graph in graphs.items():
        if hashlib.sha256((graph/'work/ServiceGraph/stmtids.out').read_bytes()).hexdigest()!=contract['statement_sha256'][role]:raise ValueError('Frozen graph changed')
    rebuilt=json.loads(reconstruction.read_text())
    if rebuilt['unresolved_http_messages'] or not rebuilt['targets'] or not all(t['known'] for t in rebuilt['targets']):raise ValueError('Unqualified TF HTTP reconstruction')
    fields={s['field'] for target in rebuilt['targets'] for s in target['sources']}
    source=out/'method-input';traces=source/'work/traces/test1';traces.mkdir(parents=True)
    for role in ('carts','orders'):
        snapshots=sorted((fd/'runtime'/role/'test1').glob('Remote*.em'))
        if not snapshots:raise ValueError('No final native Remote capture')
        shutil.copyfile(snapshots[-1],traces/snapshots[-1].name)
    results={'flowdist':[],'tracefusion':[]}
    for q in contract['queries']:
        producer=q['endpoints']['carts'];receiver=q['endpoints']['orders']
        remote=method_query(repo,source,out/q['id']/'remote',producer['method']+'; '+q['sink'].split(' - ',1)[0])
        inspection=json.loads((out/q['id']/'remote/trace-inspection-stage.json').read_text())
        if not inspection['reciprocal_peer_correlation'] or not inspection['distinct_server_client_roles']:raise ValueError('Native process clock correlation missing')
        produced,pflags=local_query(repo,fd,graphs['carts'],template,out/q['id']/'producer',producer['read'],producer['return'])
        if produced is not True:raise ValueError('Native serialization producer control failed')
        consumed,cflags=local_query(repo,fd,graphs['orders'],template,out/q['id']/'receiver',receiver['read'],q['sink'],stream)
        prediction=consumed if remote['decision']=='candidate-flow' else False
        results['flowdist'].append(dict(q,prediction=prediction,producer_flags=pflags,receiver_flags=cflags,
            process_candidate=remote['decision'],composition='Original process-clock candidate AND original producer field-to-return AND shared typed JSON property model AND original receiver field-to-total'))
        results['tracefusion'].append(dict(q,prediction=q['property'] in fields,
            basis='Actual same-message Carts field reads -> Orders response DTO -> reconstructed total; aggregate property projection'))
    report={'kind':'distributed-carts-response-to-orders-total-field-type-pilot','scope':contract['scope'],
        'results':results,'summary':{mode:summarize(rows) for mode,rows in results.items()},
        'flowdist_configuration':'Original process-clock method phase + original all-query full-trace matching + normal-return probes + sequential Stream and default JSON property models',
        'flowdist_uuid_or_tf_inference_consumed':False,'native_framework_controls_passed':11,
        'tracefusion_target_orders':len(rebuilt['targets']),'tracefusion_actual_field_paths':sum(len(t['sources']) for t in rebuilt['targets']),
        'native_request_instance_resolution_tested':False,'accuracy_eligible':False,'performance_eligible':False,
        'limitations':['Three aggregate field-type queries only; neither a full five-API benchmark nor a reproduction of paper accuracy.',
            'Default source-conditioned native matching diagnostics are retained separately; this configuration uses another author-provided builder without changing its search.',
            'Distributed FlowDist result is a disclosed composition using a high-level JSON boundary model, not an unmodified OT3 socket-level path report.',
            'TF UUID-resolved instances are projected to aggregate field types for common scoring; no native per-request claims.',
            'Normal-return instrumentation changes event volume; no previous runtime/memory numbers qualify this configuration.']}
    tool.save(out/'comparison.json',report)
    with (out/'main-table.csv').open('w',encoding='utf-8-sig',newline='') as file:
        table=[{'configuration':mode,**summary} for mode,summary in report['summary'].items()]
        writer=csv.DictWriter(file,fieldnames=list(table[0]));writer.writeheader();writer.writerows(table)
    print(json.dumps(report['summary'],indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=('freeze','evaluate'))
    for flag in ('repo','flowdist','tracefusion','orders','carts','template','stream-model','qualification','reconstruction','out'):
        parser.add_argument('--'+flag,type=Path,required=True)
    a=parser.parse_args();graphs={r:getattr(a,r).resolve() for r in ('orders','carts')}
    if a.action=='freeze':freeze(a.tracefusion.resolve(),graphs,a.out.resolve())
    else:evaluate(a.repo.resolve(),a.flowdist.resolve(),a.tracefusion.resolve(),graphs,a.template.resolve(),a.stream_model.resolve(),a.qualification.resolve(),a.reconstruction.resolve(),a.out.resolve())
