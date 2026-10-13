#!/usr/bin/env python3
"""Bounded aggregate field-type dependencies to total; not process-path accuracy.

Freeze source/sink statement selectors before predictions. Original FlowDist
decisions are read from its own flags; TraceFusion derives its own DTO model.
Missing endpoints or incomplete decisions remain unknown and fail exact checks.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
from zipfile import ZipFile

import flowdist_preflight as tool
from audit_flowdist_coverage import canonical_rows,coverage
from evaluate_five_methods import orders_claims


SOURCES=[('Item','quantity','getQuantity',True),('Item','unitPrice','getUnitPrice',True),
    ('Item','itemId','getItemId',False),('Customer','firstName','getFirstName',False),
    ('Address','street','getStreet',False),('Card','longNum','getLongNum',False),('Card','ccv','getCcv',False)]


def freeze(graph,out):
    out.mkdir(parents=True,exist_ok=False)
    rows=(graph/'stmtids.out').read_text().splitlines()
    sinks=[r for r in rows if 'CustomerOrder: void <init>(' in r and ': float total> =' in r]
    if len(sinks)!=1:raise ValueError('Ambiguous total sink')
    queries=[]
    for owner,field,getter,expected in SOURCES:
        sources=[r for r in rows if '.entities.'+owner+':' in r.split(' - ')[0]
            and ' '+getter+'()>' in r.split(' - ')[0] and ' '+field+'>' in r.split(' - ')[1]]
        if len(sources)!=1:raise ValueError('Ambiguous field source: '+owner+'.'+field)
        queries.append({'id':owner+'.'+field+'-to-total','field':field,'owner':owner,
            'expected_dependency':expected,'query':sources[0]+'; '+sinks[0],
            'source_statement_id':rows.index(sources[0]),'sink_statement_id':rows.index(sinks[0])})
    contract={'scope':'aggregate field-type dependency to total across the selected newOrder workload; Orders JVM only',
        'request_instance_disambiguation_tested':False,'cross_process_path_accuracy_tested':False,
        'oracle':'Independent original business formula: sum(Item.quantity * Item.unitPrice) + literal 4.99F',
        'graph_statement_sha256':hashlib.sha256((graph/'stmtids.out').read_bytes()).hexdigest(),
        'queries':queries,'second_human_reviewed':False}
    tool.save(out/'frozen-queries.json',contract)


def summarize(rows):
    known=[r for r in rows if r['prediction'] is not None]
    tp=sum(r['prediction'] is True and r['expected_dependency'] for r in rows)
    fp=sum(r['prediction'] is True and not r['expected_dependency'] for r in rows)
    tn=sum(r['prediction'] is False and not r['expected_dependency'] for r in rows)
    fn=sum(r['prediction'] is False and r['expected_dependency'] for r in rows)
    return {'queries':len(rows),'answered':len(known),'unknown':len(rows)-len(known),
        'correct':tp+tn,'exact_rate':(tp+tn)/len(rows),'tp':tp,'fp':fp,'tn':tn,'fn_answered':fn,
        'missed_positive_including_unknown':sum(r['expected_dependency'] and r['prediction'] is not True for r in rows),
        'precision':tp/(tp+fp) if tp+fp else None,
        'recall':tp/sum(r['expected_dependency'] for r in rows)}


def positive_controls(repo,scored,out):
    out.mkdir(parents=True,exist_ok=False)
    contract=json.loads((scored/'frozen-queries.json').read_text());controls=[]
    for field in ('quantity','unitPrice'):
        q=next(r for r in contract['queries'] if r['field']==field)
        work=out/field/'work';shutil.copytree(scored/q['id']/'work',work)
        rows=(work/'graph/stmtids.out').read_text().splitlines()
        source=q['query'].split('; ',1)[0];method=source.split(' - ')[0]
        returns=[r for r in rows if r.startswith(method+' - return ')]
        if len(returns)!=1:raise ValueError('Ambiguous original getter return')
        text=source+'; '+returns[0];(work/'query.txt').write_text(text+'\n')
        controls.append({'field':field,'query':text,'expected_dependency':True,
            'purpose':'Positive control of original runtime statement engine, outside scored total queries'})
    tool.save(out/'frozen-controls.json',controls)
    results=[]
    for q in controls:
        target=out/q['field']
        tool.execute(repo,target,'control-query',['-Xmx1g','-ea','-cp','/work/launcher:'+tool.CP,
            'FlowDistStatementDecision','/work/query.txt','/work/traces','/work/graph',
            '-method','-stmtcov','-postprune','-debug',''])
        raw=(target/'control-query.log').read_text()
        flags=json.loads(re.search(r'FLOWDIST_ORIGINAL_FLAGS=(\{[^\n]+\})',raw)[1])
        results.append(dict(q,flags=flags))
        if not flags['is_local'] or flags['source_nodes']<1 or flags['sink_nodes']<1:
            raise ValueError('Original getter-return positive control failed')
    tool.save(out/'result.json',{'positive_controls_passed':True,'controls':results,
        'included_in_seven_query_score':False})


def evaluate(repo,pilot,static,out):
    contract=json.loads((out/'frozen-queries.json').read_text());graph=static/'work/ServiceGraph'
    if hashlib.sha256((graph/'stmtids.out').read_bytes()).hexdigest()!=contract['graph_statement_sha256']:
        raise ValueError('Frozen statement map changed')
    fd=pilot/'flowdist';tf=pilot/'tracefusion'
    for run in (fd,tf):
        execution=json.loads((run/'result.json').read_text())
        if execution['status'] not in ('business-and-common-observer-passed','business-passed') or execution.get('frontend_errors') or \
            not execution['cases'] or not all(c['business_passed'] for c in execution['cases']):
            raise ValueError('Incomplete common workload')
    if json.loads((fd/'protocol.json').read_text())!=json.loads((tf/'protocol.json').read_text()):
        raise ValueError('Different common workload/observer protocols')
    runtime=fd/'runtime/orders';ids=(runtime/'stmtids.out').read_text().splitlines()
    if canonical_rows(ids)!=canonical_rows((graph/'stmtids.out').read_text().splitlines()):
        raise ValueError('Runtime and graph statement indices differ')
    mapping=[set(map(int,r.split())) for r in (runtime/'entitystmt.out.branch').read_text().splitlines()]
    _,covered=coverage(runtime/'stmtCoverage1.out',mapping,len(ids))
    deps=out/'compile-deps'
    with ZipFile(repo/'tool/soot-trunk.jar') as archive:
        for name in archive.namelist():
            if name.endswith('.class') and not name.startswith('/'):
                path=deps/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(archive.read(name))
    launcher=out/'launcher';launcher.mkdir()
    source=Path(__file__).with_name('FlowDistStatementDecision.java')
    cp=':'.join(map(str,[deps,repo/'tool/FLOWDIST.jar',repo/'tool/DUA1.jar']))
    subprocess.run(['javac','--release','8','-cp',cp,'-d',str(launcher),str(source)],check=True,capture_output=True,timeout=30)
    claims=orders_claims(tf,'tracefusion')
    business=json.loads((tf/'result.json').read_text())['cases']
    active=[c for c in business if c['phase']=='accuracy' and c.get('method','newOrder')=='newOrder' and c['expected_target']]
    targets=[(c['case'],(claims.get(c['trace_id']) or {}).get('arg#total')) for c in active]
    if not targets:raise ValueError('No original target field observations')
    tf_fields=set()
    tf_known=all(row and row['known'] for _,row in targets)
    if tf_known:
        for _,row in targets:
            for coordinate in row['sources']:
                if len(coordinate)!=5:tf_known=False;continue
                tf_fields.add(coordinate[-1])
    results={'flowdist':[],'tracefusion':[]}
    for q in contract['queries']:
        target=out/q['id'];work=target/'work';work.mkdir(parents=True)
        shutil.copytree(graph,work/'graph');shutil.copytree(launcher,work/'launcher')
        for name in ('methodList.out','coveredMethods.txt'):
            shutil.copyfile(static/'work'/name,work/name)
        shutil.copyfile(static/'work/methodList.out',work/'methodsInPair.out')
        traces=work/'traces';traces.mkdir()
        for trace in runtime.rglob('*.em'):shutil.copyfile(trace,traces/trace.name)
        if not list(traces.glob('Local*.em')):raise ValueError('Missing full original local method trace')
        (work/'query.txt').write_text(q['query']+'\n')
        (work/'graph/stmtCoverageOT1.out').write_text(' '.join(map(str,sorted(covered)))+'\n')
        (work/'graph/stmtCoverage1.out').unlink(missing_ok=True)
        tool.execute(repo,target,'statement-query',['-Xmx1g','-ea','-cp','/work/launcher:'+tool.CP,
            'FlowDistStatementDecision','/work/query.txt','/work/traces','/work/graph',
            '-method','-stmtcov','-postprune','-debug',''])
        raw=(target/'statement-query.log').read_text()
        match=re.search(r'FLOWDIST_ORIGINAL_FLAGS=(\{[^\n]+\})',raw)
        if not match:raise ValueError('Missing original decision flags')
        flags=json.loads(match[1]);prediction=None
        valid=q['source_statement_id'] in covered and q['sink_statement_id'] in covered
        valid=valid and flags['source_nodes']>0 and flags['sink_nodes']>0
        if valid:
            if flags['is_local']:prediction=True
            elif flags['no_dependency']:prediction=False
        results['flowdist'].append(dict(q,prediction=prediction,original_flags=flags,
            endpoints_covered=valid,log_sha256=hashlib.sha256(raw.encode()).hexdigest()))
        results['tracefusion'].append(dict(q,prediction=q['field'] in tf_fields if tf_known else None,
            supported_target_count=len(targets)))
    mt=pilot/'mirrortaint'
    if (mt/'result.json').is_file():
        mt_claims=orders_claims(mt,'mirrortaint')
        mt_business=json.loads((mt/'result.json').read_text())['cases']
        mt_active=[c for c in mt_business if c['phase']=='accuracy' and c.get('method','newOrder')=='newOrder' and c['expected_target']]
        if {c['case'] for c in mt_active}!={c['case'] for c in active}:
            raise ValueError('MirrorTaint has a different selected total-query workload')
        mt_targets=[(c['case'],(mt_claims.get(c['trace_id']) or {}).get('arg#total')) for c in mt_active]
        mt_known=bool(mt_targets) and all(row and row['known'] for _,row in mt_targets)
        mt_fields=set()
        if mt_known:
            for _,row in mt_targets:
                for coordinate in row['sources']:
                    if len(coordinate)!=5:mt_known=False;continue
                    mt_fields.add(coordinate[-1])
        results['mirrortaint']=[dict(q,prediction=q['field'] in mt_fields if mt_known else None,
            supported_target_count=len(mt_targets),
            projection='Aggregate field types from actual original-runtime source tags; no expected labels consumed') for q in contract['queries']]
    report={'kind':'flowdist-tracefusion-total-field-type-pilot','scope':contract['scope'],
        'queries':results,'summary':{mode:summarize(rows) for mode,rows in results.items()},
        'cross_process_path_accuracy_tested':False,'request_instance_accuracy_tested':False,
        'accuracy_eligible':False,'performance_eligible':False,
        'limitations':['Only seven aggregate field-type relations to total in the Orders JVM; not general accuracy.',
            'FlowDist uses original graph/query algorithms with disclosed lambda model and framework exclusions.',
            'TraceFusion uses its independently derived scalar/stream model; predictions do not read expected labels.',
            'MirrorTaint, when supplied in the pilot, projects its actual source tags to the same aggregate field types; adapters remain disclosed.',
            'Whole-deployment branch coverage includes startup and warmup; not individual request coverage.',
            'Cross-process source instance/path accuracy requires HTTP DTO modeling and separate evaluation.']}
    tool.save(out/'comparison.json',report)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=('freeze','evaluate','positive-controls'))
    for key in ('repo','out'):p.add_argument('--'+key,type=Path,required=True)
    for key in ('pilot','static','scored-queries'):p.add_argument('--'+key,type=Path)
    a=p.parse_args()
    if a.action=='positive-controls':
        if not a.scored_queries:p.error('--scored-queries required')
        positive_controls(a.repo.resolve(),a.scored_queries.resolve(),a.out.resolve())
    elif not a.static:p.error('--static required')
    elif a.action=='freeze':freeze(a.static.resolve()/'work/ServiceGraph',a.out.resolve())
    elif not a.pilot:p.error('--pilot required')
    else:evaluate(a.repo.resolve(),a.pilot.resolve(),a.static.resolve(),a.out.resolve())
