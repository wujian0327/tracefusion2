#!/usr/bin/env python3
"""Original-business MirrorTaint capability probes; no performance measurement."""
import argparse
from collections import defaultdict
import json
import re
from pathlib import Path
import secrets
import time
from run_planned_service import HERE, ROOT, load, save, sha
import run_response_binding_revision as old
from build_mirror_capability import configure


def read_events(capture,role):
    rows=[json.loads(s) for s in (capture/role/'native-capability.jsonl').read_text().splitlines()]
    assert [r['seq'] for r in rows]==list(range(1,len(rows)+1))
    assert sum(r['kind']=='closed' for r in rows)==1
    problems=[r for r in rows if r['kind']=='problem']
    if problems:raise ValueError('Native export invalid: '+str(problems[:3]))
    from transport_context import validate_protocol
    wire=[json.loads(s) for s in (capture/role/'instances.jsonl').read_text().splitlines()]
    assert [r['seq'] for r in wire]==list(range(1,len(wire)+1))
    assert sum(r['kind']=='metrics' for r in wire)==1 and not any(r['kind']=='problem' for r in wire)
    validate_protocol(wire)
    for target in rows:
        if target['kind']!='target':continue
        message=target['context'].get('message')
        target['wire_fields']=[f for r in wire if r['kind']=='http-json' and r['phase']=='write' and r['direction']=='response' and r['message']==message for f in r['fields']]
    return rows


def native_answer(rows,message,path):
    targets=[r for r in rows if r['kind']=='target' and r['context'].get('message')==message]
    if len(targets)!=1:return {'state':'evidence_invalid','reason':'target absent/ambiguous','target_count':len(targets)}
    target=targets[0]
    serialized=[f for f in target.get('wire_fields',[]) if f['path']==path]
    if len(serialized)!=1:return {'state':'unknown','reason':'actual serialized field instance absent/ambiguous'}
    sf=serialized[0]
    leaves=[f for f in target['fields'] if all(f.get(k)==sf.get(k) for k in ('owner','field','version'))]
    if len(leaves)!=1:return {'state':'unknown','reason':'requested target leaf not uniquely exported'}
    leaf=leaves[0];label_event=target
    if leaf['value']!=sf['observed'].get('value'):return {'state':'evidence_invalid','reason':'serialized instance value differs'}
    if not target['native_available'] or not leaf['tag_present']:
        observed=[(r,f) for r in rows if r['kind']=='native-observation' and r['root']==target['root'] and r['seq']<target['seq'] and r['native_available']
                  for f in r['fields'] if f['tag_present'] and all(f.get(k)==sf.get(k) for k in ('owner','field','version'))]
        if observed:
            if any(f['value']!=sf['observed'].get('value') for r,f in observed) or len({tuple(sorted(f['native_ids'])) for r,f in observed})!=1:
                return {'state':'unknown','reason':'native collector labels for the same field version conflict'}
            label_event,leaf=max(observed,key=lambda rf:rf[0]['seq'])
    index=defaultdict(set)
    for r in rows:
        if r['kind']!='source' or r['root']!=target['root']:continue
        for f in r['fields']:
            for token in f['native_ids']:
                index[token].add((r['call'],r['ordinal'],f['path'],f.get('owner'),f.get('field'),f.get('version')))
    # Manual boundary labels include the concrete call UUID/ordinal and the
    # pinned tagger's creator path. A cached boxed value can expose the same
    # native ID at MANY positions; its first creator is not all those positions.
    # Decode only the fixed, unambiguous DTO/list grammar. Other native IDs keep
    # the conservative observed-instance binding; no expected answer is read.
    source_rows=[r for r in rows if r['kind']=='source' and r['root']==target['root']]
    tokens=set(index)
    for token in tokens:
        creators=[r for r in source_rows if token.startswith('capability#'+r['label']+'#result')]
        if not creators:continue
        if len(creators)!=1:
            index[token]=set();continue
        r=creators[0];tail=token[len('capability#'+r['label']+'#result'):].split(':',1)[0]
        pieces=re.findall(r'#([A-Za-z_$][A-Za-z0-9_$]*)|\[([0-9]+)\]',tail)
        reconstructed=''.join('#'+a if a else '['+b+']' for a,b in pieces)
        if reconstructed!=tail:continue
        creator_path=''.join('/'+(a or b) for a,b in pieces)
        fs=[f for f in r['fields'] if creator_path==f['path'] or creator_path.startswith(f['path']+'/')]
        if not fs:continue
        longest=max(len(f['path']) for f in fs);fs=[f for f in fs if len(f['path'])==longest]
        if len(fs)==1:
            f=fs[0];index[token]={(r['call'],r['ordinal'],f['path'],f.get('owner'),f.get('field'),f.get('version'))}
    actual=set();unbound=[]
    for token in leaf['native_ids']:
        matches=index[token]
        if len(matches)!=1:unbound.append({'token':token,'bindings':[list(v) for v in matches]})
        else:actual.update(matches)
    # An absent tag is NOT evidence of a known empty provenance set.
    known=leaf['tag_present'] and not unbound and label_event['native_available']
    return {'state':'known' if known else 'unknown','sources':[list(v) for v in sorted(actual,key=str)],'unbound':unbound,'native_target':leaf,'root':target['root'],
            'native_label_event_seq':label_event['seq'],'native_label_event_kind':label_event['kind']}


def create(out,base,bundle):
    out.mkdir(parents=True,exist_ok=False)
    seal=load(HERE/'capability-comparison-62-20261020.json')
    q=next(q for q in seal['queries'] if q['id']=='sockshop-carts-get-customerId')
    previous=ROOT/'artifacts/call-lifecycle-revision-20261020/cart-create-guard'
    prior=load(previous/'capture/run.json');uid=prior['cases'][0]['response']['customerId']
    capture=out/'capture';capture.mkdir()
    spec=old.spec_for('tracefusion',capture,base,1,'768m')
    spec['services']={k:v for k,v in spec['services'].items() if k in ('carts','carts-db')}
    spec['services']['carts']['ports']=['127.0.0.1:19681:80']
    spec['networks']={'default':{'ipam':{'config':[{'subnet':'10.254.246.0/24'}]}}}
    configure(spec,capture,base,bundle,q);save(capture/'compose.json',spec)
    save(out/'protocol.json',{'query':q,'counterpart':str(previous),'counterpart_checks_sha256':sha(previous/'checks.json'),'requests':prior['cases'],'same_input_customerId':uid,'fresh_database':True,'business_jar_sha256':sha(base/'carts/original.jar'),'native_bundle_sha256':sha(bundle/'build.json'),'oracle':'Original CartResource.lambda$value$24 creates/saves then invokes value().get() again. First request returns SECOND repository read, subsequent request FIRST. Historical argument-zero expectation is preserved but corrected here. Native labels do not decide expected origins.'})
    dep=old.Deployment(argparse.Namespace(project='tf2-mt-cap-'+secrets.token_hex(5)),capture,capture/'compose.json')
    run={'status':'failed','project':dep.args.project,'roles':['carts'],'cases':[]}
    try:
        dep.compose('up','-d','--pull','never',timeout=180);cl=old.Client(capture);deadline=time.monotonic()+180
        while time.monotonic()<deadline:
            try:cl.request('GET','http://127.0.0.1:19681/health',label='readiness');break
            except Exception:time.sleep(2)
        else:raise ValueError('Original Cart readiness failed')
        for i,c in enumerate(prior['cases']):
            cd=capture/('request-'+str(i));cd.mkdir();client=old.Client(cd)
            trace,span=c['message'].split('/');client.headers={'traceparent':'00-'+trace+'-'+span+'-01','tracestate':'research=capability'}
            response=client.request('GET','http://127.0.0.1:19681/carts/'+uid,label='target-query');assert response==c['response']
            run['cases'].append({**c,'response':response})
        dep.compose('stop','-t','20','carts',timeout=40);run['status']='business-completed'
    finally:old.cleanup(dep,run,capture)
    rows=read_events(capture,'carts');results=[]
    tf=load(previous/'checks.json')['checks']
    for i,c in enumerate(run['cases']):
        answer=native_answer(rows,c['message'],'/customerId')
        target=next(r for r in rows if r['kind']=='target' and r['context'].get('message')==c['message'])
        source_rows=[r for r in rows if r['kind']=='source' and r['root']==target['root'] and '.findByCustomerId(' in r['call']]
        assert len(source_rows)==(2 if i==0 else 1)
        s=source_rows[-1];p='/0/customerId';fields=[f for f in s['fields'] if f['path']==p];assert len(fields)==1
        f=fields[0];assert f['value']==uid
        expected={(s['call'],s['ordinal'],p,f.get('owner'),f.get('field'),f.get('version'))}
        exact=answer['state']=='known' and {tuple(v) for v in answer['sources']}==expected
        results.append({'query':q['id'],'input':'first-create' if i==0 else 'second-read','message':c['message'],'target':'/customerId','tf_state':'known_correct' if tf[i]['known'] else 'unknown','baseline_state':'known_correct' if exact else 'known_wrong' if answer['state']=='known' else answer['state'],'baseline_answer':answer,'expected':[list(v) for v in expected]})
    save(out/'results.json',{'scope':'Two concrete matched targets; calibration, not complete 62-family evaluation','results':results,'baseline_correct_tf_unanswered':[r for r in results if r['baseline_state']=='known_correct' and r['tf_state']!='known_correct']})
    print(json.dumps(results,ensure_ascii=False,indent=2),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);p.add_argument('--base',type=Path,required=True);p.add_argument('--bundle',type=Path,required=True);a=p.parse_args();create(a.out.resolve(),a.base.resolve(),a.bundle.resolve())
