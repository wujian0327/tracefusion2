#!/usr/bin/env python3
"""Positive stage controls for the real Carts response -> Orders total path.

These qualify model coverage, not a benchmark score. Failed positive controls
leave the main distributed field baseline unqualified instead of inventing FNs.
"""
import argparse
import json
from pathlib import Path
import re
import shutil
import flowdist_preflight as tool
from audit_flowdist_coverage import coverage, canonical_rows


def only(rows, predicate):
    values=[r for r in rows if predicate(r)]
    if len(values)!=1:raise ValueError('Ambiguous stage endpoint '+repr(values))
    return values[0]


def qualify(repo, pilot, template, orders, carts, out, only_stages=None, stream_model=None, all_queries=False):
    out.mkdir(parents=True,exist_ok=False)
    graphs={'orders':orders/'work/ServiceGraph','carts':carts/'work/ServiceGraph'}
    rows={role:(graph/'stmtids.out').read_text().splitlines() for role,graph in graphs.items()}
    stages=[]
    for role in ('carts','orders'):
        for field,getter in (('quantity','getQuantity'),('unitPrice','getUnitPrice')):
            read=only(rows[role],lambda r:('.Item: ' in r.split(' - ')[0] and ' '+getter+'()>' in r.split(' - ')[0] and ' '+field+'>' in r.split(' - ')[1]))
            returns=only(rows[role],lambda r:r.startswith(read.split(' - ')[0]+' - return '))
            stages.append({'id':role+'-'+field+'-getter','role':role,'source':read,'sink':returns,'expected':True})
            if role=='orders':
                mapper=only(rows[role],lambda r:'lambda$calculateTotal$' in r and ' - return ' in r)
                stages.append({'id':'orders-'+field+'-to-mapper','role':role,'source':read,'sink':mapper,'expected':True})
    mapper=only(rows['orders'],lambda r:'lambda$calculateTotal$' in r and ' - return ' in r)
    summed=only(rows['orders'],lambda r:' calculateTotal(' in r.split(' - ')[0] and 'double sum()>' in r)
    total=only(rows['orders'],lambda r:'CustomerOrder: void <init>(' in r.split(' - ')[0] and ': float total> =' in r)
    stages.extend([{'id':'orders-mapper-to-stream-sum','role':'orders','source':mapper,'sink':summed,'expected':True},
                   {'id':'orders-stream-sum-to-total','role':'orders','source':summed,'sink':total,'expected':True}])
    returned=only(rows['orders'],lambda r:' calculateTotal(' in r.split(' - ')[0] and ' - return ' in r)
    caller=only(rows['orders'],lambda r:' newOrder(' in r.split(' - ')[0] and ' = specialinvoke ' in r and ': float calculateTotal(' in r)
    stages.extend([{'id':'orders-sum-to-calculate-return','role':'orders','source':summed,'sink':returned,'expected':True},
        {'id':'orders-calculate-return-to-caller','role':'orders','source':returned,'sink':caller,'expected':True},
        {'id':'orders-caller-to-total','role':'orders','source':caller,'sink':total,'expected':True}])
    if only_stages:stages=[s for s in stages if s['id'] in only_stages]
    tool.save(out/'frozen-stage-controls.json',{'controls':stages,'scope':'Known positive model qualification; excluded from accuracy scoring'})
    results=[]
    for stage in stages:
        role=stage['role'];graph=graphs[role];target=out/stage['id'];work=target/'work';work.mkdir(parents=True)
        shutil.copytree(graph,work/'graph');shutil.copytree(template/'launcher',work/'launcher')
        runtime=pilot/'flowdist/runtime'/role
        if canonical_rows((runtime/'stmtids.out').read_text().splitlines())!=canonical_rows(rows[role]):raise ValueError('Mismatched statement map')
        mapping=[set(map(int,line.split())) for line in (runtime/'entitystmt.out.branch').read_text().splitlines()]
        _,covered=coverage(runtime/'stmtCoverage1.out',mapping,len(rows[role]))
        for name in ('methodList.out','coveredMethods.txt'):shutil.copyfile(graph.parent/name,work/name)
        shutil.copyfile(graph.parent/'methodList.out',work/'methodsInPair.out')
        (work/'traces').mkdir()
        for file in runtime.glob('Local*.em'):shutil.copyfile(file,work/'traces'/file.name)
        (work/'graph/stmtCoverageOT1.out').write_text(' '.join(map(str,sorted(covered)))+'\n')
        (work/'graph/stmtCoverage1.out').unlink(missing_ok=True)
        (work/'query.txt').write_text(stage['source']+'; '+stage['sink']+'\n')
        arguments=['-Xmx1g','-ea','-cp','/work/launcher:'+tool.CP,
            'FlowDistFieldDecision','/work/query.txt','/work/traces','/work/graph']
        if stream_model and role=='orders':
            shutil.copyfile(stream_model,work/'stream-model.tsv');arguments.append('/work/stream-model.tsv')
        if all_queries:arguments.append('--all-query-matching')
        tool.execute(repo,target,'control',arguments)
        flags=json.loads(re.search(r'FLOWDIST_ORIGINAL_FLAGS=(\{[^\n]+\})',(target/'control.log').read_text())[1])
        results.append(dict(stage,flags=flags,passed=flags['source_nodes']>0 and flags['sink_nodes']>0 and flags['is_local']))
    report={'scope':'Framework stage qualification; not a TP/FP/FN evaluation','controls':results,
            'all_passed':all(r['passed'] for r in results),'passed':sum(r['passed'] for r in results),
            'failed_stages':[r['id'] for r in results if not r['passed']],'accuracy_eligible':False}
    tool.save(out/'result.json',report);print(json.dumps({k:v for k,v in report.items() if k!='controls'},indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for flag in ('repo','pilot','template','orders','carts','out'):parser.add_argument('--'+flag,type=Path,required=True)
    parser.add_argument('--only',nargs='+')
    parser.add_argument('--stream-model',type=Path)
    parser.add_argument('--all-query-matching',action='store_true')
    a=parser.parse_args();qualify(*[getattr(a,k).resolve() for k in ('repo','pilot','template','orders','carts','out')],only_stages=a.only,
        stream_model=a.stream_model.resolve() if a.stream_model else None,all_queries=a.all_query_matching)
