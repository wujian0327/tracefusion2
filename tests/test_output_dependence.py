"""Check final-origin certificates against independently emulated machine code."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from test_gin_choice_provenance import choice_evidence,project
from test_gin_byte_provenance import evidence,combine
from go_byte_adapter import assembly_rows,decode_function,REGISTERS
from gin_byte_boundaries import bind
from gin_byte_adapter import select_observation
from observation_policy import choose_observation
from output_dependence import analyze_output_dependence,certify_output_projection
try:
    import unicorn as uc
    from unicorn import x86_const as x86
except ImportError:
    uc=None


def copy_plan(variant):
    _,p=choice_evidence();p['observation_target']='final-byte-origins-v1'
    name='choice' if variant=='none' else variant if variant.startswith('correlated') else 'kill-'+variant
    p['sites']=[s for s in p['sites'] if s['op']!='instruction']
    ir=decode_function(assembly_rows((Path(__file__).parent/'fixtures'/('go-byte-'+name+'.asm')).read_text()))
    for n in ir:
        sid=max(s['id'] for s in p['sites'])+1;n['site']=sid
        arg=n['args'][0] if n['op'] in ('cmp','movzx') else n['args'][1] if n['op']=='test' else None
        snapshots={'load':dict(address=arg,length=1)} if arg and arg['kind']=='mem' else {}
        p['sites'].append(dict(id=sid,address=n['address'],op='instruction',phase='step',pair=-1,snapshots=snapshots))
    p.update(instructions=ir,entry=ir[0]['address'],event_order=[s['id'] for s in p['sites']],
             runtime_input_sites=[n['site'] for n in ir if n['op']=='cmp' and n['args'][0]['kind']=='mem'])
    return p


def executed(variant,control,**kwargs):
    doc,_=evidence('assign',**kwargs);p=copy_plan(variant)
    events=[e for e in doc['events'] if e['op']!='instruction']
    pre=next(e for e in events if e['op']=='work' and e['phase']=='pre');post=next(e for e in events if e['op']=='work' and e['phase']=='post')
    ptr=0x5000+kwargs.get('offset',0);pre['registers']['rdi']=ptr
    engine=uc.Uc(uc.UC_ARCH_X86,uc.UC_MODE_64)
    offset=kwargs.get('offset',0);engine.mem_map(0x1000+offset,0xa000)
    for e in events:
        if e['op']=='source' and e['phase']=='post':
            v=e['values']['value'];engine.mem_write(v['pointer'],bytes.fromhex(v['hex']))
    v=pre['values']['dst'];engine.mem_write(v['pointer'],bytes.fromhex(v['hex']));engine.mem_write(ptr,bytes([control]))
    by_address={n['address']:n for n in p['instructions']};start=p['entry']&~4095
    engine.mem_map(start,0x2000)
    for n in p['instructions']:engine.mem_write(n['address'],bytes.fromhex(n['code']))
    registers={r:getattr(x86,'UC_X86_REG_'+r.upper()) for r in REGISTERS}
    for r,identifier in registers.items():engine.reg_write(identifier,pre['registers'][r])
    dynamic=[]
    def hook(machine,address,size,data):
        n=by_address[address];registers_now={r:machine.reg_read(i) for r,i in registers.items()}
        e=deepcopy(pre);e.update(site=n['site'],op='instruction',phase='step',registers=registers_now,values={})
        spec=next(s for s in p['sites'] if s['id']==n['site'])
        if spec['snapshots']:
            arg=spec['snapshots']['load']['address']
            address=registers_now[arg['base']]+(registers_now[arg['index']]*arg['scale'] if arg.get('index') else 0)+arg['offset']
            e['values']['load']=dict(pointer=address,hex=bytes(machine.mem_read(address,1)).hex(),key=f'{address:x}:1')
        dynamic.append(e)
        if n['op']=='ret':machine.emu_stop()
    engine.hook_add(uc.UC_HOOK_CODE,hook);engine.emu_start(p['entry'],start+0x2000,count=256)
    assert dynamic[-1]['site']==next(n['site'] for n in p['instructions'] if n['op']=='ret')
    post['registers']={r:engine.reg_read(i) for r,i in registers.items()}
    assert bytes(engine.mem_read(pre['registers']['rax'],4))==b'SAME'
    at=events.index(pre)+1;events[at:at]=dynamic
    for i,e in enumerate(events):e['sequence']=i;e['timestamp']=i
    doc['events']=events;doc['stats']['submitted']=len(events)
    return doc,p


class OutputProofTests(unittest.TestCase):
    def test_backward_last_definitions_keep_partial_dependencies(self):
        for variant,varying,killed in [('full',[],4),('partial',[0,1],2),('none',[0,1,2,3],0)]:
            p=copy_plan(variant);r=analyze_output_dependence(p)
            self.assertEqual(r['varying_output_bytes'],varying)
            self.assertEqual([len(path['overwritten_writes']) for path in r['paths']],[killed,killed])
            choice=choose_observation(p);self.assertEqual(choice['mode'],'output' if variant=='full' else 'entry',choice)
            if varying:
                with self.assertRaises(ValueError):select_observation(p,'output')

    def test_unknown_effects_and_unsafe_flag_partitions_refuse_proof(self):
        p=copy_plan('full')
        for change in ('call','shared','store','branch','bound','comparison','input'):
            bad=deepcopy(p)
            if change=='call':bad['instructions'][0]['op']='call'
            elif change=='shared':bad['runtime_input_ownership']='shared'
            elif change=='store':next(n for n in bad['instructions'] if n['op']=='mov')['args'][1]['base']='rbx'
            elif change=='branch':next(n for n in bad['instructions'] if n['op']=='jne')['op']='js'
            elif change=='bound':bad['max_steps']=3
            elif change=='comparison':next(n for n in bad['instructions'] if n['op']=='cmp' and n['args'][0]['kind']=='mem')['args'][1]['value']=1
            else:next(n for n in bad['instructions'] if n['op']=='movzx')['args'][0]['base']='r9'
            with self.assertRaises((ValueError,KeyError),msg=change):certify_output_projection(bad)

    def test_rewriting_from_old_output_does_not_kill_its_dependencies(self):
        p=copy_plan('full')
        last_load=next(n for n in reversed(p['instructions']) if n['op']=='movzx')
        last_load['args'][0]['base']='rax'  # dst[i] = dst[i], rather than fresh src[i]
        result=analyze_output_dependence(p)
        self.assertEqual(result['varying_output_bytes'],[0,1,2,3])
        with self.assertRaises(ValueError):certify_output_projection(p)

    @unittest.skipUnless(uc,'Unicorn is required for independent machine execution')
    def test_full_and_reduced_match_for_unsigned_control_classes(self):
        for variant in ('full','partial','none'):
            for control in (0,1,127,128,255):
                d,p=executed(variant,control);full=bind(d,p);self.assertEqual(full['status'],'resolved',full)
                mode='output' if variant=='full' else 'entry';doc,plan=project(d,p,mode);r=bind(doc,plan)
                self.assertEqual(r['status'],'resolved',r)
                prov=r['results'][0]['provenance']
                self.assertEqual(prov['byte_sources'],full['results'][0]['provenance']['byte_sources'])
                expected=[dict(output_byte=i,origins=[dict(source='request:1:source:'+str(1 if control==0 or variant=='full' or variant=='partial' and i>=2 else 2),byte=i)]) for i in range(4)]
                self.assertEqual(prov['byte_sources'],expected)
                if mode=='output':
                    self.assertEqual(prov['instruction_steps'],[]);self.assertIsNone(prov['source_versions']);self.assertIsNone(prov['total_writes'])
                    self.assertEqual(prov['execution_history'],'not_reconstructed')
                    self.assertEqual(sum(e['op']=='instruction' for e in doc['events']),0)

    @unittest.skipUnless(uc,'Unicorn is required for independent machine execution')
    def test_certificate_and_runtime_identity_tampering_are_unknown(self):
        d,p=executed('full',1);doc,plan=project(d,p,'output')
        for case in ('certificate','ir','alias','result','exit','extra','target'):
            bad=deepcopy(doc);bp=deepcopy(plan)
            if case=='certificate':bp['output_projection']['projection'][0][1]='aux'
            elif case=='ir':next(n for n in reversed(bp['instructions']) if n['op']=='cmp')['args'][1]['value']=99
            elif case=='alias':next(e for e in bad['events'] if e['op']=='work' and e['phase']=='pre')['registers']['rdi']=0x1000
            elif case=='result':next(e for e in bad['events'] if e['op']=='json' and e['phase']=='pre')['values']['value']['hex']='00000000'
            elif case=='exit':next(e for e in bad['events'] if e['op']=='work' and e['phase']=='post')['registers']['rax']+=1
            elif case=='target':bp.pop('observation_target')
            else:
                extra=next(e for e in d['events'] if e['op']=='instruction');bad['events'].insert(8,deepcopy(extra))
                for i,e in enumerate(bad['events']):e['sequence']=i
                bad['stats']['submitted']=len(bad['events'])
            self.assertEqual(bind(bad,bp)['status'],'unknown',case)

    @unittest.skipUnless(uc,'Unicorn is required for independent machine execution')
    def test_interleaved_requests_bind_projections_to_their_own_objects(self):
        a,p=executed('full',0,ticket=1);b,_=executed('full',1,use_c=True,ticket=2,g=0x999,offset=0x10000)
        d,plan=project(combine([a,b]),p,'output');r=bind(d,plan)
        self.assertEqual(r['status'],'resolved',r)
        self.assertEqual([row['local_sources'] for row in r['results']],[['source:1'],['source:3']])

    @unittest.skipUnless(uc,'Unicorn is required for independent machine execution')
    def test_projection_graph_stitches_to_actual_upstream_bytes(self):
        from test_gin_cross_provenance import evidence as cross_evidence,OTHER
        from test_gin_otel_provenance import spans
        from gin_cross_boundaries import bind_service
        from gin_otel_boundaries import stitch_otel
        from lineage_graph import backward_nodes
        upstream,up=cross_evidence('upstream',trace=OTHER)
        downstream,dp=cross_evidence('downstream');local,p=executed('full',1)
        dp['sites']=[s for s in dp['sites'] if s['op']!='instruction'];mapping={}
        for spec in p['sites']:
            if spec['op']!='instruction':continue
            sid=max(s['id'] for s in dp['sites'])+1;mapping[spec['id']]=sid;dp['sites'].append(dict(spec,id=sid))
        for key in ('instructions','entry','runtime_inputs','runtime_input_ownership','observation_target','scope'):
            dp[key]=deepcopy(p[key])
        for n in dp['instructions']:n['site']=mapping[n['site']]
        dp['runtime_input_sites']=[mapping[s] for s in p['runtime_input_sites']]
        dp['event_order']=[s['id'] for s in dp['sites']];dp['trace_mode']='otel'
        start=next(i for i,e in enumerate(downstream['events']) if e['op']=='work' and e['phase']=='pre')
        end=next(i for i,e in enumerate(downstream['events']) if e['op']=='work' and e['phase']=='post')
        body=[deepcopy(e) for e in local['events'] if e['op'] in ('work','instruction')]
        for e in body:
            e['pid']=20
            if e['op']=='instruction':e['site']=mapping[e['site']]
        downstream['events'][start:end+1]=body
        for i,e in enumerate(downstream['events']):
            e['sequence']=i;e['timestamp']=i
            if e['op']=='source' and e['phase']=='pre':e['values'].pop('trace',None)
            if e['op']=='http_header' and e['phase']=='pre':e['values']['trace']['hex']=OTHER.encode().hex()
        downstream['stats']['submitted']=len(downstream['events'])
        doc,plan=project(downstream,dp,'output')
        result=stitch_otel(bind_service(upstream,up),bind_service(doc,plan),spans())
        self.assertEqual(result['status'],'resolved',result)
        graph=result['results'][0]['graph'];nodes={n['id']:n for n in graph['nodes']}
        for i in range(4):
            kept=backward_nodes(graph['edges'],[f'downstream/request:1:output-byte:{i}'],{'data','http-json-field'})
            self.assertIn(f'upstream/request:1:output-byte:{i}',kept)
            self.assertTrue(any(nodes[n]['kind']=='source' and nodes[n]['path'].endswith('A.txt') for n in kept))

if __name__=='__main__':unittest.main()
