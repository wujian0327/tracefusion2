#!/usr/bin/env python3
"""Original statement queries for Carts/Shipping reference-flow controls.

These four aggregate reference controls do not share the scalar-field denominator
of the five-controller calibration. No accuracy ranking is derived from them.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
from zipfile import ZipFile
import subprocess
import flowdist_preflight as tool
from audit_flowdist_coverage import coverage, canonical_rows


def selected(rows, predicate, label):
    matches=[(i,row) for i,row in enumerate(rows) if predicate(row)]
    if len(matches)!=1:raise ValueError('Ambiguous original selector: '+label)
    return matches[0]


def freeze(carts, shipping, out):
    out.mkdir(parents=True,exist_ok=False)
    queries=[]
    rows=(carts/'work/ServiceGraph/stmtids.out').read_text().splitlines()
    source=selected(rows,lambda r:'CartResource: java.util.function.Supplier value()>' in r.split(' - ')[0] and 'findByCustomerId(' in r,'CartDAO actual query result')
    selectors=[('get',lambda r:'CartsController:' in r.split(' - ')[0] and ' get(' in r.split(' - ')[0] and r.split(' - ')[1].startswith('return ')),
               ('delete',lambda r:'CartResource: void lambda$destroy$' in r.split(' - ')[0] and 'CartDAO: void delete(' in r),
               ('mergeCarts',lambda r:'CartContentsResource: void lambda$add$' in r.split(' - ')[0] and 'CartDAO:' in r and ' save(' in r)]
    for method,predicate in selectors:
        sink=selected(rows,predicate,method+' sink')
        queries.append({'method':method,'role':'carts','source_statement_id':source[0],'sink_statement_id':sink[0],
                        'query':source[1]+'; '+sink[1],'expected_dependency':True,
                        'scope':'Aggregate CartDAO result collection reference to controller return/delete/save reference, across full workload'})
    rows=(shipping/'work/ServiceGraph/stmtids.out').read_text().splitlines()
    source=selected(rows,lambda r:'ShippingController:' in r.split(' - ')[0] and ' postShipping(' in r.split(' - ')[0] and '@parameter0:' in r,'Shipping argument')
    sink=selected(rows,lambda r:'ShippingController:' in r.split(' - ')[0] and ' postShipping(' in r.split(' - ')[0] and r.split(' - ')[1].startswith('return '),'Shipping return')
    queries.append({'method':'postShipping','role':'shipping','source_statement_id':source[0],'sink_statement_id':sink[0],
                    'query':source[1]+'; '+sink[1],'expected_dependency':True,'scope':'Original incoming Shipment reference is returned unchanged'})
    tool.save(out/'frozen-controls.json',{'queries':queries,'oracle':'Original business code plus independent nonempty fixture contracts; reference reachability only',
        'graph_statement_sha256':{role:hashlib.sha256((path/'work/ServiceGraph/stmtids.out').read_bytes()).hexdigest()
                                 for role,path in (('carts',carts),('shipping',shipping))},
        'scalar_field_calibration_denominator_shared':False,'cross_process_paths_tested':False})


def evaluate(repo, pilot, carts, shipping, out):
    contract=json.loads((out/'frozen-controls.json').read_text());static={'carts':carts,'shipping':shipping}
    compile=out/'compile-deps'
    with ZipFile(repo/'tool/soot-trunk.jar') as archive:
        for name in archive.namelist():
            if name.endswith('.class') and not name.startswith('/'):
                file=compile/name;file.parent.mkdir(parents=True,exist_ok=True);file.write_bytes(archive.read(name))
    launcher=out/'launcher';launcher.mkdir()
    source=Path(__file__).with_name('FlowDistStatementDecision.java')
    cp=':'.join(map(str,[compile,repo/'tool/FLOWDIST.jar',repo/'tool/DUA1.jar']))
    subprocess.run(['javac','--release','8','-cp',cp,'-d',str(launcher),str(source)],capture_output=True,check=True,timeout=30)
    results=[]
    for q in contract['queries']:
        role=q['role'];graph=static[role]/'work/ServiceGraph';runtime=pilot/'flowdist/runtime'/role
        if hashlib.sha256((graph/'stmtids.out').read_bytes()).hexdigest()!=contract['graph_statement_sha256'][role]:
            raise ValueError('Frozen graph map changed')
        reference=(graph/'stmtids.out').read_text().splitlines();actual=(runtime/'stmtids.out').read_text().splitlines()
        if canonical_rows(reference)!=canonical_rows(actual):raise ValueError('Runtime graph statement alignment failed')
        mapping=[set(map(int,row.split())) for row in (runtime/'entitystmt.out.branch').read_text().splitlines()]
        _,covered=coverage(runtime/'stmtCoverage1.out',mapping,len(reference))
        target=out/q['method'];work=target/'work';work.mkdir(parents=True)
        shutil.copytree(graph,work/'graph');shutil.copytree(launcher,work/'launcher')
        for name in ('methodList.out','coveredMethods.txt'):shutil.copyfile(static[role]/'work'/name,work/name)
        shutil.copyfile(static[role]/'work/methodList.out',work/'methodsInPair.out')
        traces=work/'traces';traces.mkdir()
        local=list(runtime.glob('Local*.em'))
        if len(local)!=1:raise ValueError('Expected final original Local trace')
        shutil.copyfile(local[0],traces/local[0].name)
        for remote in (runtime/'test1').glob('Remote*.em'):shutil.copyfile(remote,traces/remote.name)
        (work/'query.txt').write_text(q['query']+'\n')
        (work/'graph/stmtCoverageOT1.out').write_text(' '.join(map(str,sorted(covered)))+'\n')
        (work/'graph/stmtCoverage1.out').unlink(missing_ok=True)
        tool.execute(repo,target,'statement-query',['-Xmx1g','-ea','-cp','/work/launcher:'+tool.CP,
            'FlowDistStatementDecision','/work/query.txt','/work/traces','/work/graph','-method','-stmtcov','-postprune','-debug',''])
        log=(target/'statement-query.log').read_text();match=re.search(r'FLOWDIST_ORIGINAL_FLAGS=(\{[^\n]+\})',log)
        if not match:raise ValueError('Missing original query decision')
        flags=json.loads(match[1]);known=all(q[key] in covered for key in ('source_statement_id','sink_statement_id'))
        known=known and flags['source_nodes']>0 and flags['sink_nodes']>0
        prediction=True if known and flags['is_local'] else False if known and flags['no_dependency'] else None
        results.append(dict(q,prediction=prediction,original_flags=flags,endpoints_covered=known))
    tool.save(out/'result.json',{'kind':'flowdist-native-reference-controls','queries':results,
        'scalar_field_calibration_denominator_shared':False,'accuracy_eligible':False,'performance_eligible':False,
        'limitations':['Four positive-only reference controls, not a precision/recall benchmark.',
                       'Aggregate workload relations, not specific request instances or scalar fields.',
                       'Original lambda capture/callback and framework exclusions may affect reachability.']})


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=('freeze','evaluate'))
    for flag in ('repo','pilot','carts','shipping','out'):parser.add_argument('--'+flag,type=Path,required=True)
    a=parser.parse_args()
    if a.action=='freeze':freeze(a.carts.resolve(),a.shipping.resolve(),a.out.resolve())
    else:evaluate(a.repo.resolve(),a.pilot.resolve(),a.carts.resolve(),a.shipping.resolve(),a.out.resolve())
