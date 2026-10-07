"""Independent execution traces for private control updates between bytes."""
from copy import deepcopy
from pathlib import Path
import json
import tempfile
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from test_gin_byte_provenance import evidence,combine
from go_byte_adapter import decode_function,assembly_rows
from gin_byte_adapter import select_observation
from gin_byte_boundaries import bind
from observation_policy import choose_observation
from test_gin_cross_provenance import evidence as cross_evidence,TRACE,OTHER
from test_gin_otel_provenance import spans
from gin_cross_boundaries import bind_service
from gin_otel_boundaries import stitch_otel
from gin_otel_compare import comparison_signature


def toggle_evidence(initial=0,**kwargs):
    d,p=evidence('assign',**kwargs);p['scope']='Synthetic control-update fixture'
    p['sites']=[s for s in p['sites'] if s['op']!='instruction']
    ir=decode_function(assembly_rows((Path(__file__).parent/'fixtures/go-byte-toggle.asm').read_text()))
    for n in ir:
        sid=max(s['id'] for s in p['sites'])+1;n['site']=sid
        arg=n['args'][0] if n['op'] in ('cmp','movzx') else n['args'][1] if n['op']=='test' else None
        snaps={'load':{'address':arg,'length':1}} if arg and arg['kind']=='mem' else {}
        p['sites'].append(dict(id=sid,op='instruction',phase='step',pair=-1,address=n['address'],snapshots=snaps))
    runtime=[n['site'] for n in ir if n['op'] in ('cmp','movzx') and n['args'][0].get('base')=='rdi']
    p.update(instructions=ir,entry=ir[0]['address'],event_order=[s['id'] for s in p['sites']],
        runtime_inputs=[dict(register='rdi',length=1)],runtime_input_ownership='request-private',
        runtime_state_model='xor-control-byte-v1',runtime_input_sites=runtime,
        runtime_update_sites=[ir[4]['site']])
    next(s for s in p['sites'] if s['op']=='work' and s['phase']=='post')['snapshots']['control']=dict(pointer='rdi',length=1)
    events=[e for e in d['events'] if e['op']!='instruction'];pre=next(e for e in events if e['op']=='work' and e['phase']=='pre')
    post=next(e for e in events if e['op']=='work' and e['phase']=='post')
    ptr=0x5000+kwargs.get('offset',0);pre['registers']['rdi']=ptr;regs=dict(pre['registers']);output=bytearray(4);value=initial;dynamic=[]
    def snapshot(address,data):return dict(pointer=address,hex=data.hex(),key=f'{address:x}:{len(data)}')
    def emit(index,load=None):
        n=ir[index];e=deepcopy(pre);e.update(site=n['site'],op='instruction',phase='step',registers=dict(regs),values={})
        if load:e['values']['load']=snapshot(*load)
        dynamic.append(e)
    emit(0);regs['rdx']=0;emit(1)
    for i in range(5):
        emit(6);emit(7)
        if i==4:break
        emit(8,(ptr,bytes([value])));emit(9)
        first=15 if value else 10;src=regs['rcx'] if value else regs['rbx'];dst=regs['rax'];data=b'SAME'
        emit(first,(dst,bytes(output[:1])));emit(first+1,(src,data[:1]));emit(first+2,(src+i,data[i:i+1]))
        regs['rsi']=data[i];emit(first+3);output[i]=data[i];emit(first+4)
        emit(2,(ptr,bytes([value])));regs['rsi']=value;emit(3);regs['rsi']^=1
        emit(4);value=regs['rsi'];emit(5);regs['rdx']=i+1
    emit(20);post['registers']=dict(regs);post['values']['control']=snapshot(ptr,bytes([value]))
    events[events.index(pre)+1:events.index(pre)+1]=dynamic
    for i,e in enumerate(events):e['sequence']=i;e['timestamp']=i
    d['events']=events;d['stats']['submitted']=len(events);return d,p


def project(d,p,mode):
    plan=select_observation(p,mode);ids={s['id'] for s in plan['sites']};doc=deepcopy(d)
    doc['events']=[e for e in doc['events'] if e['site'] in ids]
    if plan['observation_mode']=='entry_replay':
        # Independently specified immutable initial state in a synthetic trace;
        # no claim this additional entry event was captured on a host.
        snap=next(e['values']['load'] for e in d['events'] if e['site'] in p['runtime_input_sites'])
        next(e for e in doc['events'] if e['op']=='instruction')['values']['control']=deepcopy(snap)
    for i,e in enumerate(doc['events']):e['sequence']=i
    doc['stats']['submitted']=len(doc['events']);return doc,plan


class ToggleTests(unittest.TestCase):
    def test_alternating_origins_survive_http_and_sdk_stitching(self):
        for initial in (0,1):
            upstream,up=cross_evidence('upstream',trace=OTHER);up['scope']='synthetic upstream'
            downstream,dp=cross_evidence('downstream');toggle,tp=toggle_evidence(initial)
            dp['sites']=[s for s in dp['sites'] if s['op']!='instruction'];mapping={}
            for spec in tp['sites']:
                if spec['op']!='instruction':continue
                sid=max(s['id'] for s in dp['sites'])+1;mapping[spec['id']]=sid
                dp['sites'].append(dict(spec,id=sid))
            for key in ('instructions','entry','runtime_inputs','runtime_input_ownership','runtime_state_model','scope'):
                dp[key]=deepcopy(tp[key])
            for n in dp['instructions']:n['site']=mapping[n['site']]
            dp['runtime_input_sites']=[mapping[s] for s in tp['runtime_input_sites']]
            dp['runtime_update_sites']=[mapping[s] for s in tp['runtime_update_sites']]
            dp['event_order']=[s['id'] for s in dp['sites']];dp['trace_mode']='otel'
            next(s for s in dp['sites'] if s['op']=='work' and s['phase']=='post')['snapshots']['control']=dict(pointer='rdi',length=1)
            start=next(i for i,e in enumerate(downstream['events']) if e['op']=='work' and e['phase']=='pre')
            end=next(i for i,e in enumerate(downstream['events']) if e['op']=='work' and e['phase']=='post')
            body=[deepcopy(e) for e in toggle['events'] if e['op'] in ('work','instruction')]
            for e in body:
                e['pid']=20
                if e['op']=='instruction':e['site']=mapping[e['site']]
            downstream['events'][start:end+1]=body
            for i,e in enumerate(downstream['events']):
                e['sequence']=i;e['timestamp']=i
                if e['op']=='source' and e['phase']=='pre':e['values'].pop('trace',None)
                if e['op']=='http_header' and e['phase']=='pre':e['values']['trace']['hex']=OTHER.encode().hex()
            downstream['stats']['submitted']=len(downstream['events'])
            signatures=[]
            for mode in ('full','selective','auto'):
                u,uplan=project(upstream,up,mode);d,dplan=project(downstream,dp,mode)
                result=stitch_otel(bind_service(u,uplan),bind_service(d,dplan),spans())
                self.assertEqual(result['status'],'resolved',result)
                with tempfile.TemporaryDirectory() as tmp:
                    root=Path(tmp);cap=root/'downstream/capture';cap.mkdir(parents=True)
                    (cap/'client-responses.json').write_text(json.dumps([dict(trace=TRACE,ticket=1)]))
                    (root/'joined.json').write_text(json.dumps(result));signature=comparison_signature(root)
                expected=[[[('downstream' if initial^(i%2) else 'upstream'),'1',('B.txt' if initial^(i%2) else 'A.txt'),i]] for i in range(4)]
                self.assertEqual(signature[0]['byte_sources'],expected);signatures.append(signature)
            self.assertEqual(signatures[0],signatures[1]);self.assertEqual(signatures[0],signatures[2])

    def test_alternating_byte_origins_and_control_versions(self):
        for initial in (0,1):
            d,p=toggle_evidence(initial)
            decision=choose_observation(p);self.assertEqual(decision['mode'],'entry_replay',decision)
            with self.assertRaises(ValueError):select_observation(p,'entry')
            for mode in ('full','selective','auto'):
                doc,plan=project(d,p,mode);result=bind(doc,plan);self.assertEqual(result['status'],'resolved',result)
                prov=result['results'][0]['provenance']
                expected=[dict(output_byte=i,origins=[dict(source='request:1:source:2' if initial^(i%2) else 'request:1:source:1',byte=i)]) for i in range(4)]
                self.assertEqual(prov['byte_sources'],expected)
                self.assertEqual([(u['before'],u['after']) for u in prov['runtime_control_updates']],[(initial^(i%2),initial^((i+1)%2)) for i in range(4)])
                self.assertEqual(prov['final_runtime_control'],initial)
                if mode=='auto':
                    self.assertEqual(sum(e['op']=='instruction' for e in doc['events']),1)
                    comparisons=[s for s in prov['instruction_steps'] if s['address']==p['instructions'][8]['address']]
                    self.assertEqual([s['runtime_input_evidence']['version'] for s in comparisons],list(range(4)))
            doc,plan=project(d,p,'boundary');self.assertEqual(bind(doc,plan)['status'],'unknown')

    def test_interleaved_requests_do_not_share_control_state(self):
        a,p=toggle_evidence(0,ticket=1);b,_=toggle_evidence(1,g=0x999,offset=0x10000,ticket=2)
        # Build request-specific entry snapshots before interleaving.
        a,plan=project(a,p,'auto');b,_=project(b,p,'auto');result=bind(combine([a,b]),plan)
        self.assertEqual(result['status'],'resolved',result)
        self.assertEqual([r['provenance']['final_runtime_control'] for r in result['results']],[0,1])

    def test_unknown_update_or_new_input_refuses_optimization(self):
        _,p=toggle_evidence()
        for change in ('load','constant','operator','partial_block','ownership'):
            bad=deepcopy(p)
            if change=='load':bad['instructions'][2]['args'][0]['base']='r9'
            elif change=='constant':bad['instructions'][3]['args'][0]['value']=256
            elif change=='operator':bad['instructions'][3]['op']='add'
            elif change=='partial_block':bad['instructions'][1]['target']=bad['instructions'][3]['address']
            else:bad.pop('runtime_input_ownership')
            self.assertEqual(choose_observation(bad)['status'],'unsupported',change)

    def test_bad_observations_or_exit_state_are_unknown(self):
        d,p=toggle_evidence()
        for mode in ('full','selective','auto'):
            for change in ('final','sample','missing'):
                doc,plan=project(d,p,mode)
                if change=='final':next(e for e in doc['events'] if e['op']=='work' and e['phase']=='post')['values']['control']['hex']='01'
                elif change=='sample':
                    if mode=='auto':e=next(e for e in doc['events'] if e['op']=='instruction');key='control'
                    else:e=next(e for e in doc['events'] if e['site'] in p['runtime_input_sites']);key='load'
                    e['values'][key]['hex']='01'
                else:
                    i=next(i for i,e in enumerate(doc['events']) if e['op']=='instruction');doc['events'].pop(i)
                    for i,e in enumerate(doc['events']):e['sequence']=i
                    doc['stats']['submitted']=len(doc['events'])
                self.assertEqual(bind(doc,plan)['status'],'unknown',(mode,change))

if __name__=='__main__':unittest.main()
