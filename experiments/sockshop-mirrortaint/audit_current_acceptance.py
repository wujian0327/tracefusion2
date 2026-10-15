#!/usr/bin/env python3
"""Current two-application acceptance, independent of transport-migration history.

Replays scoring/auditing on copies, reruns Java protocol and image checks, and
binds the receipt to actual captures/build/current audit code. It makes no
unchanged-core or before/after W3C migration claim.
"""
import argparse
import json
from pathlib import Path
import shutil

from run_planned_service import ROOT,HERE,load,save,sha
from run_distributed_paths import check
from compare_w3c_paths import APPS,canonical,wire
from transport_context import validate_protocol


def signature(correctness,build):
    return {'build_sha256':sha(build/'build.json'),
            'capture_sha256':{str(p.relative_to(correctness)):sha(p) for p in sorted(correctness.rglob('*')) if p.is_file()},
            'audit_sources':{str(p.relative_to(ROOT)):sha(p) for p in [Path(__file__),*[HERE/n for n in
             ('compare_w3c_paths.py','evaluate_distributed_paths.py','audit_distributed_paths.py','check_w3c_protocol.py','verify_original_path_images.py','transport_context.py','experiment_environment.py')]]}}


def wire_audit(correctness):
    details={}
    for app,roles in APPS.items():
        clients={};servers={};messages={c['message'] for c in load(correctness/app/'run.json')['cases']}
        if len({m.split('/')[0] for m in messages})!=1:raise ValueError('Same-trace test required')
        for role in roles:
            rows=[json.loads(l) for l in (correctness/app/role/'events.jsonl').read_text().splitlines()]
            validate_protocol(rows)
            if any(r['kind']=='problem' for r in rows):raise ValueError('Collector errors')
            for r in rows:
                if r['kind'] not in ('http-request-context','http-server-context'):continue
                if r.get('wire_traceparent') is None:
                    if r['kind']!='http-server-context' or r['parent_span_id'] is not None or r['span_id']!=r['request_span_id']:
                        raise ValueError('Invalid root invocation')
                    continue
                if wire(r['wire_traceparent'])!=(r['trace_id'],r['request_span_id'],r['trace_flags']):raise ValueError('Wire identity differs')
                if r.get('wire_tracestate')!=r.get('tracestate'):raise ValueError('Wire tracestate differs')
                pool=clients if r['kind']=='http-request-context' else servers
                if r['message'] in pool:raise ValueError('Duplicate invocation')
                pool[r['message']]=(role,r)
            if app=='sockshop' and role=='orders':
                if not any(r.get('class','').endswith('/AsyncExecutionAspectSupport') for r in rows):raise ValueError('Missing async hook')
                if not all(r['parent_message'] in messages for r in rows if r['kind']=='http-rpc-enter'):raise ValueError('Async parent lost')
        if not messages<=servers.keys():raise ValueError('Missing root calls')
        matched=0
        for message,(role,s) in servers.items():
            if message not in clients:continue
            cr,c=clients[message]
            if role==cr or s['parent_span_id']!=c['span_id'] or s['span_id']==c['span_id']:raise ValueError('Invalid cross-service parent')
            matched+=1
        if not matched:raise ValueError('No observed crossing')
        details[app]={'root_calls':len(messages),'matched_cross_service_calls':matched}
    return details


def verify(receipt,correctness,build):
    check(correctness,build)
    r=load(receipt/'current-acceptance.json')
    if r.get('kind')!='current-two-application-acceptance' or not r.get('all_passed'):raise ValueError('Current acceptance failed')
    if r['signature']!=signature(correctness,build):raise ValueError('Current acceptance capture/build/audit hashes differ')
    for name,h in r['audit_evidence_sha256'].items():
        if sha(receipt/name)!=h:raise ValueError('Acceptance audit evidence changed: '+name)
    return r


def run(out,correctness,build):
    check(correctness,build);before=signature(correctness,build)
    out.mkdir(parents=True,exist_ok=False);replay=out/'replay'
    shutil.copytree(correctness,replay)
    from evaluate_distributed_paths import evaluate
    from audit_distributed_paths import audit
    from check_w3c_protocol import check as protocol
    from verify_original_path_images import verify as images
    evaluate(replay,build);audit(replay,build)
    if (replay/'protocol-checks').exists():shutil.rmtree(replay/'protocol-checks')
    protocol(build,replay);images(replay,build)
    for app,n in [('sockshop',198),('trainticket',31)]:
        original=load(correctness/app/'field-results.json');r=load(replay/app/'field-results.json');s=r['summary']
        if s['exact']!=n or s['queries']!=n or s['fp'] or s['fn'] or s['unknown']:raise ValueError('Two-application scoring failed')
        if canonical(r['queries'])!=canonical(original['queries']):raise ValueError('Stored scores differ from replay')
    details=wire_audit(replay)
    if before!=signature(correctness,build):raise ValueError('Original evidence changed during audit')
    evidence={str(p.relative_to(out)):sha(p) for p in sorted(replay.rglob('*')) if p.is_file()}
    save(out/'current-acceptance.json',{'kind':'current-two-application-acceptance','all_passed':True,
         'signature':before,'wire':details,'audit_evidence_sha256':evidence,
         'scope':'Current captures independently re-scored, bytecode/negative controls, actual wire and Java protocol tests, six original image JARs. No unchanged-core or historical migration claim.'})
    verify(out,correctness,build)
    print('Current acceptance passed; original captures unchanged.',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('out','correctness','build'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();run(a.out.resolve(),a.correctness.resolve(),a.build.resolve())
