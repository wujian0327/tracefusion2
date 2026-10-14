#!/usr/bin/env python3
"""Independently audit the bounded field comparison and index its raw evidence."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re


def read(path):
    return json.loads(path.read_text())


def audit(pilot, comparison):
    contract=read(comparison/'frozen-field-queries.json');report=read(comparison/'comparison.json')
    queries={q['id']:q for q in contract['queries']}
    assert len(queries)==20 and sum(q['expected_dependency'] for q in queries.values())==7
    assert read(pilot/'flowdist/protocol.json')==read(pilot/'tracefusion/protocol.json')
    calls={}
    for mode in ('flowdist','tracefusion'):
        run=read(pilot/mode/'result.json');assert not run['frontend_errors']
        assert run['status']=='business-passed' and all(c['business_passed'] for c in run['cases'])
        calls[mode]=len(run['cases'])
        rows=report['results'][mode];assert {r['id'] for r in rows}==queries.keys() and len(rows)==20
        counts=Counter()
        for row in rows:
            q=queries[row['id']]
            assert all(row[key]==value for key,value in q.items())
            positive=q['expected_dependency'];answer=row['prediction']
            counts['unknown']+=answer is None
            counts['tp']+=positive and answer is True
            counts['fp']+=not positive and answer is True
            counts['tn']+=not positive and answer is False
            counts['fn_including_unknown_positive']+=positive and answer is not True
        summary=report['summary'][mode]
        assert all(summary[key]==value for key,value in counts.items())
        assert summary['exact_rate']==(counts['tp']+counts['tn'])/20
        assert summary['coverage']==1-counts['unknown']/20
        tp,fp,fn=counts['tp'],counts['fp'],counts['fn_including_unknown_positive']
        assert summary['precision']==(tp/(tp+fp) if tp+fp else None)
        assert summary['recall']==tp/(tp+fn)
        assert summary['f1']==2*tp/(2*tp+fp+fn)
    decoded={}
    adapter=read(comparison/'adapter-manifest.json')
    assert adapter['loaded_graph_class_modified'] and adapter['original_jar_unchanged']
    for row in report['results']['flowdist']:
        stage=comparison/row['id'];log=(stage/'statement-query.log').read_text()
        assert not re.search(r'Failed to cast|No GZIP!|Exception in thread|static fallback forbidden',log)
        trace=json.loads(re.search(r'FLOWDIST_DECODED_TRACE=(\{[^\n]+\})',log)[1])
        flags=json.loads(re.search(r'FLOWDIST_ORIGINAL_FLAGS=(\{[^\n]+\})',log)[1])
        assert flags==row['original_flags'] and flags['exercised_nodes']>0 and flags['exercised_edges']>0
        assert trace['all_event_entries_preserved'] and trace['enters']>0 and trace['returns']>0
        assert flags['source_nodes']==1 and flags['sink_nodes']==1 and row['endpoints_observed']
        assert read(stage/'statement-query-stage.json')['exit_code']==0
        patched=stage/'work/launcher/disttaint/DynTransferGraph.class'
        assert hashlib.sha256(patched.read_bytes()).hexdigest()==adapter['patched_class_sha256']
        decoded.setdefault(row['role'],trace);assert decoded[row['role']]==trace
    controls=report['positive_controls'];assert len(controls)==4
    assert all(c['passed'] and c['flags']['is_local'] for c in controls)
    assert not report['controls_in_scored_denominator'] and not report['accuracy_eligible'] and not report['performance_eligible']
    return {'validation_passed':True,'business_calls':calls,'query_count':20,'positive_truths':7,
            'native_positive_controls':4,'native_decoded_events':decoded,'summary':report['summary'],
            'scope':'Field instruction sites aggregated per JVM; not request-instance or cross-process paths',
            'accuracy_eligible':False,'performance_eligible':False}


def checkpoint(pilot, comparison):
    value=audit(pilot,comparison)
    evidence=set(comparison.glob('*.json'))|set(comparison.glob('*.csv'))|set(comparison.glob('*.log'))
    evidence|=set(comparison.glob('*/statement-query*'))
    evidence|=set(comparison.glob('positive-controls/*/control*'))
    evidence|={Path('artifacts/field-access-regressions-20261014.log')}
    for mode in ('flowdist','tracefusion'):
        root=pilot/mode
        evidence|=set(root.glob('*.json'))
        evidence|=set(root.rglob('*.em'))|set(root.rglob('events.jsonl'))|set(root.rglob('*.original.class'))
        if mode=='flowdist':
            for name in ('stmtids.out','entitystmt.out.branch','stmtCoverage1.out'):
                evidence|=set((root/'runtime').rglob(name))
    for role in ('orders','carts','shipping'):
        root=Path('artifacts/flowdist-'+role+'-data-20261014')
        evidence|={root/'manifest.json',root/'work/ServiceGraph/staticVtg.dat',root/'work/ServiceGraph/stmtids.out'}
    evidence|={Path('artifacts/tracefusion-field-sites-v2-20261014')/name for name in ('result.json','tracefusion-service-agent.jar')}
    evidence|={Path('artifacts/boundary-field-sites-v2-20261014')/name for name in ('result.json','boundary-agent.jar')}
    evidence|={Path('artifacts/external-tools/flowdist/tool/FLOWDIST.jar'),Path('artifacts/java-collection-deps/asm-9.7.1.jar'),
               Path('artifacts/java-collection-deps/asm-tree-9.7.1.jar')}
    here=Path(__file__).parent
    sources=[here/name for name in ('audit_field_comparison.py','compare_field_accesses.py','infer_field_access_sites.py',
        'test_field_access_sites.py','FlowDistFieldDecision.java','FlowDistFieldIndexPatch.java','FlowDistFieldAdapterTest.java',
        'FlowDistStatementDecision.java','flowdist_preflight.py','flowdist_service_static.py','infer_service_sources.py',
        'service_model.py','three_method_five.py','tracefusion/ServiceAgent.java','tracefusion/ServiceRecorder.java',
        'boundary/BoundaryAgent.java','boundary/BoundaryRecorder.java')]
    value.update(pilot=str(pilot),comparison=str(comparison),groups=read(comparison/'comparison.json')['groups'],
        query_contract=read(comparison/'frozen-field-queries.json'),
        results=read(comparison/'comparison.json')['results'],
        positive_controls=read(comparison/'comparison.json')['positive_controls'],
        limitations=read(comparison/'comparison.json')['limitations'],
        supersedes={'native_statement_results':['Earlier FlowDist 5/7 aggregate total score','Earlier four reference positive controls',
                                               'artifacts/field-access-query-comparison-20261014'],
                    'reason':'Native consumer failed to cast HashMap to LinkedHashMap and fell back to static graph; no valid dynamic statement accuracy.'},
        adapter=read(comparison/'adapter-manifest.json'),
        source_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
        evidence_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(evidence) if p.is_file()})
    return value


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for flag in ('pilot','comparison','out'):p.add_argument('--'+flag,type=Path,required=True)
    args=p.parse_args();value=checkpoint(args.pilot,args.comparison)
    if args.out.exists():raise ValueError('Refusing to replace checkpoint')
    args.out.write_text(json.dumps(value,indent=2)+'\n')
    print(json.dumps({k:value[k] for k in ('validation_passed','business_calls','query_count','native_positive_controls','summary')},indent=2))
