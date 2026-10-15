#!/usr/bin/env python3
"""Audit original artifacts, independently disassemble the model, and perturb evidence."""
import argparse
import copy
import json
from pathlib import Path
import tempfile
from zipfile import ZipFile

from run_security_leak import evaluate, save, sha, DEPS
from security_field_flow import infer, read_events
from service_model import disassemble, methods, local


def audit_model(run):
    capture=run/'target';events=read_events(capture/'events.jsonl')
    model=next(r for r in events if r['kind']=='model')
    cls=capture/'SecurityLeakLab$Flow.original.class'
    code=methods(disassemble(cls),'SecurityLeakLab$Flow')[model['method']]
    if len(code)!=len(model['instructions']):raise ValueError('Model length differs from javap')
    offsets={r['offset']:i for i,r in enumerate(code)}
    ops={'getfield':180,'putfield':181,'ldc':18,'invokevirtual':182,'invokespecial':183,
         'invokestatic':184,'invokeinterface':185,'ifeq':153,'ifne':154,'goto':167,
         'new':187,'dup':89,'return':177,'pop':87,'aconst_null':1}
    for index,(raw,observed) in enumerate(zip(code,model['instructions'])):
        if observed['site']!=index:raise ValueError('Invalid model site')
        variable=local(raw,'aload');store=local(raw,'astore')
        if variable is not None or store is not None:
            if observed['op']!=(25 if variable is not None else 58) or observed['var']!=(variable if variable is not None else store):raise ValueError('Local operand changed')
            continue
        if ops.get(raw['op'])!=observed['op']:raise ValueError('Opcode changed')
        op=raw['op']
        if op in ('getfield','putfield'):
            reference=raw['comment'].removeprefix('Field ');name,desc=reference.split(':',1)
            if name!=observed['owner']+'.'+observed['name'] or desc!=observed['desc']:raise ValueError('Field operand changed')
        elif op.startswith('invoke'):
            ref=raw['comment'].split(' ',1)[1].replace('"','');name,desc=ref.split(':',1)
            if '.' not in name:name='SecurityLeakLab$Flow.'+name
            if name!=observed['owner']+'.'+observed['name'] or desc!=observed['desc']:raise ValueError('Call operand changed')
        elif op in ('ifeq','ifne','goto'):
            if offsets[int(raw['operand'])]!=observed['target']:raise ValueError('Branch destination changed')
        elif op=='ldc':
            if raw['comment']!='String '+observed['constant']:raise ValueError('Constant changed')
        elif op=='new' and raw['comment']!='class '+observed['type']:raise ValueError('Allocation type changed')
    return len(code)


def audit(out,build):
    result=evaluate(out);manifest=json.loads((build/'manifest.json').read_text());contract=json.loads((out/'contract.json').read_text())
    constructor=methods(disassemble(build/'classes/SecurityLeakLab$Box.class'),'SecurityLeakLab$Box')['<init>()V']
    if [r['op'] for r in constructor]!=['aload_0','invokespecial','return'] or constructor[1]['comment']!='Method java/lang/Object."<init>":()V':
        raise ValueError('Fresh Box constructor has unsupported side effects')
    summaries={};proofs=[]
    for profile,cfg in contract['profiles'].items():
        run=out/profile;deployment=json.loads((run/'deployment.json').read_text())
        if not deployment['all_stopped']:raise ValueError('Own processes not stopped')
        business=json.loads((run/'business.json').read_text())
        cases=contract['controlled'] if profile=='controlled' else contract['cve']
        if {row['id'] for row in business}!={row['id'] for row in cases} or len(business)!=len(cases) or not all(row['business_passed'] for row in business):
            raise ValueError('Incomplete or failed business workload')
        native_count=0
        for role in ('source','target'):
            capture=run/role
            events=read_events(capture/'events.jsonl')
            for row in events:
                if row['kind']!='transformed':continue
                original=capture/(row['class'].replace('/','_')+'.original.class')
                if sha(original)!=row['sha256']:raise ValueError('Original capture class changed')
                if row['class'].startswith('SecurityLeakLab$'):
                    if sha(build/'classes'/(row['class']+'.class'))!=row['sha256']:raise ValueError('Application differs from build')
                else:
                    with ZipFile(DEPS/f"log4j-core-{cfg['version']}.jar") as z:
                        import hashlib
                        if hashlib.sha256(z.read(row['class']+'.class')).hexdigest()!=row['sha256']:raise ValueError('Upstream library class differs')
                    native_count+=1
            proofs.extend(capture.glob('*'))
        instruction_count=audit_model(run)
        rows=read_events(run/'target/events.jsonl');active=set();peak=0
        for row in rows:
            if row['kind']=='enter':active.add(row['frame']);peak=max(peak,len(active))
            if row['kind']=='exit':active.remove(row['frame'])
        if profile=='controlled' and peak!=12:raise ValueError('Twelve business frames did not overlap')
        if profile=='cve-vulnerable' and native_count!=1:raise ValueError('Native JndiLookup hook missing')
        summaries[profile]=dict(result['profiles'][profile]['metrics'],peak_overlapping_frames=peak,
                               independently_verified_instructions=instruction_count)
        proofs.extend(p for p in run.iterdir() if p.is_file())
    # All controls operate on copies; the inference engine never receives the oracle.
    run=out/'controlled';source=read_events(run/'source/events.jsonl');target=read_events(run/'target/events.jsonl')
    checks=[]
    with tempfile.TemporaryDirectory(prefix='tf2-security-audit-') as temporary:
        directory=Path(temporary)
        def predict(s,t):
            for name,rows in (('source',s),('target',t)):
                (directory/(name+'.jsonl')).write_text(''.join(json.dumps(dict(r,seq=i+1))+'\n' for i,r in enumerate(rows)))
            return infer(directory/'source.jsonl',directory/'target.jsonl')
        def rejects(name,s,t,substring):
            try:predict(s,t)
            except ValueError as error:
                if substring not in str(error):raise
                checks.append({'control':name,'passed':True,'rejection':str(error)})
            else:raise AssertionError(name+' accepted')
        changed=copy.deepcopy(target)
        next(r for r in changed if r['kind']=='enter' and r['request_id']=='equal-values-public')['message']='missing-identity'
        answer=next(a for a in predict(source,changed)['answers'] if a['request_id']=='equal-values-public')
        assert answer['disclosure'] is None and answer['origins']==[]
        checks.append({'control':'missing-message-with-equal-values','passed':True,'result':'unknown, no guessed source'})
        reordered=copy.deepcopy(source);send_rows=[i for i,r in enumerate(reordered) if r['kind']=='http-send']
        values=[reordered[i] for i in send_rows][::-1]
        for i,row in zip(send_rows,values):reordered[i]=row
        expected={a['request_id']:a['origins'] for a in infer(run/'source/events.jsonl',run/'target/events.jsonl')['answers']}
        assert {a['request_id']:a['origins'] for a in predict(reordered,target)['answers']}==expected
        checks.append({'control':'source-order-shuffled','passed':True,'result':'all message/property origins unchanged'})
        duplicate=copy.deepcopy(source);duplicate.append(copy.deepcopy(next(r for r in duplicate if r['kind']=='http-send')))
        rejects('duplicate-message-id',duplicate,target,'Duplicate HTTP send')
        changed=copy.deepcopy(target);index=next(i for i,r in enumerate(changed) if r['kind']=='branch');changed.pop(index)
        rejects('missing-branch-observation',source,changed,'Static/runtime instruction mismatch')
        changed=copy.deepcopy(target);next(r for r in changed if r['kind']=='write')['version']+=1
        rejects('field-version-corruption',source,changed,'Field version discontinuity')
        changed=copy.deepcopy(target);next(r for r in changed if r['kind']=='sink-argument')['observed']['value']='FORGED'
        rejects('forged-actual-sink',source,changed,'Actual sink argument differs')
        changed=copy.deepcopy(target);next(r for r in changed if r['kind']=='enter')['wire']='{}'
        rejects('wire-body-corruption',source,changed,'Message body mismatch')
        changed=copy.deepcopy(target);row=next(r for r in changed if r['kind']=='enter' and r['request_id']=='direct-leak');row['request_id']='unrelated-report-label'
        assert next(a for a in predict(source,changed)['answers'] if a['request_id']=='unrelated-report-label')['origins']==expected['direct-leak']
        checks.append({'control':'request-label-not-used-for-provenance','passed':True,'result':'source unchanged'})
        cve=out/'cve-vulnerable'
        changed=read_events(cve/'target/events.jsonl')
        next(row for row in changed if row['kind']=='jndi-lookup')['key']='different-key'
        answer=next(a for a in predict(read_events(cve/'source/events.jsonl'),changed)['answers'] if a['request_id']=='lookup-direct')
        assert answer['unsafe_lookup'] is None
        checks.append({'control':'native-lookup-key-does-not-match-message','passed':True,'result':'unknown, unsupported library relation'})
    save(out/'negative-controls.json',{'checks':checks,'raw_captures_modified':False})
    proofs.extend([out/'contract.json',out/'results.json',out/'results.csv',out/'negative-controls.json',build/'manifest.json',DEPS/'manifest.json'])
    proof_hashes={str(p):sha(p) for p in proofs if p.is_file()}
    value={'validated':True,'profiles':summaries,'negative_controls':checks,'evidence_sha256':proof_hashes}
    save(out/'audit.json',value);return value


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);p.add_argument('--build',type=Path,required=True);a=p.parse_args()
    r=audit(a.out.resolve(),a.build.resolve());print(json.dumps({k:v for k,v in r.items() if k!='evidence_sha256'},indent=2))
