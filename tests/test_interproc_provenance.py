"""Independent ISA execution, native fixture oracle, and cross-call regressions."""
import copy
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import hybrid_provenance as common
import interproc_model as model
import interproc_provenance as app
from language_adapters import get_adapter
try:
    import unicorn as uc
    from unicorn import x86_const as x86
except ImportError:
    uc=None

SCENARIO=common.ROOT/'scenarios/interproc-provenance'


def emulated_events(binary,plans,config,selections=(0,1),runtime_guard=None):
    adapter=get_adapter(config)
    elf=binary.read_bytes();phoff=struct.unpack_from('<Q',elf,32)[0]
    size,count=struct.unpack_from('<HH',elf,54)
    segments=[struct.unpack_from('<IIQQQQQQ',elf,phoff+i*size) for i in range(count)]
    bias=0x1000000;bases={p['function']:bias+p['symbol_address'] for p in plans}
    points={bases[p['function']]+off:(fid,off) for fid,p in enumerate(plans) for off in p['probe_offsets']}
    instructions={p['function']:{i['offset']:i for i in p['instructions']} for p in plans}
    events=[];call=0
    roots=[(fid,p) for fid,p in enumerate(plans) if p['is_root']]
    for round_id in range(2):
        for rootid,root in roots:
            for select in selections:
                call+=1;cpu=uc.Uc(uc.UC_ARCH_X86,uc.UC_MODE_64)
                mapped=set()
                for s in segments:
                    if s[0]!=1:continue
                    start=bias+s[3]
                    for page in range(start&~4095,(start+s[6]+4095)&~4095,4096):
                        if page not in mapped:cpu.mem_map(page,4096);mapped.add(page)
                    cpu.mem_write(start,elf[s[2]:s[2]+s[5]])
                src,dst,stack,stop=0x2000000,0x3000000,0x4000000,0x5000000
                for a in (src,dst,stack,stop):cpu.mem_map(a,4096)
                root_sp=stack+2040
                values=dict(secret=424242+round_id,public_value=424242+round_id,noise=99)
                cpu.mem_write(src,struct.pack('<'+'I'*len(config['input_fields']),*(values[f] for f in config['input_fields'])))
                cpu.mem_write(dst,struct.pack('<II',0xdeadbeef,0))
                cpu.mem_write(root_sp,struct.pack('<Q',stop))
                for reg,value in [(adapter.input_register,src),(adapter.output_register,dst),(adapter.selector_register,select),('rsp',root_sp)]:
                    cpu.reg_write(getattr(x86,'UC_X86_REG_'+reg.upper()),value)
                # Nonzero callee-saved values expose incorrect push/pop restoration.
                for i,r in enumerate(adapter.saved_registers):cpu.reg_write(getattr(x86,'UC_X86_REG_'+r.upper()),0xabc000+i)
                if adapter.runtime_guard_offset is not None:
                    goroutine=0x6000000;cpu.mem_map(goroutine,4096)
                    guard=stack+256 if runtime_guard is None else runtime_guard
                    cpu.mem_write(goroutine+adapter.runtime_guard_offset,struct.pack('<Q',guard))
                    cpu.reg_write(x86.UC_X86_REG_R14,goroutine)
                frames=[];sequence=[0]
                rejected=[False]
                def observe(machine,address,size,user):
                    if address not in points:return
                    fid,off=points[address];p=plans[fid]
                    if off==0:frames.append(fid)
                    assert frames and frames[-1]==fid
                    event=dict(timestamp=len(events)+1,pid_tid=(123<<32)|123,call_id=call,sequence=sequence[0],
                        root=rootid,depth=len(frames),src_addr=src,dst_addr=dst,root_sp=root_sp,ip=address,
                        flags=machine.reg_read(x86.UC_X86_REG_EFLAGS),
                        regs=[machine.reg_read(getattr(x86,'UC_X86_REG_'+r.upper())) for r in model.REGS],
                        function=fid,offset=off,source_error=0,destination_error=0,stack_error=0,
                        inputs=list(struct.unpack('<'+'I'*len(config['input_fields']),machine.mem_read(src,4*len(config['input_fields'])))),
                        outputs=list(struct.unpack('<'+'I'*len(config['output_fields']),machine.mem_read(dst,4*len(config['output_fields'])))),
                        stack=list(struct.unpack('<'+'Q'*(model.STACK_WORDS+adapter.stack_above//8),machine.mem_read(root_sp-model.STACK_BYTES,model.STACK_WORDS*8+adapter.stack_above))))
                    if adapter.runtime_guard_offset is not None:
                        event.update(runtime_guard=int.from_bytes(machine.mem_read(machine.reg_read(x86.UC_X86_REG_R14)+adapter.runtime_guard_offset,8),'little'),runtime_guard_error=0)
                    events.append(event);sequence[0]+=1
                    if instructions[p['function']][off]['op']=='ret':frames.pop()
                    if instructions[p['function']][off]['op']=='unsupported_runtime':
                        rejected[0]=True;machine.emu_stop()
                cpu.hook_add(uc.UC_HOOK_CODE,observe)
                cpu.emu_start(bases[root['function']],stop,timeout=1000000,count=5000)
                assert rejected[0] or (cpu.reg_read(x86.UC_X86_REG_RIP)==stop and not frames)
    return events,bases


class StaticTests(unittest.TestCase):
    def test_recursion_external_and_loops_are_rejected(self):
        c=json.loads((SCENARIO/'config.json').read_text());c['functions']=['entry']
        cases=[('1000: call 2000 <recursive>\n1005: ret\n2000: call 2000 <recursive>\n2005: ret',{'entry':(0x1000,6),'recursive':(0x2000,6)}),
               ('1000: call 3000 <external>\n1005: ret',{'entry':(0x1000,6)}),
               ('1000: jmp 1000 <entry>',{'entry':(0x1000,2)})]
        for asm,symbols in cases:
            with self.subTest(asm=asm),self.assertRaises(ValueError):model.plan_program(asm,symbols,c)


@unittest.skipUnless(uc and shutil.which('gcc'),'Requires GCC/binutils and optional Unicorn')
class CrossFunctionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.out=Path(cls.temp.name)/'build';cls.out.mkdir()
        cls.binary,cls.plans,cls.config=app.build(SCENARIO,cls.out)
        cls.events,cls.bases=emulated_events(cls.binary,cls.plans,cls.config)
        cls.oracle=[json.loads(l) for l in subprocess.check_output([str(cls.binary)],text=True).splitlines()]
        cls.stats=dict(backend='unicorn-test-only',received_events=len(cls.events),attempted_events=len(cls.events),
                       lost_events=0,submit_errors=0,state_errors=0,process_returncode=0)

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def replay(self,events=None):
        return model.infer(self.events if events is None else events,self.plans,self.config,self.bases)

    def test_nested_calls_returns_and_native_oracle(self):
        result=self.replay();evaluation=common.evaluate(result,self.oracle,self.stats,self.plans)
        self.assertEqual(result['issues'],[])
        self.assertTrue(evaluation['passed'],evaluation)
        self.assertEqual(len(result['results']),12)
        self.assertEqual(max(e['depth'] for e in self.events),3)
        self.assertGreater(len(self.plans),len(self.config['functions']))
        self.assertLess(evaluation['static_source_relations']['precision'],1)

    def test_repeated_helper_contexts_and_overwritten_first_return(self):
        result=self.replay()['results'][2]
        calls=[c for c in result['call_instances'] if c['function']=='read_selected']
        self.assertEqual(len(calls),2)
        self.assertNotEqual(calls[0]['context'],calls[1]['context'])
        self.assertEqual(result['sources'],['input.public_value'])
        self.assertNotIn('input.secret',{n['static_node'] for n in result['dependency_graph']['nodes']})
        kinds={e['kind'] for e in result['dependency_graph']['edges']}
        self.assertIn('argument',kinds);self.assertIn('return',kinds)

    def test_corrupt_return_stack_depth_and_callee_events_rejected(self):
        template=[e for e in self.events if e['call_id']==1]
        nested=next(i for i,e in enumerate(template) if e['depth']==3)
        for fault in ('stack','depth','missing','duplicate','return-register','root','stack-read','base'):
            events=copy.deepcopy(template)
            if fault=='stack':
                e=events[nested];index=(e['regs'][7]-(e['root_sp']-model.STACK_BYTES))//8;e['stack'][index]^=1
            elif fault=='depth':events[nested]['depth']=2
            elif fault=='missing':events.pop(nested)
            elif fault=='duplicate':events.insert(nested,copy.deepcopy(events[nested]))
            elif fault=='return-register':events[-1]['regs'][1]^=1
            elif fault=='root':events[nested]['root']=1
            elif fault=='stack-read':events[nested]['stack_error']=-14
            elif fault=='base':events[nested]['ip']+=16
            with self.subTest(fault=fault):
                result=self.replay(events);self.assertFalse(result['results']);self.assertTrue(result['issues'])

    def test_loss_and_missing_root_cannot_pass(self):
        inferred=self.replay()
        self.assertFalse(common.evaluate(inferred,self.oracle,dict(self.stats,lost_events=1),self.plans)['passed'])
        inferred=self.replay([e for e in self.events if e['call_id']!=1])
        self.assertFalse(common.evaluate(inferred,self.oracle,self.stats,self.plans)['passed'])

    def test_renaming_roots_helpers_and_relocating_binary(self):
        scenario=Path(self.temp.name)/'variant';scenario.mkdir()
        names=[p['function'] for p in self.plans]
        for f in SCENARIO.iterdir():shutil.copyfile(f,scenario/f.name)
        for name in ('model.h','main.c','operations.c'):
            file=scenario/name;text=file.read_text().replace('0x55u','0x66u')
            for old in sorted(names,key=len,reverse=True):text=text.replace(old,'renamed_'+old)
            if name=='operations.c':text='int unrelated(int n) { return n*n+3; }\n'+text
            file.write_text(text)
        config=copy.deepcopy(self.config);config['functions']=['renamed_'+n for n in config['functions']]
        common.save(scenario/'config.json',config)
        out=Path(self.temp.name)/'variant-build';out.mkdir()
        binary,plans,config=app.build(scenario,out)
        events,bases=emulated_events(binary,plans,config)
        truth=[json.loads(l) for l in subprocess.check_output([str(binary)],text=True).splitlines()]
        inferred=model.infer(events,plans,config,bases)
        self.assertEqual(inferred['issues'],[])
        self.assertTrue(common.evaluate(inferred,truth,dict(self.stats,received_events=len(events),attempted_events=len(events)),plans)['passed'])
        self.assertNotEqual(plans[0]['symbol_address'],self.plans[0]['symbol_address'])


if __name__=='__main__':unittest.main()
