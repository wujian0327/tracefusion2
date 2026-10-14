#!/usr/bin/env python3
"""Same explicit field access endpoints and labels for adapted FlowDist and TF.

Storage probes and derived-total probes have separate groups. Their projection
is aggregate per service JVM, not request-instance or end-to-end accuracy.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
from zipfile import ZipFile
import flowdist_preflight as tool
from audit_flowdist_coverage import canonical_rows, coverage
from compare_flowdist_total_queries import SOURCES
from infer_field_access_sites import infer, accessor_model, signature, read_events


def one(rows, method, field, write):
    matches=[]
    for index,row in enumerate(rows):
        head,body=row.split(' - ',1)
        if head!=method:continue
        refs=re.findall(r'<([^:]+): ([^>]+)>',body)
        if len(refs)!=1:continue
        owner,typed=refs[0];name=typed.rsplit(' ',1)[-1]
        if owner+'.'+name!=field:continue
        if ('> = ' in body)==write:matches.append((index,row))
    if len(matches)!=1:raise ValueError('Ambiguous field-only endpoint: '+method+'/'+field)
    return matches[0]


def freeze(pilot, graphs, out):
    out.mkdir(parents=True,exist_ok=False);queries=[];models={}
    for role,entity,fields in (('carts','Item',['quantity','unitPrice','itemId']),('shipping','Shipment',['id','name'])):
        model=accessor_model(pilot/'tracefusion/boundary-events'/role,role,entity);models[role]=model
        rows=(graphs[role]/'work/ServiceGraph/stmtids.out').read_text().splitlines()
        for source in fields:
            setters=[key for key,value in model['setters'].items() if value['field']==model['owner']+'.'+source]
            if len(setters)!=1:raise ValueError('Source must be an audited single-field setter')
            for sink in fields:
                getters=[key for key,value in model['getters'].items() if key.startswith('get') and value['field']==model['owner']+'.'+sink]
                if len(getters)!=1:raise ValueError('Sink must be an audited single-field getter')
                sm,tm=signature(model,setters[0]),signature(model,getters[0])
                first=one(rows,sm,model['owner']+'.'+source,True);last=one(rows,tm,model['owner']+'.'+sink,False)
                queries.append({'id':role+'-'+source+'-to-'+sink,'group':role+'-DTO-field-storage','role':role,
                    'source_field':model['owner']+'.'+source,'sink_field':model['owner']+'.'+sink,
                    'source_method':sm,'sink_method':tm,'source_statement_id':first[0],'sink_statement_id':last[0],
                    'query':first[1]+'; '+last[1],'expected_dependency':source==sink})
    rows=(graphs['orders']/'work/ServiceGraph/stmtids.out').read_text().splitlines()
    sink=[(i,r) for i,r in enumerate(rows) if 'CustomerOrder: void <init>(' in r.split(' - ')[0] and ': float total> =' in r]
    if len(sink)!=1:raise ValueError('Unique physical total write required')
    for owner,field,getter,expected in SOURCES:
        matches=[(i,row) for i,row in enumerate(rows) if '.entities.'+owner+':' in row.split(' - ')[0]
                 and ' '+getter+'()>' in row.split(' - ')[0] and ' '+field+'>' in row.split(' - ')[1]]
        if len(matches)!=1:raise ValueError('Unique physical source field read required')
        source=matches[0]
        queries.append({'id':'orders-'+owner+'-'+field+'-to-total','group':'orders-derived-total','role':'orders',
            'source_field':'works.weave.socks.orders.entities.'+owner+'.'+field,
            'sink_field':'works.weave.socks.orders.entities.CustomerOrder.total',
            'source_method':source[1].split(' - ')[0],'sink_method':sink[0][1].split(' - ')[0],
            'source_statement_id':source[0],'sink_statement_id':sink[0][0],
            'query':source[1]+'; '+sink[0][1],'expected_dependency':expected})
    tool.save(out/'frozen-field-queries.json',{'queries':queries,'accessor_models':models,
        'graph_statement_sha256':{role:hashlib.sha256((path/'work/ServiceGraph/stmtids.out').read_bytes()).hexdigest() for role,path in graphs.items()},
        'policy':'Explicit scalar value dependence, aggregate by actual field instruction site per service JVM',
        'oracle':'Audited original independent-field setters/getters and quantity*unitPrice sum formula; input schema selects the fields, not query outcomes.',
        'query_freeze':'Selectors/labels frozen before native predictions; observations were available for endpoint qualification; calibration, not blinded benchmark.',
        'request_instances_tested':False,'cross_process_paths_tested':False})


def project(query, prediction, observations):
    role=query['role'];source=query['source_method'];sink=query['sink_method']
    if role!='orders':
        block=prediction['storage'][role];reads=block['sinks'].get(sink,[])
        if source not in block['observed_write_sites'] or not reads:return None,'unobserved-access-site'
        if any(r['known'] and r['origin']==source and r['origin_field']==query['source_field'] for r in reads):
            return True,'physical-write-to-read: same owner/field/version and immutable-value check'
        if any(not r['known'] for r in reads):return None,'unresolved-reaching-write; reflective/DB provenance is not invented'
        return False,'all observed reaching field definitions are from other access sites'
    observed={r.get('access_method') for r in observations['orders'] if r['kind']=='read'}
    if source not in observed:return None,'unobserved-source-field-read'
    targets=[value for value in prediction['derived_total'].values() if value['target']==sink]
    if not targets or any(not value['known'] for value in targets):return None,'unresolved-derived-target'
    return any(source in value['origin_read_sites'] for value in targets),'existing scalar/stream reconstruction bound to physical getter read and total write'


def summarize(rows):
    tp=sum(r['prediction'] is True and r['expected_dependency'] for r in rows)
    fp=sum(r['prediction'] is True and not r['expected_dependency'] for r in rows)
    tn=sum(r['prediction'] is False and not r['expected_dependency'] for r in rows)
    fn=sum(r['expected_dependency'] and r['prediction'] is not True for r in rows)
    unknown=sum(r['prediction'] is None for r in rows)
    return {'queries':len(rows),'tp':tp,'fp':fp,'fn_including_unknown_positive':fn,'tn':tn,'unknown':unknown,
        'answered':len(rows)-unknown,'exact_rate':(tp+tn)/len(rows),'coverage':(len(rows)-unknown)/len(rows),
        'precision':tp/(tp+fp) if tp+fp else None,'recall':tp/(tp+fn) if tp+fn else None,
        'f1':2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else None}


def evaluate(repo,pilot,graphs,out):
    tool.verify_repository(repo)
    for mode in ('flowdist','tracefusion'):
        execution=json.loads((pilot/mode/'result.json').read_text())
        if execution['status'] not in ('business-passed','business-and-common-observer-passed') or execution.get('frontend_errors') or not execution['cases'] or not all(c['business_passed'] for c in execution['cases']):
            raise ValueError('Incomplete common business workload')
    if json.loads((pilot/'flowdist/protocol.json').read_text())!=json.loads((pilot/'tracefusion/protocol.json').read_text()):
        raise ValueError('Different common workload protocols')
    contract=json.loads((out/'frozen-field-queries.json').read_text());runtime=pilot/'flowdist/runtime'
    prepared={}
    for role,static in graphs.items():
        manifest=json.loads((static/'manifest.json').read_text())
        if manifest.get('dependency_policy')!='explicit-data-only':raise ValueError('Data-only native graph required')
        graph=static/'work/ServiceGraph';reference=(graph/'stmtids.out').read_text().splitlines()
        if hashlib.sha256((graph/'stmtids.out').read_bytes()).hexdigest()!=contract['graph_statement_sha256'][role]:raise ValueError('Frozen graph changed')
        if canonical_rows(reference)!=canonical_rows((runtime/role/'stmtids.out').read_text().splitlines()):raise ValueError('Runtime/graph indices differ')
        mapping=[set(map(int,row.split())) for row in (runtime/role/'entitystmt.out.branch').read_text().splitlines()]
        _,covered=coverage(runtime/role/'stmtCoverage1.out',mapping,len(reference));prepared[role]=(graph,covered)
    deps=out/'compile-deps'
    with ZipFile(repo/'tool/soot-trunk.jar') as archive:
        for name in archive.namelist():
            if name.endswith('.class') and not name.startswith('/'):
                file=deps/name;file.parent.mkdir(parents=True,exist_ok=True);file.write_bytes(archive.read(name))
    launcher=out/'launcher';launcher.mkdir()
    asm=Path('artifacts/java-collection-deps/asm-9.7.1.jar').resolve()
    tree=asm.with_name('asm-tree-9.7.1.jar')
    compile_cp=':'.join(map(str,[asm,tree,deps,repo/'tool/FLOWDIST.jar',repo/'tool/DUA1.jar']))
    subprocess.run(['javac','--release','8','-cp',compile_cp,'-d',str(launcher),
                    str(Path(__file__).with_name('FlowDistFieldDecision.java')),
                    str(Path(__file__).with_name('FlowDistFieldIndexPatch.java'))],capture_output=True,check=True,timeout=30)
    patch=subprocess.run(['java','-cp',str(launcher)+':'+compile_cp,'FlowDistFieldIndexPatch',
                          str(repo/'tool/FLOWDIST.jar'),str(launcher)],capture_output=True,text=True,check=True,timeout=30)
    (out/'index-patch.log').write_text(patch.stdout+patch.stderr)
    tool.save(out/'adapter-manifest.json',{
        'configuration':'FlowDist + full-event decoder + graph method-ID lookup compatibility fix',
        'author_jar_sha256':tool.TOOL_HASHES['FLOWDIST.jar'],
        'original_jar_unchanged':True,'loaded_graph_class_modified':True,
        'class_change':'In query buildGraph overload only: EAmethod2idx.get(method) -> this.method2idx.get(method)',
        'inverse_patch_canonical_byte_comparison_passed':True,
        'patched_class_sha256':hashlib.sha256((launcher/'disttaint/DynTransferGraph.class').read_bytes()).hexdigest(),
        'decode_policy':'Read Map implementations; retain all original timestamps, signed method IDs and event order; separate process clock metadata from method index.',
        'native_calls':['OT3AnalysisAll.init','DynTransferGraph.buildGraph(query, full events)',
                        'DynTransferGraph.postPruneByCoverage','OT3AnalysisAll.computeNodes'],
        'custom_field_edges':False,'custom_path_search':False,'static_fallback_permitted':False})
    prediction=infer(pilot/'tracefusion');tool.save(out/'tracefusion-site-predictions.json',prediction)
    obs={'orders':read_events(pilot/'tracefusion/tracefusion-events/events.jsonl')}
    results={'flowdist':[],'tracefusion':[]}
    controls=[]
    for query in contract['queries']:
        role=query['role'];graph,covered=prepared[role];target=out/query['id'];work=target/'work';work.mkdir(parents=True)
        shutil.copytree(graph,work/'graph');shutil.copytree(launcher,work/'launcher')
        for name in ('methodList.out','coveredMethods.txt'):shutil.copyfile(graphs[role]/'work'/name,work/name)
        shutil.copyfile(graphs[role]/'work/methodList.out',work/'methodsInPair.out')
        traces=work/'traces';traces.mkdir()
        for trace in (runtime/role).rglob('*.em'):shutil.copyfile(trace,traces/trace.name)
        (work/'query.txt').write_text(query['query']+'\n');(work/'graph/stmtCoverageOT1.out').write_text(' '.join(map(str,sorted(covered)))+'\n')
        (work/'graph/stmtCoverage1.out').unlink(missing_ok=True)
        tool.execute(repo,target,'statement-query',['-Xmx1g','-ea','-cp','/work/launcher:'+tool.CP,'FlowDistFieldDecision',
            '/work/query.txt','/work/traces','/work/graph','-method','-stmtcov','-postprune','-debug',''])
        log=(target/'statement-query.log').read_text();match=re.search(r'FLOWDIST_ORIGINAL_FLAGS=(\{[^\n]+\})',log)
        if not match:raise ValueError('Missing native flags')
        flags=json.loads(match[1]);active=query['source_statement_id'] in covered and query['sink_statement_id'] in covered
        valid=active and flags['source_nodes']>0 and flags['sink_nodes']>0
        fd=True if valid and flags['is_local'] else False if valid and flags['no_dependency'] else None
        tf,basis=project(query,prediction,obs)
        results['flowdist'].append(dict(query,prediction=fd,original_flags=flags,endpoints_observed=active))
        results['tracefusion'].append(dict(query,prediction=tf,basis=basis))
        if (role,query['source_field'].rsplit('.',1)[-1]) in (('carts','quantity'),('carts','unitPrice'),('shipping','id'),('orders','quantity')) and (role=='orders' or query['source_field']==query['sink_field']):
            # Separate native positive controls: getter read -> its actual return.
            source=query['query'].split('; ',1)[0 if role=='orders' else 1]
            method=source.split(' - ',1)[0]
            returns=[r for r in (graph/'stmtids.out').read_text().splitlines() if r.startswith(method+' - return ')]
            if len(returns)!=1:raise ValueError('Ambiguous native positive control')
            control=out/'positive-controls'/query['id'];shutil.copytree(work,control/'work')
            text=source+'; '+returns[0];(control/'work/query.txt').write_text(text+'\n')
            tool.execute(repo,control,'control',['-Xmx1g','-ea','-cp','/work/launcher:'+tool.CP,
                'FlowDistFieldDecision','/work/query.txt','/work/traces','/work/graph'])
            flags=json.loads(re.search(r'FLOWDIST_ORIGINAL_FLAGS=(\{[^\n]+\})',(control/'control.log').read_text())[1])
            if not flags['is_local'] or not flags['source_nodes'] or not flags['sink_nodes']:raise ValueError('Native getter-read to return positive control failed')
            controls.append({'query':text,'flags':flags,'passed':True})
    if len(controls)!=4:raise ValueError('Missing native positive controls')
    groups=sorted({q['group'] for q in contract['queries']})
    report={'kind':'common-physical-field-access-comparison','scope':contract['policy'],'results':results,
        'summary':{mode:summarize(rows) for mode,rows in results.items()},
        'groups':{group:{mode:summarize([r for r in rows if r['group']==group]) for mode,rows in results.items()} for group in groups},
        'accuracy_eligible':False,'performance_eligible':False,
        'positive_controls':controls,'controls_in_scored_denominator':False,
        'flowdist_configuration':'FlowDist + full-event decoder and one method-ID namespace fix',
        'limitations':['20 bounded aggregate field-site queries, not all field instances of five APIs or full distributed paths.',
                       'Storage accessors exercise Carts/Shipping DTO value persistence; Orders probes exercise derived total.',
                       'Unknowns remain in exact-query/coverage denominators; unknown positives count as misses.',
                       'FlowDist + full-event decoder and one trace-ID/graph-ID lookup fix; original query traversal, edge rules and statement search retained.',
                       'Source selectors bind to physical field instructions; partial reflective/DB writes may leave TF provenance unknown.']}
    tool.save(out/'comparison.json',report)
    rows=[{'group':group,'configuration':mode,**values} for group,modes in report['groups'].items() for mode,values in modes.items()]
    with (out/'field-comparison.csv').open('w',encoding='utf-8-sig',newline='') as file:
        writer=csv.DictWriter(file,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=('freeze','evaluate'))
    for flag in ('repo','pilot','orders','carts','shipping','out'):parser.add_argument('--'+flag,type=Path,required=True)
    a=parser.parse_args();graphs={role:getattr(a,role).resolve() for role in ('orders','carts','shipping')}
    if a.action=='freeze':freeze(a.pilot.resolve(),graphs,a.out.resolve())
    else:evaluate(a.repo.resolve(),a.pilot.resolve(),graphs,a.out.resolve())
