"""Independent traces: identical data, independent private selector bytes."""
from copy import deepcopy
from itertools import product
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from test_gin_byte_provenance import evidence,combine
from test_gin_choice_provenance import project
from go_byte_adapter import assembly_rows,decode_function
from gin_byte_adapter import select_observation
from gin_byte_boundaries import bind
from observation_policy import choose_observation


def inputs_evidence(controls=(0,1,1,0),**kwargs):
    d,p=evidence('assign',**kwargs);p['scope']='Independent indexed-input trace'
    p['sites']=[s for s in p['sites'] if s['op']!='instruction']
    ir=decode_function(assembly_rows((Path(__file__).parent/'fixtures/go-byte-inputs.asm').read_text()))
    for n in ir:
        sid=max(s['id'] for s in p['sites'])+1;n['site']=sid
        arg=n['args'][0] if n['op'] in ('cmp','movzx') else n['args'][1] if n['op']=='test' else None
        snaps={'load':{'address':arg,'length':1}} if arg and arg['kind']=='mem' else {}
        p['sites'].append(dict(id=sid,op='instruction',phase='step',pair=-1,address=n['address'],snapshots=snaps))
    p.update(instructions=ir,entry=ir[0]['address'],event_order=[s['id'] for s in p['sites']],
        runtime_inputs=[dict(register='rdi',length=4)],runtime_input_model='indexed-control-bytes-v1',
        runtime_input_ownership='request-private',runtime_input_sites=[ir[i]['site'] for i in (5,6)])
    events=[e for e in d['events'] if e['op']!='instruction']
    pre=next(e for e in events if e['op']=='work' and e['phase']=='pre')
    post=next(e for e in events if e['op']=='work' and e['phase']=='post')
    ptr=0x5000+kwargs.get('offset',0);pre['registers']['rdi']=ptr;regs=dict(pre['registers']);output=bytearray(4);dynamic=[]
    def emit(index,load=None):
        n=ir[index];e=deepcopy(pre);e.update(site=n['site'],op='instruction',phase='step',registers=dict(regs),values={})
        if load:
            address,data=load;e['values']['load']=dict(pointer=address,hex=data.hex(),key=f'{address:x}:{len(data)}')
        dynamic.append(e)
    emit(0);regs['rdx']=0;emit(1)
    for i in range(5):
        emit(3);emit(4)
        if i==4:break
        emit(5,(ptr,bytes([controls[0]])));emit(6,(ptr+i,bytes([controls[i]])));regs['rsi']=controls[i]
        emit(7);emit(8)
        first=14 if controls[i] else 9;src=regs['rcx'] if controls[i] else regs['rbx'];dst=regs['rax'];data=b'SAME'
        emit(first,(dst,bytes(output[:1])));emit(first+1,(src,data[:1]));emit(first+2,(src+i,data[i:i+1]))
        regs['rsi']=data[i];emit(first+3);output[i]=data[i];emit(first+4)
        emit(2);regs['rdx']=i+1
    emit(19);post['registers']=dict(regs)
    at=events.index(pre)+1;events[at:at]=dynamic
    for i,e in enumerate(events):e['sequence']=i;e['timestamp']=i
    d['events']=events;d['stats']['submitted']=len(events);return d,p


class InputsTests(unittest.TestCase):
    def test_all_16_patterns_use_actual_reads_and_preserve_origins(self):
        for controls in product((0,1),repeat=4):
            doc,p=inputs_evidence(controls);decision=choose_observation(p)
            self.assertEqual(decision['mode'],'selective',decision)
            self.assertEqual(decision['instruction_sites'],p['runtime_input_sites'])
            for forbidden in ('entry','entry_replay'):
                with self.assertRaises(ValueError):select_observation(p,forbidden)
            expected=[dict(output_byte=i,origins=[dict(source=f'request:1:source:{2 if value else 1}',byte=i)]) for i,value in enumerate(controls)]
            for mode in ('full','auto'):
                d,plan=project(doc,p,mode);r=bind(d,plan);self.assertEqual(r['status'],'resolved',r)
                prov=r['results'][0]['provenance'];self.assertEqual(prov['byte_sources'],expected)
                samples=[s['runtime_input_evidence'] for s in prov['instruction_steps'] if 'runtime_input_evidence' in s]
                self.assertEqual([s['offset'] for s in samples],[0,0,0,1,0,2,0,3])
                self.assertEqual([s['value'] for s in samples],[x for c in controls for x in (controls[0],c)])
                if mode=='auto':self.assertEqual(sum(e['op']=='instruction' for e in d['events']),8)

    def test_identical_boundaries_and_first_byte_do_not_fix_middle_sources(self):
        boundaries=[];origins=[]
        for controls in ((0,0,0,0),(0,1,1,0)):
            doc,p=inputs_evidence(controls);d,plan=project(doc,p,'boundary')
            result=bind(d,plan);self.assertEqual(result['status'],'unknown')
            self.assertIn('Missing runtime input observation',result['reason'])
            for e in d['events']:e.pop('timestamp')
            boundaries.append(d['events'])
            d,plan=project(doc,p,'auto');origins.append(bind(d,plan)['results'][0]['provenance']['byte_sources'])
        self.assertEqual(*boundaries);self.assertNotEqual(*origins)

    def test_missing_each_read_bad_addresses_and_changed_private_input_rejected(self):
        doc,p=inputs_evidence();d,plan=project(doc,p,'auto')
        indexes=[i for i,e in enumerate(d['events']) if e['op']=='instruction']
        for index in indexes:
            bad=deepcopy(d);bad['events'].pop(index)
            for i,e in enumerate(bad['events']):e['sequence']=i
            bad['stats']['submitted']=len(bad['events'])
            self.assertEqual(bind(bad,plan)['status'],'unknown')
        for failure in ('pointer','repeat','change','ownership','bounds','overlap'):
            bad=deepcopy(d);bp=deepcopy(plan);e=bad['events'][indexes[2]]
            if failure=='pointer':e['values']['load']['pointer']+=1
            elif failure=='repeat':bad['events'].insert(indexes[2],deepcopy(e))
            elif failure=='change':e['values']['load']['hex']='01'
            elif failure=='ownership':bp['runtime_input_ownership']='shared'
            elif failure=='bounds':bp['instructions'][6]['args'][0]['offset']=4
            else:
                work=next(e for e in bad['events'] if e['op']=='work' and e['phase']=='pre')
                work['registers']['rdi']=work['registers']['rax']-2
            for i,e in enumerate(bad['events']):e['sequence']=i
            bad['stats']['submitted']=len(bad['events'])
            result=bind(bad,bp);self.assertEqual(result['status'],'unknown',failure)
            if failure=='bounds':self.assertIn('outside declared region',result['reason'])

    def test_request_interleaving_and_unsupported_inputs(self):
        a,p=inputs_evidence((0,1,1,0),ticket=1);b,_=inputs_evidence((1,0,0,1),g=0x999,offset=0x10000,ticket=2)
        doc,plan=project(combine([a,b]),p,'auto');r=bind(doc,plan)
        self.assertEqual(r['status'],'resolved',r);self.assertEqual(r['concurrency']['migrated_requests'],2)
        self.assertNotEqual(*(row['provenance']['byte_sources'] for row in r['results']))
        for failure in ('call','outside_input','ownership','length','write'):
            bad=deepcopy(p)
            if failure=='call':bad['instructions'][0]['op']='call'
            elif failure=='outside_input':bad['instructions'][6]['args'][0]['base']='r9'
            elif failure=='ownership':bad.pop('runtime_input_ownership')
            elif failure=='length':bad['runtime_inputs'][0]['length']=100
            else:bad['instructions'][12]['args'][1]['base']='rdi'
            self.assertEqual(choose_observation(bad)['status'],'unsupported',failure)

    def test_actual_test_opcode_width_is_not_objdump_mnemonic_width(self):
        _,p=inputs_evidence();n=p['instructions'][7]
        self.assertEqual(n['asm'],'TESTL SI, SI');self.assertEqual(n['code'],'4084f6');self.assertEqual(n['width'],8)


if __name__=='__main__':unittest.main()
