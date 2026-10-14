#!/usr/bin/env python3
"""Audit the first aggregate distributed field pilot against native/raw evidence."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re


def read(path):return json.loads(path.read_text())
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def audit(comparison,fd,tf,qualification,reconstruction):
    report=read(comparison/'comparison.json');contract=read(comparison/'frozen-queries.json')
    assert len(contract['queries'])==3 and [q['expected_dependency'] for q in contract['queries']]==[True,True,False]
    assert not report['flowdist_uuid_or_tf_inference_consumed'] and not report['native_request_instance_resolution_tested']
    assert read(qualification/'result.json')['all_passed'] and len(read(qualification/'result.json')['controls'])==11
    assert read(fd/'protocol.json')==read(tf/'protocol.json')
    business={};image_sets=[];case_shapes=[]
    for mode,run in (('flowdist',fd),('tracefusion',tf)):
        result=read(run/'result.json');assert result['status']=='business-passed' and not result['frontend_errors']
        assert all(c['business_passed'] for c in result['cases']);business[mode]=len(result['cases'])
        spec=read(run/'compose.lock.json')
        image_sets.append({key:value['image'] for key,value in spec['services'].items()})
        case_shapes.append([(c['case'],c.get('method'),c.get('phase'),c.get('expected_target')) for c in result['cases']])
        if mode=='flowdist':assert all('-Dflowdist.http.carts=true' in spec['services'][r]['environment']['JAVA_OPTS'] for r in ('orders','carts'))
        else:
            assert '-Dtracefusion.http.carts=true' in spec['services']['carts']['environment']['JAVA_OPTS']
            assert '-Dtracefusion.http.instances=true' in spec['services']['orders']['environment']['JAVA_OPTS']
        assert len(report['results'][mode])==3 and report['summary'][mode]['queries']==3
        counts=Counter()
        for row,q in zip(report['results'][mode],contract['queries']):
            assert all(row[k]==v for k,v in q.items())
            y=q['expected_dependency'];p=row['prediction'];counts['unknown']+=p is None
            counts['tp']+=y and p is True;counts['fp']+=not y and p is True
            counts['fn_including_unknown_positive']+=y and p is not True;counts['tn']+=not y and p is False
        summary=report['summary'][mode];assert all(summary[k]==v for k,v in counts.items())
        assert summary['exact_rate']==(counts['tp']+counts['tn'])/3 and summary['coverage']==1-counts['unknown']/3
        tp,fp,fn=counts['tp'],counts['fp'],counts['fn_including_unknown_positive']
        assert summary['precision']==tp/(tp+fp) and summary['recall']==tp/(tp+fn)
        assert summary['f1']==2*tp/(2*tp+fp+fn)
    assert image_sets[0]==image_sets[1] and case_shapes[0]==case_shapes[1]
    for row in report['results']['flowdist']:
        root=comparison/row['id']
        for role,key in (('producer','producer_flags'),('receiver','receiver_flags')):
            folder=root/role;raw=(folder/'field-query.log').read_text()
            assert 'FLOWDIST_GRAPH_POLICY=author-full-trace-all-query-matching' in raw
            flags=json.loads(re.search(r'FLOWDIST_ORIGINAL_FLAGS=(\{[^\n]+\})',raw)[1]);assert flags==row[key]
            assert flags['source_nodes']==flags['sink_nodes']==1 and flags['exercised_edges']>0
            assert not (folder/'work/launcher/disttaint/DynTransferGraph.class').exists()
            assert read(folder/'field-query-stage.json')['exit_code']==0
        assert row['producer_flags']['is_local']
        candidate=read(root/'remote/result.json');inspection=read(root/'remote/trace-inspection-stage.json')
        assert candidate['decision']==row['process_candidate'] and inspection['reciprocal_peer_correlation'] and inspection['distinct_server_client_roles']
        for trace in candidate['input_trace_sha256']:
            assert candidate['input_trace_sha256'][trace]==sha(comparison/'method-input/work/traces/test1'/trace)
        prediction=row['receiver_flags']['is_local'] if row['process_candidate']=='candidate-flow' else False
        assert prediction==row['prediction']
    rebuilt=read(reconstruction);assert not rebuilt['labels_consumed'] and not rebuilt['unresolved_http_messages']
    assert len(rebuilt['targets'])==15 and all(t['known'] for t in rebuilt['targets'])
    producer=[json.loads(s) for s in (tf/'boundary-events/carts/events.jsonl').read_text().splitlines()]
    consumers=[json.loads(s) for s in (tf/'tracefusion-events/events.jsonl').read_text().splitlines()]
    byseq={r['seq']:r for r in producer};byreply={r['rpc']:r for r in consumers if r['kind']=='rpc-exit'}
    for edge in rebuilt['http_field_bindings']:
        reply=byreply[edge['message']];path='result#body['+str(edge['item_index'])+']#'+edge['field']
        target=next(f for f in reply['fields'] if f['path']==path)
        for seq in edge['read_sequences']:
            source=byseq[seq];assert source['message_id']==edge['message'] and source['owner']==edge['owner']
            assert source['field']==target['field']==edge['field'] and source['observed']['value']==target['observed']['value']
    evidence=set(comparison.glob('*.json'))|set(comparison.glob('*.csv'))
    for pattern in ('*/remote/*.json','*/remote/*.log','*/producer/*.json','*/producer/*.log','*/receiver/*.json','*/receiver/*.log','method-input/work/traces/test1/*.em'):
        evidence|=set(comparison.glob(pattern))
    evidence|=set(comparison.glob('*/producer/work/traces/*.em'))|set(comparison.glob('*/receiver/work/traces/*.em'))
    evidence|=set(qualification.glob('*.json'))|set(qualification.glob('*/control*'))
    for run in (fd,tf):
        evidence|=set(run.glob('*.json'))|set(run.rglob('*.em'))|set(run.rglob('events.jsonl'))|set(run.rglob('*.original.class'))
    evidence|={reconstruction,Path('artifacts/flowdist-sequential-stream-return-model-20261014/model.json'),Path('artifacts/flowdist-sequential-stream-return-model-20261014/model.tsv')}
    for name in ('flowdist-carts-http-resumptions-20261014','flowdist-carts-http-fullmethods-20261014'):
        folder=Path('artifacts')/name;evidence|={folder/'manifest.json'}|set(folder.glob('*-resume.log'))
        evidence|=set(folder.glob('*-flowdist.jar'))
    for name in ('carts-orders-native-stage-controls-20261014','carts-orders-native-return-controls-20261014','carts-orders-native-qualified-stages-20261014','carts-orders-static-diagnostics-20261014'):
        folder=Path('artifacts')/name;evidence|=set(folder.glob('*.json'))|set(folder.glob('*/*.json'))|set(folder.glob('*/*.log'))
    evidence|={Path('artifacts/flowdist-all-query-launcher-v2-20261014/manifest.json'),Path('artifacts/flowdist-all-query-launcher-v2-20261014/compile.log')}
    evidence|={Path('artifacts/carts-orders-regressions-20261014.log'),Path('artifacts/external-tools/flowdist/tool/FLOWDIST.jar')}
    for role in ('carts','orders'):
        root=Path('artifacts/flowdist-'+role+'-data-20261014')
        evidence|={root/'manifest.json',root/'work/ServiceGraph/staticVtg.dat',root/'work/ServiceGraph/stmtids.out'}
        for name in ('stmtids.out','entitystmt.out.branch','stmtCoverage1.out'):evidence|=set((fd/'runtime'/role).glob(name))
    sources=[Path(__file__).parent/name for name in ('audit_carts_orders.py','compare_carts_orders.py','infer_carts_http_sources.py',
        'flowdist_stream_model.py','FlowDistFieldDecision.java','flowdist/FlowDistStreamModel.java','FlowDistResumeCalls.java',
        'build_flowdist_resumptions.py','refresh_flowdist_http.py','qualify_carts_orders.py','FlowDistHttpConfiguration.java',
        'tracefusion/ServiceRecorder.java','boundary/BoundaryRecorder.java','three_method_five.py',
        'test_carts_http_sources.py','test_flowdist_stream_model.py','test_flowdist_resumptions.py',
        'infer_service_sources.py','service_model.py','infer_field_access_sites.py','flowdist_query.py','flowdist_preflight.py',
        'flowdist/FlowDistHttpClock.java','flowdist/FlowDistSpringHooks.java','build_flowdist_spring_apps.py',
        'build_flowdist_field_launcher.py')]
    return {'validation_passed':True,'scope':report['scope'],'business_calls':business,'comparison':report,
        'query_contract':contract,'framework_qualification':read(qualification/'result.json'),
        'tracefusion_instance_evidence':{'target_orders':15,'source_property_bindings':len(rebuilt['http_field_bindings']),
            'actual_total_source_paths':sum(len(t['sources']) for t in rebuilt['targets']),'unresolved_messages':0},
        'native_algorithm_jar_sha256':sha(Path('artifacts/external-tools/flowdist/tool/FLOWDIST.jar')),
        'flowdist_run':str(fd),'tracefusion_run':str(tf),
        'source_sha256':{str(p):sha(p) for p in sources},
        'evidence_sha256':{str(p):sha(p) for p in sorted(evidence) if p.is_file()},
        'accuracy_eligible':False,'performance_eligible':False}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for flag in ('comparison','flowdist','tracefusion','qualification','reconstruction','out'):p.add_argument('--'+flag,type=Path,required=True)
    a=p.parse_args()
    if a.out.exists():raise ValueError('Refusing to replace checkpoint')
    result=audit(a.comparison,a.flowdist,a.tracefusion,a.qualification,a.reconstruction)
    a.out.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'validation_passed':True,'summary':result['comparison']['summary'],'source_files':len(result['source_sha256']),'evidence_files':len(result['evidence_sha256'])},indent=2))
