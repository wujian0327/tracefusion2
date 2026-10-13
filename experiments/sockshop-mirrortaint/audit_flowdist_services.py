#!/usr/bin/env python3
"""Align measured service coverage with the lambda-extended static graphs.

This checks per-service indices, not cross-process DTO transfer or accuracy.
"""
import argparse
import hashlib
import json
from pathlib import Path
from audit_flowdist_coverage import canonical_rows,coverage
import flowdist_preflight as tool


def audit(runtime,orders,shipping,out):
    result=json.loads((runtime/'result.json').read_text())
    if result['status']!='order-async-mq-delivery-and-peer-compatibility-passed':
        raise ValueError('Full runtime compatibility not passed')
    roles={}
    for role,static in (('orders',orders),('shipping',shipping)):
        home=runtime/'runtime'/role;graph=static/'work/ServiceGraph'
        meta=json.loads((static/'service-refinement-stage.json').read_text())
        if meta['exit_code']!=0 or meta['errors']:raise ValueError('Static refinement failed')
        ids=home/'stmtids.out';graph_ids=graph/'stmtids.out'
        rows=ids.read_text().splitlines()
        if canonical_rows(rows)!=canonical_rows(graph_ids.read_text().splitlines()):
            raise ValueError('Measured/static statement indices differ for '+role)
        mapping=[set(map(int,r.split())) for r in (home/'entitystmt.out.branch').read_text().splitlines()]
        branches,statements=coverage(home/'stmtCoverage1.out',mapping,len(rows))
        controller=' newOrder(' if role=='orders' else ' postShipping('
        hits=[i for i in sorted(statements) if controller in rows[i]]
        if not hits:raise ValueError('Controller absent from measured coverage')
        counts=json.loads((static/'result.json').read_text())
        roles[role]={'static_artifact':str(static),'graph_nodes':counts['nodes'],'graph_edges':counts['edges'],
            'branches_hit':len(branches),'branches_mapped':len(mapping),'statements_hit':len(statements),
            'statements_mapped':len(rows),'controller_statements_hit':len(hits),
            'covered_statement_ids':sorted(statements),'per_index_alignment':'local-renaming-only',
            'coverage_scope':'cumulative process startup, health checks and one target order',
            'statement_coverage_method':'author branch-to-statement inference',
            'sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in
                (ids,graph_ids,graph/'staticVtg.dat',home/'entitystmt.out.branch',home/'stmtCoverage1.out')}}
    report={'kind':'flowdist-service-coverage-static-alignment','runtime':str(runtime),'roles':roles,
        'per_service_static_graph_and_measured_indices_verified':True,
        'cross_process_statement_path_verified':False,'http_serialization_modeled':False,
        'lambda_capture_and_callback_dependencies_modeled':False,'accuracy_eligible':False,'performance_eligible':False}
    if out.exists():raise ValueError('Refusing to overwrite audit evidence')
    tool.save(out,report)
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('runtime','orders','shipping','out'):p.add_argument('--'+key,type=Path,required=True)
    a=p.parse_args();audit(a.runtime.resolve(),a.orders.resolve(),a.shipping.resolve(),a.out.resolve())
