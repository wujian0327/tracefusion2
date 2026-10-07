"""Independent traces for an unobserved control byte and equal-valued sources."""
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from test_gin_byte_provenance import evidence,combine
from go_byte_adapter import decode_function,assembly_rows
from gin_byte_adapter import select_observation
from gin_byte_boundaries import bind
from gin_choice_provenance import individual_unknowns
from gin_byte_provenance import fixtures
from gin_cross_provenance import readiness
from gin_otel_provenance import client
from gin_otel_boundaries import span_chains,read_spans
import gin_byte_capture


def choice_evidence(control=0,use_c=False,**kwargs):
    doc,p=evidence('assign',use_c,**kwargs)
    p['scope']='Independent trace fixture';p['sites']=[s for s in p['sites'] if s['op']!='instruction']
    ir=decode_function(assembly_rows((Path(__file__).parent/'fixtures/go-byte-choice.asm').read_text()))
    for n in ir:
        sid=max(s['id'] for s in p['sites'])+1;n['site']=sid
        arg=n['args'][0] if n['op'] in ('cmp','movzx') else n['args'][1] if n['op']=='test' else None
        snaps={'load':{'address':arg,'length':1}} if arg and arg['kind']=='mem' else {}
        p['sites'].append(dict(id=sid,op='instruction',phase='step',pair=-1,address=n['address'],snapshots=snaps))
    p.update(instructions=ir,entry=ir[0]['address'],event_order=[s['id'] for s in p['sites']],
             runtime_inputs=[dict(register='rdi',length=1)],runtime_input_sites=[n['site'] for n in ir if n['asm'].startswith('CMPB')])
    events=[e for e in doc['events'] if e['op']!='instruction']
    pre=next(e for e in events if e['op']=='work' and e['phase']=='pre')
    post=next(e for e in events if e['op']=='work' and e['phase']=='post')
    pre['registers']['rdi']=0x5000+kwargs.get('offset',0);regs=dict(pre['registers']);dynamic=[];output=bytearray(4)
    src=regs['rcx'] if control else regs['rbx'];dst=regs['rax'];data=b'SAME'
    def emit(index,load=None):
        n=ir[index];e=deepcopy(pre);e.update(site=n['site'],op='instruction',phase='step',registers=dict(regs),values={})
        if load:
            ptr,b=load;e['values']['load']=dict(pointer=ptr,hex=b.hex(),key=f'{ptr:x}:{len(b)}')
        dynamic.append(e)
    emit(0);regs['rdx']=0;emit(1)
    for i in range(5):
        emit(3);emit(4)
        if i==4:break
        emit(5,(regs['rdi'],bytes([control])));emit(6)
        first=13 if control else 7
        emit(first,(dst,bytes(output[:1])));emit(first+1,(src,data[:1]));emit(first+2,(src+i,data[i:i+1]))
        regs['rsi']=data[i];emit(first+3);output[i]=data[i]
        if not control:emit(11)
        emit(17 if control else 12);emit(2);regs['rdx']=i+1
    emit(18);post['registers']=dict(regs)
    at=events.index(pre)+1;events[at:at]=dynamic
    for i,e in enumerate(events):e['sequence']=i;e['timestamp']=i
    doc['events']=events;doc['stats']['submitted']=len(events)
    return doc,p


def project(doc,plan,mode):
    p=select_observation(plan,mode);ids={s['id'] for s in p['sites']};d=deepcopy(doc)
    d['events']=[e for e in d['events'] if e['site'] in ids]
    for i,e in enumerate(d['events']):e['sequence']=i
    d['stats']['submitted']=len(d['events']);return d,p


class ChoiceTests(unittest.TestCase):
    def test_same_boundary_values_different_actual_origins(self):
        projections=[]
        for control in (0,1):
            d,p=choice_evidence(control);full=bind(d,p)
            self.assertEqual(full['status'],'resolved',full)
            self.assertEqual(full['results'][0]['local_sources'],['source:2' if control else 'source:1'])
            sparse,sp=project(d,p,'selective');result=bind(sparse,sp)
            self.assertEqual(result['status'],'resolved',result)
            self.assertEqual(result['results'][0]['provenance']['byte_sources'],full['results'][0]['provenance']['byte_sources'])
            boundary,bp=project(d,p,'boundary');unknown=bind(boundary,bp)
            self.assertEqual(unknown['status'],'unknown');self.assertIn('Missing runtime input observation',unknown['reason'])
            self.assertTrue(all(r['passed'] for r in individual_unknowns(boundary,bp)))
            for e in boundary['events']:e.pop('timestamp')
            projections.append(boundary['events'])
            probes=gin_byte_capture.physical_probes(sp)
            self.assertEqual(sum(s['op']=='instruction' for probe in probes for s in probe['sites']),1)
            self.assertEqual(sum(e['op']=='instruction' for e in sparse['events']),4)
            self.assertTrue(gin_byte_capture.source(sp,1,SimpleNamespace(st_dev=0,st_ino=0)))
        self.assertEqual(*projections,'Boundary values/registers identical; timing excluded, control snapshots differ')

    def test_interleaved_requests_with_distinct_controls(self):
        a,p=choice_evidence(0,ticket=1);b,_=choice_evidence(1,g=0x999,offset=0x10000,ticket=2)
        doc,plan=project(combine([a,b]),p,'selective');result=bind(doc,plan)
        self.assertEqual(result['status'],'resolved',result)
        self.assertEqual([r['local_sources'] for r in result['results']],[['source:1'],['source:2']])

    def test_missing_extra_and_bad_pointer_selected_events(self):
        d,p=choice_evidence();doc,plan=project(d,p,'selective')
        for failure in ('missing','extra','pointer'):
            bad=deepcopy(doc);events=bad['events'];i=next(i for i,e in enumerate(events) if e['op']=='instruction')
            if failure=='missing':events.pop(i)
            elif failure=='extra':events.insert(i,deepcopy(events[i]))
            else:
                v=events[i]['values']['load'];v['pointer']+=1;v['key']=f"{v['pointer']:x}:1"
            for j,e in enumerate(events):e['sequence']=j
            bad['stats']['submitted']=len(events)
            self.assertEqual(bind(bad,plan)['status'],'unknown',failure)

    @unittest.skipUnless(os.environ.get('GIN_CHOICE_BUILD'),'Set GIN_CHOICE_BUILD for native HTTP and actual probe plans')
    def test_native_http_sdk_and_plans(self):
        root=Path(os.environ['GIN_CHOICE_BUILD'])/'build'
        for role in ('upstream','downstream'):
            plan=json.loads((root/role/'plan.json').read_text())
            for mode in ('full','boundary','selective'):
                p=select_observation(plan,mode)
                self.assertTrue(gin_byte_capture.source(p,1,SimpleNamespace(st_dev=0,st_ino=0)))
                if mode=='selective':self.assertEqual(sum(s['op']=='instruction' for s in p['sites']),int(role=='downstream'))
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp);captures={};procs={};logs=[]
            try:
                for role in ('upstream','downstream'):
                    cap=out/role;cap.mkdir();captures[role]=cap;inputs=fixtures(cap)
                    # Distinct native-test source values prove query routing;
                    # the BPF fixture intentionally keeps all source values SAME.
                    for ticket in range(1,9):(inputs/str(ticket)/'B.txt').write_bytes(b'LOCL')
                    upstream=readiness(captures['upstream'],procs['upstream'])['address'] if role=='downstream' else ''
                    log=(cap/'target.stdout').open('w');err=(cap/'target.stderr').open('w');logs.extend([log,err])
                    proc=subprocess.Popen([str(root/role/'gin-byte-target')],stdin=subprocess.PIPE,stdout=log,stderr=err,text=True);procs[role]=proc
                    proc.stdin.write(json.dumps(dict(Inputs=str(inputs),Upstream=upstream,Service=role,TraceFile=str(cap/'spans.jsonl')))+'\n');proc.stdin.close()
                responses=client(captures['downstream'],root/'client/otel-client')
                for proc in procs.values():self.assertEqual(proc.wait(timeout=15),0)
                self.assertEqual(len(span_chains(read_spans(captures))),8)
                for r in responses:
                    expected=b'LOCL' if r['ticket']%4>=2 else b'SAME'
                    self.assertEqual(json.loads(r['body']),dict(result=list(expected)))
            finally:
                for proc in procs.values():
                    if proc.poll() is None:proc.terminate();proc.wait(timeout=10)
                for log in logs:log.close()

if __name__=='__main__':unittest.main()
