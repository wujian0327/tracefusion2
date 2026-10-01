"""ABI contracts and independent ISA tests; assembler fixtures are NOT Go builds."""
import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import hybrid_provenance as common
import interproc_model as interproc
import loop_provenance as core
import go_provenance as go
from language_adapters import C, GO, get_adapter
from test_interproc_provenance import emulated_events, uc

GO_SCENARIO = common.ROOT/'scenarios/go-provenance'


class AdapterContracts(unittest.TestCase):
    def test_legacy_config_and_layout(self):
        config=json.loads((common.ROOT/'scenarios/interproc-provenance/config.json').read_text())
        self.assertEqual(get_adapter(config),C)
        self.assertEqual(C.layout(config,'input').field('public_value').offset,4)
        with self.assertRaises(ValueError): C.layout(config,'input').at(2,4)
        config['adapter']=GO.name
        with self.assertRaises(ValueError): get_adapter(config)
        config['adapter']='unknown'
        with self.assertRaises(ValueError): get_adapter(config)

    def test_go_symbol_sizes_are_decimal(self):
        self.assertEqual(go.parse_nm('  401000 16 T main.goSelect\n'),{'main.goSelect':(0x401000,16)})

    def test_go_rejects_runtime_calls_and_cross_function_planner(self):
        config=json.loads((GO_SCENARIO/'config.json').read_text());config['functions']=['main.one']
        asm='1000: call 2000 <runtime.morestack>\n1005: ret'
        symbols={'main.one':(0x1000,6),'runtime.morestack':(0x2000,1)}
        with self.assertRaisesRegex(ValueError,'leaf'):core.plan_program(asm,symbols,config)
        with self.assertRaisesRegex(ValueError,'leaf'):interproc.plan_program(asm,symbols,config)


@unittest.skipUnless(uc and shutil.which('gcc'),'Requires GCC/binutils and optional Unicorn')
class AdapterISATests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.cases={}
        template='''
.intel_syntax noprefix
.text
.globl NAME_select
.type NAME_select,@function
NAME_select:
test SELECTOR,SELECTOR
jne 1f
mov r8d,DWORD PTR [INPUT+4]
jmp 2f
1: mov r8d,DWORD PTR [INPUT]
xor r8d,0x55
2: mov DWORD PTR [OUTPUT],r8d
ret
.size NAME_select,.-NAME_select
.globl NAME_overwrite
.type NAME_overwrite,@function
NAME_overwrite:
mov r8d,DWORD PTR [INPUT]
mov DWORD PTR [OUTPUT],r8d
mov r8d,DWORD PTR [INPUT+4]
mov DWORD PTR [OUTPUT],r8d
ret
.size NAME_overwrite,.-NAME_overwrite
.globl NAME_merge
.type NAME_merge,@function
NAME_merge:
mov r8d,DWORD PTR [INPUT]
xor r8d,0x55
add r8d,DWORD PTR [INPUT+4]
mov DWORD PTR [OUTPUT],r8d
ret
.size NAME_merge,.-NAME_merge
.section .note.GNU-stack,"",@progbits
'''
        for adapter,prefix,select in [(C,'c','edx'),(GO,'main.go','ecx')]:
            folder=Path(cls.temp.name)/adapter.name;folder.mkdir()
            config=json.loads((GO_SCENARIO/'config.json').read_text())
            config.update(adapter=adapter.name,abi=adapter.abi,functions=[prefix+'_'+s for s in ('select','overwrite','merge')])
            assembly=template.replace('NAME',prefix).replace('SELECTOR',select).replace('INPUT',adapter.input_register).replace('OUTPUT',adapter.output_register)
            (folder/'model.S').write_text(assembly);(folder/'main.c').write_text('int main(void) { return 0; }\n')
            binary=folder/'test'
            subprocess.run(['gcc','-fPIE','-pie',str(folder/'main.c'),str(folder/'model.S'),'-o',str(binary)],check=True,capture_output=True)
            asm=subprocess.check_output(['objdump','-d','-M','intel','--no-show-raw-insn',str(binary)],text=True)
            symbols={}
            for line in subprocess.check_output(['nm','-S','--defined-only',str(binary)],text=True).splitlines():
                w=line.split()
                if len(w)==4 and w[2] in ('t','T'):symbols[w[3]]=(int(w[0],16),int(w[1],16))
            plans=core.plan_program(asm,symbols,config)
            events,bases=emulated_events(binary,plans,config)
            result=core.infer(events,plans,config,bases)
            cls.cases[adapter.name]=(config,plans,events,bases,result,binary)

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def test_same_provenance_engine_on_two_argument_conventions(self):
        outputs=[]
        for adapter in (C,GO):
            config,plans,events,bases,result,_=self.cases[adapter.name]
            self.assertEqual(result['issues'],[])
            self.assertEqual(len(result['results']),12)
            normalized=[(r['sources'],[x['id'] for x in r['contributing_reads']],r['value']) for r in result['results']]
            outputs.append(normalized)
            for i,r in enumerate(result['results']):
                round_id=i//6;kind=(i%6)//2;choice=i%2;v=424242+round_id
                expected=v if kind==1 or (kind==0 and choice==0) else v^0x55 if kind==0 else (v^0x55)+v
                fields=['input.public_value'] if kind==1 or (kind==0 and choice==0) else ['input.secret'] if kind==0 else ['input.public_value','input.secret']
                self.assertEqual(r['value'],expected);self.assertEqual(r['sources'],fields)
        self.assertEqual(outputs[0],outputs[1])

    def test_go_context_and_boundary_mismatch_rejected(self):
        config,plans,template,bases,_,_=self.cases[GO.name]
        for fault in ('goroutine-switch','missing-g','thread-switch','boundary'):
            events=copy.deepcopy(template)
            if fault=='boundary':events[0]['src_addr']+=4
            elif fault=='thread-switch':events[0]['pid_tid']+=1
            elif fault=='missing-g':events[0]['regs'][14]=0
            else:
                for e in events:
                    if e['call_id']==2:e['regs'][14]+=64
            with self.subTest(fault=fault):
                r=core.infer(events,plans,config,bases)
                self.assertTrue(r['issues'])
                self.assertLess(len(r['results']),12)

    def test_c_abi_cannot_decode_go_entry(self):
        config,plans,events,bases,_,_=self.cases[GO.name]
        wrong=copy.deepcopy(config);wrong.update(adapter=C.name,abi=C.abi,functions=['wrong'])
        result=core.infer(events,plans,wrong,bases)
        self.assertFalse(result['results']);self.assertTrue(result['issues'])

    def test_elf_mapping_nonzero_link_address(self):
        # GCC ET_EXEC tests the same object-format case needed by Go's
        # nonzero link addresses, without pretending this is a Go binary.
        folder=Path(self.temp.name)/'exec-layout';folder.mkdir()
        (folder/'a.c').write_text('int main(void) { return 0; }\n')
        binary=folder/'a';subprocess.run(['gcc','-no-pie',str(folder/'a.c'),'-o',str(binary)],check=True)
        import struct
        elf=binary.read_bytes();pos=struct.unpack_from('<Q',elf,32)[0];size,count=struct.unpack_from('<HH',elf,54)
        segments=[struct.unpack_from('<IIQQQQQQ',elf,pos+i*size) for i in range(count)]
        lines=[]
        for seg in segments:
            if seg[0]!=1:continue
            start=seg[3]&~4095;end=(seg[3]+seg[6]+4095)&~4095;off=seg[2]&~4095
            lines.append(f'{start:x}-{end:x} r'+('x' if seg[1]&1 else '-')+f'p {off:08x} 00:00 0 {binary}')
        executable=next(s for s in segments if s[0]==1 and s[1]&1)
        plans=[dict(function='test',symbol_address=executable[3],probe_offsets=[0])]
        self.assertEqual(common.resolve_runtime_bases(elf,'\n'.join(lines),str(binary),plans),{'test':executable[3]})
        with self.assertRaises(ValueError):common.resolve_runtime_bases(elf,'',str(binary),plans)


@unittest.skipUnless(shutil.which('go') and uc,'Actual Go compiler and optional Unicorn required')
class ActualGoBuildTests(unittest.TestCase):
    def test_native_go_fixture_and_independent_instruction_execution(self):
        with tempfile.TemporaryDirectory() as d:
            binary,plans,config=go.build(GO_SCENARIO,Path(d))
            events,bases=emulated_events(binary,plans,config)
            oracle=[json.loads(l) for l in subprocess.check_output([str(binary)],text=True).splitlines()]
            result=core.infer(events,plans,config,bases)
            stats=dict(received_events=len(events),attempted_events=len(events),lost_events=0,
                       submit_errors=0,state_errors=0,process_returncode=0)
            self.assertTrue(go.evaluate(result,oracle,stats,plans)['passed'])


if __name__=='__main__':unittest.main()
