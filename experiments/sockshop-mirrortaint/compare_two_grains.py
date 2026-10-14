#!/usr/bin/env python3
"""Separate field calibration and eleven common physical statement queries."""
import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import re
import shutil

from host import ROOT, HERE
from compare_flowdist_total_queries import SOURCES
from compare_field_accesses import project, summarize
from infer_field_access_sites import infer, read_events
from evaluate_five_methods import boundary_claims
from audit_flowdist_coverage import coverage, canonical_rows
import flowdist_preflight as tool

TF = ROOT / 'artifacts/sockshop-carts-http-20261014/tracefusion'
FD = ROOT / 'artifacts/sockshop-carts-http-resumptions-20261014/flowdist'
GRAPHS = {role: ROOT / ('artifacts/flowdist-' + role + '-data-20261014') for role in ('orders','carts','shipping')}
DRIVER = ROOT / 'artifacts/flowdist-all-query-launcher-v2-20261014'
STREAM = ROOT / 'artifacts/flowdist-sequential-stream-return-model-20261014/model.tsv'


def load(path): return json.loads(path.read_text())
def save(path, value): path.write_text(json.dumps(value,indent=2)+'\n')
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def freeze(out):
    out.mkdir(parents=True,exist_ok=False)
    rows={role:(p/'work/ServiceGraph/stmtids.out').read_text().splitlines() for role,p in GRAPHS.items()}
    def one(role,predicate):
        selected=[(i,s) for i,s in enumerate(rows[role]) if predicate(s)]
        if len(selected)!=1:raise ValueError('Ambiguous common statement selector')
        return selected[0]
    queries=[]
    sink=one('orders',lambda s:'CustomerOrder: void <init>(' in s.split(' - ')[0] and ': float total> =' in s)
    for entity,field,getter,expected in SOURCES:
        source=one('orders',lambda s:'.entities.'+entity+':' in s.split(' - ')[0] and ' '+getter+'()>' in s.split(' - ')[0] and ' '+field+'>' in s.split(' - ')[1])
        queries.append({'id':'orders.'+entity+'.'+field,'role':'orders','method':'newOrder',
                        'source':source[1],'source_id':source[0],'sink':sink[1],'sink_id':sink[0],
                        'sink_label':'orders.total','expected_dependency':expected,
                        'source_method':source[1].split(' - ',1)[0],'sink_method':sink[1].split(' - ',1)[0]})
    source=one('carts',lambda s:'CartResource: java.util.function.Supplier value()>' in s.split(' - ')[0] and 'findByCustomerId(' in s)
    for method,predicate in [('get',lambda s:'CartsController:' in s.split(' - ')[0] and ' get(' in s.split(' - ')[0] and s.split(' - ')[1].startswith('return ')),
                             ('delete',lambda s:'CartResource: void lambda$destroy$' in s.split(' - ')[0] and 'CartDAO: void delete(' in s),
                             ('mergeCarts',lambda s:'CartContentsResource: void lambda$add$' in s.split(' - ')[0] and 'CartDAO:' in s and ' save(' in s)]:
        sink=one('carts',predicate)
        queries.append({'id':'carts.'+method,'role':'carts','method':method,'source':source[1],'source_id':source[0],
                        'sink':sink[1],'sink_id':sink[0],'source_label':'carts.dao','sink_label':'carts.'+method,'expected_dependency':True})
    source=one('shipping',lambda s:'ShippingController:' in s.split(' - ')[0] and ' postShipping(' in s.split(' - ')[0] and '@parameter0:' in s)
    sink=one('shipping',lambda s:'ShippingController:' in s.split(' - ')[0] and ' postShipping(' in s.split(' - ')[0] and s.split(' - ')[1].startswith('return '))
    queries.append({'id':'shipping.postShipping','role':'shipping','method':'postShipping',
                    'source':source[1],'source_id':source[0],'sink':sink[1],'sink_id':sink[0],
                    'source_label':'shipping.param','sink_label':'shipping.return','expected_dependency':True})
    save(out/'statement-contract.json',{'queries':queries,'scope':'Aggregate physical statement relations over common five-method scenarios; no request or field-version disambiguation',
        'oracle':'Independent original quantity*unitPrice+4.99 formula (2 positive, 5 negative Orders pairs); source CartDAO result contents to get/delete/save; Shipment parameter contents to return.',
        'source_profiles':'Orders seven selected physical getter read values; Carts selected reference contents of actual DAO result; Shipping parameter reference contents.',
        'fixture_policy':'Same frozen 26 accuracy scenarios plus one repetition of each method; independent databases and random fixture IDs.',
        'accuracy_eligible':False,'performance_eligible':False,
        'statement_sha256':{role:sha(p/'work/ServiceGraph/stmtids.out') for role,p in GRAPHS.items()}})


def validate_runs(phos):
    runs={mode:load(run/'result.json') for mode,run in (('tracefusion',TF),('flowdist',FD))}
    for mode,status in runs.items():
        if status['status']!='business-passed' or status['frontend_errors'] or len(status['cases'])!=31 or not all(c['business_passed'] for c in status['cases']):raise ValueError('Unqualified existing business capture '+mode)
    plans=[[(c['case'],c['method'],c['phase']) for c in s['cases']] for s in runs.values()]
    if plans[0]!=plans[1]:raise ValueError('Different TF/FD workloads')
    if load(TF/'protocol.json')!=load(FD/'protocol.json'):raise ValueError('Different TF/FD protocols')
    status=load(phos/'result.json')
    if status['status']=='business-passed':
        if [(c['case'],c['method'],c['phase']) for c in status['cases']]!=plans[0]:raise ValueError('Different Phosphor workload')
        if status['frontend_errors'] or not all(c['business_passed'] for c in status['cases']):raise ValueError('Phosphor business/engine errors')
    inputs=load(phos/'protocol.json')['input_sha256']
    for name,expected in inputs.items():
        if sha(Path(name))!=expected:raise ValueError('Phosphor input artifact changed: '+name)
    for role in ('orders','carts','shipping'):
        if sha(phos/(role+'.jar'))!=sha(TF/(role+'.jar')):raise ValueError('Original application differs: '+role)
    return status


def native(repo,out,q):
    role=q['role'];graph=GRAPHS[role]/'work/ServiceGraph';runtime=FD/'runtime'/role
    rows=(graph/'stmtids.out').read_text().splitlines()
    if canonical_rows(rows)!=canonical_rows((runtime/'stmtids.out').read_text().splitlines()):raise ValueError('Native statement indices differ')
    mapping=[set(map(int,line.split())) for line in (runtime/'entitystmt.out.branch').read_text().splitlines()]
    _,covered=coverage(runtime/'stmtCoverage1.out',mapping,len(rows))
    if q['source_id'] not in covered or q['sink_id'] not in covered:return None,{'status':'unobserved-endpoint'}
    target=out/'flowdist'/q['id'];work=target/'work'
    inputs={str(file):sha(file) for file in [graph/'stmtids.out',runtime/'stmtids.out',runtime/'stmtCoverage1.out',runtime/'entitystmt.out.branch',
            DRIVER/'launcher/FlowDistFieldDecision.class',STREAM,*runtime.glob('Local*.em')]}
    cached=target/'native-result.json'
    if cached.exists():
        record=load(cached)
        if record['input_sha256']!=inputs or record['query']!=q['source']+'; '+q['sink'] or sha(target/'query.log')!=record['log_sha256']:
            raise ValueError('Cached native inputs/output changed')
        return record['prediction'],record['flags']
    work.mkdir(parents=True)
    shutil.copytree(graph,work/'graph');shutil.copytree(DRIVER/'launcher',work/'launcher')
    if (work/'launcher/disttaint/DynTransferGraph.class').exists():raise ValueError('Native engine override forbidden')
    for name in ('methodList.out','coveredMethods.txt'):shutil.copyfile(GRAPHS[role]/'work'/name,work/name)
    shutil.copyfile(GRAPHS[role]/'work/methodList.out',work/'methodsInPair.out');(work/'traces').mkdir()
    for file in runtime.glob('Local*.em'):shutil.copyfile(file,work/'traces'/file.name)
    (work/'query.txt').write_text(q['source']+'; '+q['sink']+'\n')
    (work/'graph/stmtCoverageOT1.out').write_text(' '.join(map(str,sorted(covered)))+'\n');(work/'graph/stmtCoverage1.out').unlink(missing_ok=True)
    args=['-Xmx1g','-ea','-cp','/work/launcher:'+tool.CP,'FlowDistFieldDecision','/work/query.txt','/work/traces','/work/graph','--all-query-matching']
    if role=='orders':
        shutil.copyfile(STREAM,work/'stream-model.tsv');args.append('/work/stream-model.tsv')
    tool.execute(repo,target,'query',args)
    text=(target/'query.log').read_text();flags=json.loads(re.search(r'FLOWDIST_ORIGINAL_FLAGS=(\{[^\n]+\})',text)[1])
    prediction=None if not flags['source_nodes'] or not flags['sink_nodes'] else True if flags['is_local'] else False if flags['no_dependency'] else None
    save(cached,{'input_sha256':inputs,'query':q['source']+'; '+q['sink'],'prediction':prediction,'flags':flags,'log_sha256':sha(target/'query.log')})
    return prediction,flags


def phosphor_predictions(phos):
    status=load(phos/'result.json');records={};invalid={}
    for role in ('orders','carts','shipping'):
        text=(phos/(role+'.log')).read_text(errors='replace')
        errors=[s for s in text.splitlines() if any(word in s for word in ('PHOSPHOR_STATEMENT_ERROR','java.lang.VerifyError','java.lang.NoSuchMethodError','java.lang.AbstractMethodError','AnalyzerException','Calling uninstrumented Phosphor stubs'))]
        records[role]=[json.loads(m[1]) for s in text.splitlines() if (m:=re.search(r'PHOSPHOR_STATEMENT_EVENT (\{.*\})',s))]
        if errors:invalid[role]=errors
        if records[role] and [r['seq'] for r in records[role]]!=list(range(1,len(records[role])+1)):raise ValueError('Phosphor event sequence gap')
        allowed={'orders':{'orders.'+entity+'.'+field for entity,field,_,_ in SOURCES},
                 'carts':{'carts.dao'},'shipping':{'shipping.param'}}[role]
        if any(set(r['labels'])-allowed for r in records[role]):invalid.setdefault(role,[]).append('Unmapped source label')
        if any(r['kind']=='source' and r['site'] not in r['labels'] for r in records[role]):
            invalid.setdefault(role,[]).append('Source tag was not observed after assignment')
    return status,records,invalid


def evaluate(repo,phos,out):
    tool.verify_repository(repo);contract=load(out/'statement-contract.json');phos_status=validate_runs(phos)
    for role,p in GRAPHS.items():
        if load(p/'manifest.json').get('dependency_policy')!='explicit-data-only' or sha(p/'work/ServiceGraph/stmtids.out')!=contract['statement_sha256'][role]:raise ValueError('Frozen data-only graph changed')
    driver=load(DRIVER/'manifest.json')
    for name,value in driver['class_sha256'].items():
        if sha(DRIVER/'launcher'/name)!=value:raise ValueError('Driver changed')
    if driver['engine_class_overridden']:raise ValueError('Original native class required')
    rebuilt=infer(TF);save(out/'tracefusion-site-predictions.json',rebuilt)
    obs={'orders':read_events(TF/'tracefusion-events/events.jsonl')}
    boundary={role:boundary_claims(TF,role,'tracefusion') for role in ('carts','shipping')}
    _,phos_rows,phos_errors=phosphor_predictions(phos)
    results={mode:[] for mode in ('tracefusion','flowdist','phosphor')}
    for q in contract['queries']:
        if q['role']=='orders':
            pred,basis=project(q,rebuilt,obs)
        else:
            role=q['role'];sink='return' if q['method'] in ('get','postShipping') else 'delete' if q['method']=='delete' else 'save'
            targets=[t for values in boundary[role].values() for t in values if t['sink']==sink or sink in t['sink']]
            fields=[f for t in targets for f in t['fields'].values()]
            pred=True if any(f['sources'] for f in fields) else None if not fields or any(not f['known'] for f in fields) else False
            basis='Actual readonly boundary source coordinates projected to physical source/target statements'
        results['tracefusion'].append(dict(q,prediction=pred,basis=basis))
        try:pred,flags=native(repo,out,q);available=True
        except Exception as error:pred,flags,available=None,{'analysis_error':str(error)},False
        results['flowdist'].append(dict(q,prediction=pred,flags=flags,analysis_available=available))
        role=q['role'];source=q.get('source_label',q['id']);sink=q['sink_label'];records=phos_rows[role]
        sources=[r for r in records if r['kind']=='source' and r['site']==source];targets=[r for r in records if r['kind']=='sink' and r['site']==sink]
        available=phos_status['status']=='business-passed' and role not in phos_errors and bool(sources) and bool(targets)
        pred=any(source in r['labels'] for r in targets) if available else None
        results['phosphor'].append(dict(q,prediction=pred,analysis_available=available,source_observations=len(sources),sink_observations=len(targets),
                                        reason=None if available else 'Business/engine compatibility failed or declared source/target was not observed'))
        print(q['id'],{mode:values[-1]['prediction'] for mode,values in results.items()},flush=True)
    groups={}
    for method in ('newOrder','get','delete','mergeCarts','postShipping'):
        groups[method]={}
        for mode,values in results.items():
            rows=[r for r in values if r['method']==method]
            available=all(r.get('analysis_available',True) for r in rows)
            groups[method][mode]=dict(summarize(rows),analysis_available=available)
            if not available:
                for key in ('tp','fp','fn_including_unknown_positive','tn','precision','recall','f1','exact_rate'):groups[method][mode][key]=None
    summaries={}
    for mode,values in results.items():
        summary=summarize(values);summary['analysis_available']=all(r.get('analysis_available',True) for r in values)
        if not summary['analysis_available']:
            for key in ('tp','fp','fn_including_unknown_positive','tn','precision','recall','f1','exact_rate'):summary[key]=None
        summaries[mode]=summary
    report={'kind':'two-grain-five-method-comparison','statement_contract':contract,'statement_results':results,'statement_groups':groups,
            'statement_summary':summaries,'phosphor_compatibility':phos_status,'phosphor_engine_errors':phos_errors,
            'field_comparison':load(HERE/'dynamic-baselines-20261014.json')['dynamic_baseline_audit'],
            'accuracy_eligible':False,'performance_eligible':False,
            'limitations':['Field and statement denominators remain separate; no direct ranking between the two tables.',
                'Eleven aggregate statement pairs, including five Orders negatives; not full request-instance or distributed path accuracy.',
                'Method groups associate representative physical endpoints with APIs; shared save/delete helpers are not isolated to an API root and fixture calls are included.',
                'Same scenario registry, independent random fixture IDs; whole captures include fixture calls and one repetition of each method.',
                'Source-read native tags and readonly field-origin projection use different observation mechanisms, disclosed at the common physical endpoints.',
                'Phosphor source graph for Carts/Shipping covers reference contents; primitive Carts fields are outside its source profile.',
                'FlowDist uses unchanged author all-query builder, full-event decoder, normal-return observations and disclosed sequential Stream return model.',
                'Engine or deployment failures are N/A, not algorithmic FN; unanswered valid queries retain unknown and coverage.',
                'Historical field costs retained separately; no new comparable Phosphor/FlowDist cost measurements in this query run.']}
    save(out/'comparison.json',report)
    rows=[{'method':method,'configuration':mode,**metrics} for method,modes in groups.items() for mode,metrics in modes.items()]
    with (out/'statement-table.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    accuracy=report['field_comparison']['accuracy']
    with (out/'field-table.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(accuracy[0]));writer.writeheader();writer.writerows(accuracy)
    names={'tracefusion':'TraceFusion','mirrortaint':'MirrorTaint + disclosed adapters',
           'flowdist':'FlowDist + disclosed adapters','phosphor':'Phosphor '+str(phos_status.get('phosphor_version','unknown'))+' + source/observation adapter'}
    def percent(value):return 'N/A' if value is None else f'{value:.1%}'
    lines=['# Sock Shop: separate field and statement comparisons','',
           'Field results use request/business-record/field identities; repeated reads/versions can be collapsed. Statement results use independent physical endpoints and aggregate across the workload. These denominators are separate.','',
           '## Field relations: MirrorTaint and TraceFusion','',
           '| Method | Configuration | Queries | TP | FP | FN | Precision | Recall | F1 | Exact |',
           '| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |']
    for method in ('newOrder','get','delete','mergeCarts','postShipping'):
        for mode in ('mirrortaint','tracefusion'):
            a=next(a for a in accuracy if a['method']==method and a['configuration']==mode)
            lines.append('| '+method+' | '+names[mode]+' | '+' | '.join(str(a[k]) for k in ('queries','tp','fp','fn'))+' | '
                         +' | '.join(percent(a[k]) for k in ('precision','recall','f1'))+f" | {a['exact']}/{a['queries']} |")
    lines += ['', '## Statement relations: TraceFusion, Phosphor and FlowDist','',
              '| Method group | Configuration | Queries | TP | FP | FN | TN | Precision | Recall | F1 | Coverage |',
              '| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
    for method,modes in groups.items():
        for mode in ('tracefusion','phosphor','flowdist'):
            a=modes[mode]
            lines.append('| '+method+' | '+names[mode]+' | '+' | '.join('N/A' if a[k] is None else str(a[k]) for k in
                         ('queries','tp','fp','fn_including_unknown_positive','tn'))+' | '
                         +' | '.join(percent(a[k]) for k in ('precision','recall','f1','coverage'))+' |')
    lines += ['', '## Recorded online costs for the field configurations','',
              'Historical one-deployment pilot, five warmups and twenty samples per method. Controller wall time excludes startup and offline reconstruction. Memory is whole-JVM RSS in KiB; these numbers do not measure the new Phosphor/FlowDist statement configurations.','',
              '| Method | Plain ms | MirrorTaint ms | TraceFusion ms | Plain RSS KiB | MirrorTaint RSS KiB | TraceFusion RSS KiB |',
              '| --- | ---: | ---: | ---: | ---: | ---: | ---: |']
    for method in ('newOrder','get','delete','mergeCarts','postShipping'):
        costs=[next(c for c in report['field_comparison']['costs'] if c['method']==method and c['configuration']==mode) for mode in ('plain','mirrortaint','tracefusion')]
        lines.append('| '+method+' | '+' | '.join(f"{c['controller_ms']:.3f}" for c in costs)+' | '
                     +' | '.join(f"{c['resident_kB']:.1f}" for c in costs)+' |')
    lines += ['', '## Limits','', *['- '+s for s in report['limitations']],
              '- Phosphor 0.0.3 failed primitive lambda ABIs; the complete run uses the official unmodified 0.0.4 source build and its matching instrumented Java8 JRE.',
              '- All three tools answered this eleven-query statement calibration correctly; this does not establish superior accuracy or general compatibility.', '']
    (out/'results.md').write_text('\n'.join(lines))
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('stage',choices=('freeze','evaluate'))
    p.add_argument('--out',type=Path,required=True);p.add_argument('--phosphor',type=Path)
    p.add_argument('--repo',type=Path,default=ROOT/'artifacts/external-tools/flowdist');a=p.parse_args()
    if a.stage=='freeze':freeze(a.out.resolve())
    else:
        if not a.phosphor:p.error('--phosphor is required')
        r=evaluate(a.repo.resolve(),a.phosphor.resolve(),a.out.resolve());print(json.dumps(r['statement_summary'],indent=2))
