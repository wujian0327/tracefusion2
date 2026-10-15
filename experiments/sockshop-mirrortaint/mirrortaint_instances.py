#!/usr/bin/env python3
"""MirrorTaint common Orders.total query: native tags + disclosed instance binding.

HTTP binding uses W3C concrete call spans and JSON pointers. Native labels are
decoded against actual source observations; no expected-source input enters it.
"""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import resource
import subprocess
import sys
import time
from zipfile import ZipFile, ZIP_DEFLATED

from run_planned_service import ROOT, HERE, load, save, sha
from run_query_planner import JARS
from experiment_environment import java8_target
from transport_context import validate_protocol
from evaluate_distributed_paths import one, fields, http, scored, summary

ROLES = ('orders', 'carts')


def build(out, agent, plans):
    expected = load(HERE/'sources.json')['mirrortaint']['agent_sha256']
    if sha(agent)!=expected:
        raise ValueError('Pinned original MirrorTaint agent required')
    out.mkdir(parents=True, exist_ok=False)
    subprocess.run([sys.executable, str(HERE/'build_integration_adapter.py'), '--agent', str(agent),
                    '--out', str(out/'adapter')], check=True)
    tools = out/'tools'; tools.mkdir()
    sources = [HERE/'CommonHttpInstanceAgent.java', HERE/'W3CTraceContext.java']
    command = ['javac', *java8_target()[1], '-cp', ':'.join(map(str,JARS)), '-d',str(tools),*map(str,sources)]
    result = subprocess.run(command,capture_output=True,text=True)
    (out/'compile.log').write_text(result.stdout+result.stderr)
    if result.returncode:raise RuntimeError('Common instance probe compilation failed')
    jar = out/'common-http-instances.jar'
    with ZipFile(jar,'w',ZIP_DEFLATED) as z:
        z.writestr('META-INF/MANIFEST.MF','Manifest-Version: 1.0\nPremain-Class: CommonHttpInstanceAgent\n\n')
        for p in tools.glob('*.class'):z.write(p,p.name)
        for dep in JARS:
            with ZipFile(dep) as lib:
                for name in lib.namelist():
                    if name.endswith('.class') and name.startswith(('org/objectweb/asm/','com/fasterxml/jackson/')):z.writestr(name,lib.read(name))
    for role in ROLES:
        save(out/(role+'-schema.json'), {'json_schema':load(plans/role/'plan.json')['json_schema']})
    save(out/'build.json', {'original_agent':str(agent),'original_agent_sha256':expected,
                           'adapter_sha256':sha(out/'adapter/integration-adapter.jar'), 'probe_sha256':sha(jar),
                           'source_sha256':{str(p):sha(p) for p in [*sources,*HERE.glob('MirrorTaint*Adapter.java')]},
                           'files_sha256':{str(p.relative_to(out)):sha(p) for p in [jar,out/'adapter/integration-adapter.jar',*[out/(r+'-schema.json') for r in ROLES]]},
                           'dependency_policy':'Original MirrorTaint propagation; disclosed compatibility/stream/thread/logging adapters. Probe only records transport, object identity, field and application write count.'})


def verify(bundle):
    m=load(bundle/'build.json')
    if sha(Path(m['original_agent']))!=m['original_agent_sha256']:raise ValueError('Original agent changed')
    for name,h in m['source_sha256'].items():
        if sha(Path(name))!=h:raise ValueError('Adapter/probe source changed: '+name)
    for name,h in m['files_sha256'].items():
        if sha(bundle/name)!=h:raise ValueError('Adapter/probe binary changed: '+name)


def configure(spec,dest,bundle):
    from run_sockshop_cost import JVM
    verify(bundle)
    agent=Path(load(bundle/'build.json')['original_agent'])
    for role in ROLES:
        cfg=spec['services'][role]
        capture=dest/role;capture.mkdir();capture.chmod(0o777)
        cfg.setdefault('volumes',[]).extend([
            str(bundle/'common-http-instances.jar')+':/tf2/instances.jar:ro',
            str(bundle/(role+'-schema.json'))+':/tf2/schema.json:ro',str(capture)+':/tf2/capture:rw'])
        options=JVM
        if role=='orders':
            cfg['volumes'].extend([str(agent)+':/tf2/mirrorTaint.jar:ro',
                                  str(bundle/'adapter/integration-adapter.jar')+':/tf2/adapter.jar:ro'])
            options+=(' -javaagent:/tf2/adapter.jar=strings -javaagent:/tf2/adapter.jar=streams'
                      ' -javaagent:/tf2/mirrorTaint.jar -javaagent:/tf2/adapter.jar=returns'
                      ' -javaagent:/tf2/adapter.jar=sources -javaagent:/tf2/adapter.jar=fields'
                      ' -javaagent:/tf2/adapter.jar=threads -javaagent:/tf2/adapter.jar=logging'
                      ' -Dtaint.env=remote -Dtaint.app=works.weave.socks -Dtaint.version=instances'
                      ' -Duser.home=/tf2/capture -Dtf2.mt.logging=true -Dtf2.mt.instances=true')
            if load(bundle/'build.json').get('diagnostics')=='quiet-agent-info':
                cfg['volumes'].append(str(bundle/'quiet-diagnostics.jar')+':/tf2/quiet-diagnostics.jar:ro')
                options=options.replace(' -javaagent:/tf2/mirrorTaint.jar',
                    ' -javaagent:/tf2/quiet-diagnostics.jar -javaagent:/tf2/mirrorTaint.jar')
            output=load(bundle/'build.json')
            if output.get('label_format')=='native-source-ids-query-target-v1':
                options+=' -Dtf2.mt.sourceIdsOnly=true -Dtf2.mt.export.target='+output['export_target']
        options+=' -javaagent:/tf2/instances.jar -Dinstance.schema=/tf2/schema.json -Dinstance.events=/tf2/capture/instances.jsonl'
        cfg['environment']['JAVA_OPTS']=options


def protocol_rows(root,mode):
    name='instances.jsonl' if mode=='mirrortaint' else 'events.jsonl'
    result={role:[json.loads(l) for l in (root/role/name).read_text().splitlines()] for role in ROLES}
    for role,rows in result.items():
        if [r['seq'] for r in rows]!=list(range(1,len(rows)+1)):raise ValueError('Sequence gap')
        if sum(r['kind']=='metrics' for r in rows)!=1 or any(r['kind']=='problem' for r in rows):raise ValueError('Incomplete/error capture')
        validate_protocol(rows)
    return result


def native_predictions(root,rows,events=None):
    events=events if events is not None else [json.loads(l) for l in one(root.glob('orders/**/adapted-events.jsonl'),'native MT log').read_text().splitlines()]
    by_id={e['event_id']:e for e in events}
    if len(by_id)!=len(events) or any(not e['available'] or not e['capture_complete'] for e in events):raise ValueError('Incomplete native label evidence')
    rpcs={r['mt_rpc_event_id']:r for r in rows['orders'] if r['kind']=='http-rpc-enter' and r.get('mt_rpc_event_id')}
    writes={}
    for role in ROLES:
        for r in http(rows[role],'write','response'):
            for f in r['fields']:
                key=(r['message'],f['path'])
                if key in writes:raise ValueError('Duplicate server message/property')
                writes[key]=(role,r,f)
    token_index=defaultdict(set)
    for event in events:
        if event['phase']!='rpc-response':continue
        request=by_id[event['rpc_request_event']]
        rpc=rpcs[event['rpc_request_event']]
        if event['thread_id']!=request['thread_id'] or event['method']!=request['method']:raise ValueError('MT RPC scope differs')
        received=one((r for r in http(rows['orders'],'read','response') if r['message']==rpc['message']),'native actual response')
        coordinates={(f['owner'],f['field'],f['version']):f for f in received['fields']}
        for leaf in event['fields'].values():
            coord=(leaf.get('owner'),leaf.get('field'),leaf.get('version'))
            if coord not in coordinates:continue
            f=coordinates[coord]
            if leaf.get('value')!=f['observed'].get('value'):raise ValueError('Native tagged field differs from decoded instance')
            remote=writes.get((rpc['message'],f['path']))
            if remote is None:
                source=('unobserved-server',rpc['message'],f['path'],f['owner'],f['field'],f['version'])
            else:
                role,send,sf=remote
                if sf['observed'].get('value')!=leaf.get('value'):raise ValueError('Wire property differs; never rematch by value')
                source=(role,send['seq'],sf['path'],sf['owner'],sf['field'],sf['version'])
            for token in (leaf.get('tag') or {}).get('A',[]):token_index[token['A']].add(source)
    predictions={}
    for event in events:
        if event['phase']!='sink' or event['method']!='newOrder':continue
        context=event['instance_context'];message=context['message']
        if message in predictions:raise ValueError('Duplicate target invocation')
        target=event['fields'].get('arg#total');known=target is not None and target.get('tag') is not None
        sources=set();unknown=[]
        response=one((r for r in http(rows['orders'],'write','response') if r['message']==message),'actual serialized total target')
        serialized=fields(response).get('/total')
        if not target or not serialized or any(target.get(k)!=serialized.get(k) for k in ('owner','field','version')) or target.get('value')!=serialized['observed'].get('value'):
            known=False;unknown.append({'reason':'target object/field/write-count differs from serialized response'})
        for token in ((target or {}).get('tag') or {}).get('A',[]):
            matches=token_index.get(token['A'],set())
            if len(matches)!=1:unknown.append({'token':token['A'],'bindings':len(matches)});known=False
            else:
                sources.update(matches)
                if any(s[0]=='unobserved-server' for s in matches):
                    known=False;unknown.append({'token':token['A'],'reason':'remote source property missing'})
        predictions[message]={'known':known,'source_keys':[list(s) for s in sorted(sources,key=str)],
                              'sources':[], 'native_target':target,'unknown_labels':unknown,'native_event_id':event['event_id']}
    return predictions


def audit_calibration(trial):
    import copy
    root=trial/'sockshop';rows=protocol_rows(root,'mirrortaint')
    events=[json.loads(l) for l in one(root.glob('orders/**/adapted-events.jsonl'),'MT log').read_text().splitlines()]
    baseline=native_predictions(root,rows,events)
    selected=one((c for c in load(root/'run.json')['cases'] if c['case']=='single'),'single calibration case')
    message=selected['message'];checks={}
    changed=copy.deepcopy(events)
    target=one((e for e in changed if e['phase']=='sink' and e['method']=='newOrder' and e['instance_context']['message']==message),'single target')
    target['fields']['arg#total']['version']+=1
    checks['stale_target_version_returns_unknown']=not native_predictions(root,rows,changed)[message]['known']
    changed=copy.deepcopy(events)
    target=one((e for e in changed if e['phase']=='sink' and e['method']=='newOrder' and e['instance_context']['message']==message),'single target')
    target['fields']['arg#total']['owner']='foreign-object'
    checks['same_value_wrong_target_object_returns_unknown']=not native_predictions(root,rows,changed)[message]['known']
    source_key=baseline[message]['source_keys'][0]
    changed=copy.deepcopy(rows)
    send=one((r for r in changed['carts'] if r['seq']==source_key[1]),'source observation')
    send['fields']=[f for f in send['fields'] if f['path']!=source_key[2]]
    checks['missing_remote_source_returns_unknown']=not native_predictions(root,changed,events)[message]['known']
    changed=copy.deepcopy(events)
    for e in changed:
        if e['phase']=='rpc-response':
            for f in e['fields'].values():
                if f.get('field','').endswith('.quantity'):f['version']=f.get('version',0)+100
    checks['stale_decoded_source_version_returns_unknown']=not native_predictions(root,rows,changed)[message]['known']
    changed=copy.deepcopy(events)
    for e in changed:
        if e['phase']=='rpc-response':
            for f in e['fields'].values():
                if f.get('field','').endswith('.quantity'):f['owner']='same-value-foreign-owner'
    checks['same_value_wrong_source_object_returns_unknown']=not native_predictions(root,rows,changed)[message]['known']
    changed=copy.deepcopy(rows['orders'])
    first=next(r for r in changed if r['kind']=='http-json' and r['phase']=='read' and r['direction']=='response')
    first['request_span_id']='1'*16;first['message']=first['trace_id']+'/'+first['request_span_id']
    try:validate_protocol(changed)
    except ValueError:checks['wrong_call_span_rejected']=True
    else:checks['wrong_call_span_rejected']=False
    cases=load(root/'run.json')['cases'];checks['same_trace_distinct_requests']=len({c['message'].split('/')[0] for c in cases})==1 and len({c['message'] for c in cases})==len(cases)
    checks['all_native_predictions_known']=all(a['known'] for a in baseline.values())
    report={'all_passed':all(checks.values()),'checks':checks,'adapter_scope':'Records and binds actual boundary evidence; native labels determine dependencies. No expected sources are read by native_predictions.'}
    save(trial/'instance-audit.json',report)
    if not report['all_passed']:raise ValueError('Instance calibration audit failed: '+str(checks))
    return report


def evaluate(trial,build,mode,result_out=None):
    started=time.monotonic_ns()
    result_out=result_out or trial
    root=trial/'sockshop';run=load(root/'run.json');rows=protocol_rows(root,mode)
    native_events=None
    if mode=='mirrortaint':
        native_events=[json.loads(l) for l in one(root.glob('orders/**/adapted-events.jsonl'),'native MT log').read_text().splitlines()]
    decoded=time.monotonic_ns()
    graph=None
    if mode=='mirrortaint':
        graph_built=decoded;predictions=native_predictions(root,rows,native_events)
    else:
        from infer_distributed_fields import Reconstruction
        graph=Reconstruction(build,root,list(ROLES),decoded_rows=rows);predictions={}
        graph_built=time.monotonic_ns()
        boundary={'service':'carts','kind':'http-json','phase':'write','direction':'response'}
        for c in run['cases']:
            if c['business_passed'] and c['expected_target']:predictions[c['message']]=graph.query(c['message'],'/total','orders',boundary)
    built=time.monotonic_ns();queries=[];unknown_background={}
    for c in run['cases']:
        if not c['business_passed']:continue
        if not c['expected_target']:
            if c['message'] in predictions or any(r['message']==c['message'] and '/total' in fields(r) for r in http(rows['orders'],'write','response')):
                raise ValueError('Declined order unexpectedly has a total target')
            continue
        fixture=load(root/c['case']/'fixture.json');uri='http://carts/carts/'+fixture['customer_id']+'/items'
        rpc=one((r for r in rows['orders'] if r['kind']=='http-rpc-enter' and r['uri']==uri and r['method']=='GET'),'oracle actual cart request')
        send=one((r for r in http(rows['carts'],'write','response') if r['message']==rpc['message']),'oracle actual cart response')
        sf=fields(send);indices={f['observed']['value']:p.rsplit('/',1)[0] for p,f in sf.items() if p.endswith('/itemId')}
        if set(indices)!=set(fixture['expected_items']):raise ValueError('Independent fixture record identities differ')
        expected=[];nodes=[]
        for ident in fixture['expected_items']:
            for prop in ('quantity','unitPrice'):
                path=indices[ident]+'/'+prop;f=sf[path]
                expected.append(('carts',send['seq'],path,f['owner'],f['field'],f['version']));nodes.append(f)
        answer=predictions.get(c['message'],{'known':False,'source_keys':[],'sources':[]})
        if mode=='tracefusion':
            answer=dict(answer,source_keys=[[*key,graph.nodes[tuple(key)]['owner'],graph.nodes[tuple(key)]['field'],graph.nodes[tuple(key)]['version']] for key in answer['source_keys']])
        queries.append(scored(c['case'],'/total',answer,expected,nodes))
    if graph is not None:
        for n in graph.nodes.values():
            if n.get('unknown'):unknown_background[n['field']]=unknown_background.get(n['field'],0)+1
    report={'mode':mode,'summary':summary(queries),'queries':queries,
            'source_boundary':'Actual Carts JSON response serialization; not database history',
            'instance_key':['service','observation seq','JSON pointer','object identity','field','application write count'],
            'unsupported_queries':'N/A: returned item fields, Shipment and Train Ticket not calibrated for MT here'}
    scored_at=time.monotonic_ns()
    output_root=result_out/'sockshop';output_root.mkdir(parents=True,exist_ok=True)
    save(output_root/'field-results.json',report);ready=time.monotonic_ns()
    save(result_out/'offline.json',{'graph_build_seconds':(built-started)/1e9,'restore_score_export_seconds':(ready-started)/1e9,
                             'phases_seconds':{'decode_and_validate':(decoded-started)/1e9,
                                 'graph_reconstruction':(graph_built-decoded)/1e9,
                                 'query_or_native_origin_restore':(built-graph_built)/1e9,
                                 'oracle_score_and_background_accounting':(scored_at-built)/1e9,
                                 'answer_export':(ready-scored_at)/1e9},
                             'phase_scope':'Same algorithm, predecoded row reuse avoids duplicate JSON parsing. Graph phase includes schema/sequence validation; native mode has no graph. Scores/oracle and exports are separate. This is current-code timing, never retroactive historical timing.',
                             'peak_rss_bytes':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
                             'answers_ready_ns':ready,'summary':report['summary'],'background_unknown':unknown_background})
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('stage',choices=('build','evaluate'))
    p.add_argument('--out',type=Path,required=True);p.add_argument('--agent',type=Path);p.add_argument('--build',type=Path,required=True)
    p.add_argument('--mode',choices=('mirrortaint','tracefusion'),default='mirrortaint');a=p.parse_args()
    if a.stage=='build':build(a.out.resolve(),a.agent.resolve(),a.build.resolve())
    else:print(json.dumps(evaluate(a.out.resolve(),a.build.resolve(),a.mode)['summary'],indent=2))
