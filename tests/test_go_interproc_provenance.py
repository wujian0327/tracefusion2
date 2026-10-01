"""Independent ISA checks for Go call boundaries; assembly is not a Go build."""
import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import go_interproc_provenance as app
from test_interproc_provenance import emulated_events, uc

SCENARIO=app.go.common.ROOT/'scenarios/go-interproc-provenance'

# Mimic ordinary compiler frame/spill patterns, but label this independently
# assembled input accurately. Tests with a real compiler are separate below.
ASSEMBLY=r'''
.intel_syntax noprefix
.text
.macro start name
.globl \name
.type \name,@function
\name:
.endm
.macro end name
.size \name,.-\name
.endm
start main.goCallSelect
cmp rsp,QWORD PTR [r14+0x10]
jbe .Lselect_slow
push rbp
mov rbp,rsp
sub rsp,0x20
mov QWORD PTR [rsp+0x30],rax
mov rax,rbx
mov ebx,ecx
call main.transformSelected
mov rcx,QWORD PTR [rsp+0x30]
mov DWORD PTR [rcx],eax
add rsp,0x20
pop rbp
ret
.Lselect_slow:
mov QWORD PTR [rsp+8],rax
call runtime.morestack_noctxt.abi0
jmp main.goCallSelect
end main.goCallSelect

start main.goCallOverwrite
cmp rsp,QWORD PTR [r14+0x10]
jbe .Loverwrite_slow
push rbp
mov rbp,rsp
sub rsp,0x20
mov QWORD PTR [rsp+0x30],rax
mov QWORD PTR [rsp+0x38],rbx
mov rax,rbx
mov ebx,1
call main.readSelected
mov rcx,QWORD PTR [rsp+0x30]
mov DWORD PTR [rcx],eax
mov rax,QWORD PTR [rsp+0x38]
xor ebx,ebx
call main.readSelected
mov rcx,QWORD PTR [rsp+0x30]
mov DWORD PTR [rcx],eax
add rsp,0x20
pop rbp
ret
.Loverwrite_slow:
mov QWORD PTR [rsp+8],rax
call runtime.morestack_noctxt.abi0
jmp main.goCallOverwrite
end main.goCallOverwrite

start main.goCallMerge
lea r12,[rsp-0x20]
cmp r12,QWORD PTR [r14+0x10]
jbe .Lmerge_slow
push rbp
mov rbp,rsp
sub rsp,0x20
mov QWORD PTR [rsp+0x30],rax
mov QWORD PTR [rsp+0x38],rbx
mov rax,rbx
mov ebx,1
call main.transformSelected
mov DWORD PTR [rsp+0x14],eax
mov rax,QWORD PTR [rsp+0x38]
xor ebx,ebx
call main.readSelected
mov ecx,DWORD PTR [rsp+0x14]
add eax,ecx
mov rcx,QWORD PTR [rsp+0x30]
mov DWORD PTR [rcx],eax
add rsp,0x20
pop rbp
ret
.Lmerge_slow:
mov QWORD PTR [rsp+8],rax
call runtime.morestack_noctxt.abi0
jmp main.goCallMerge
end main.goCallMerge

start main.transformSelected
cmp rsp,QWORD PTR [r14+0x10]
jbe .Ltransform_slow
push rbp
mov rbp,rsp
sub rsp,0x10
call main.readSelected
xor eax,0x55
add rsp,0x10
pop rbp
ret
.Ltransform_slow:
mov QWORD PTR [rsp+8],rax
call runtime.morestack_noctxt.abi0
jmp main.transformSelected
end main.transformSelected

start main.readSelected
test ebx,ebx
jne .Lsecret
mov eax,DWORD PTR [rax+4]
ret
.Lsecret:
mov eax,DWORD PTR [rax]
ret
end main.readSelected

start runtime.morestack_noctxt.abi0
ret
end runtime.morestack_noctxt.abi0
.section .note.GNU-stack,"",@progbits
'''


def truth(config):
    rows=[]
    for round_id in range(2):
        v=424242+round_id
        for f,name in enumerate(config['functions']):
            for choice in (0,1):
                fields=['input.secret' if choice else 'input.public_value'] if f==0 else ['input.public_value'] if f==1 else ['input.secret','input.public_value']
                value=v^0x55 if f==0 else v if f==1 else (v^0x55)+v
                rows.append(dict(sequence=len(rows)+1,function=name,expected_sources=fields,expected_value=value,output=value))
    return rows


@unittest.skipUnless(uc and shutil.which('gcc'),'Requires GCC and optional Unicorn')
class GoCallISATests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();out=Path(cls.temp.name)
        (out/'calls.S').write_text(ASSEMBLY);(out/'main.c').write_text('int main(void) { return 0; }\n')
        cls.binary=out/'calls'
        subprocess.run(['gcc','-fPIE','-pie',str(out/'main.c'),str(out/'calls.S'),'-o',str(cls.binary)],check=True,capture_output=True)
        cls.assembly=subprocess.check_output(['objdump','-d','-M','intel','--no-show-raw-insn',str(cls.binary)],text=True)
        cls.symbols={}
        for line in subprocess.check_output(['nm','-S','--defined-only',str(cls.binary)],text=True).splitlines():
            words=line.split()
            if len(words)==4 and words[2] in ('t','T'):cls.symbols[words[3]]=(int(words[0],16),int(words[1],16))
        cls.config=json.loads((SCENARIO/'config.json').read_text())
        cls.plans=app.plan_program(cls.assembly,cls.symbols,cls.config)
        cls.events,cls.bases=emulated_events(cls.binary,cls.plans,cls.config)
        cls.stats=dict(received_events=len(cls.events),attempted_events=len(cls.events),lost_events=0,submit_errors=0,state_errors=0,process_returncode=0)

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def replay(self,events=None):
        return app.core.infer(self.events if events is None else events,self.plans,self.config,self.bases)

    def test_nested_calls_and_independent_same_value_oracle(self):
        result=self.replay();score=app.evaluate(result,truth(self.config),self.stats,self.plans)
        self.assertEqual(result['issues'],[])
        self.assertTrue(score['passed'],score)
        self.assertEqual(score['dynamic_source_relations']['tp'],16)
        self.assertLess(score['static_source_relations']['precision'],1)
        self.assertEqual(max(e['depth'] for e in self.events),3)
        kinds={e['kind'] for r in result['results'] for e in r['dependency_graph']['edges']}
        self.assertTrue({'argument','return'} <= kinds)

    def test_repeated_helper_contexts_and_overwrite_kill(self):
        row=self.replay()['results'][2]
        calls=[c for c in row['call_instances'] if c['function']=='main.readSelected']
        self.assertEqual(len(calls),2);self.assertNotEqual(calls[0]['context'],calls[1]['context'])
        self.assertEqual(row['sources'],['input.public_value'])
        self.assertNotIn('input.secret',{n['static_node'] for n in row['dependency_graph']['nodes']})

    def test_taken_stack_guard_is_rejected_not_skipped(self):
        events,bases=emulated_events(self.binary,self.plans,self.config,runtime_guard=(1<<64)-1)
        self.assertTrue(any(self.plans[e['function']]['instructions'][-1]['offset']==e['offset'] for e in events))
        result=app.core.infer(events,self.plans,self.config,bases)
        self.assertFalse(result['results']);self.assertEqual(len(result['issues']),12)

    def test_guard_stack_call_and_identity_corruption_rejected(self):
        template=[e for e in self.events if e['call_id']==1]
        nested=next(i for i,e in enumerate(template) if e['depth']==3)
        for fault in ('guard-value','guard-error','missing-guard','stack-spill','return-address','depth','missing','r14','return-register'):
            rows=copy.deepcopy(template)
            if fault=='guard-value':rows[0]['runtime_guard']=(1<<64)-1
            elif fault=='guard-error':rows[0]['runtime_guard_error']=-14
            elif fault=='missing-guard':del rows[0]['runtime_guard']
            elif fault=='stack-spill':rows[-1]['stack'][app.core.STACK_WORDS]^=1
            elif fault=='return-address':
                e=rows[nested];e['stack'][(e['regs'][7]-e['root_sp']+app.core.STACK_BYTES)//8]^=1
            elif fault=='depth':rows[nested]['depth']=1
            elif fault=='missing':rows.pop(nested)
            elif fault=='r14':rows[nested]['regs'][14]+=64
            elif fault=='return-register':rows[nested+1]['regs'][0]^=1
            with self.subTest(fault=fault):self.assertFalse(self.replay(rows)['results'])

    def test_runtime_external_and_unknown_guard_patterns_rejected(self):
        for old,new in [('main.readSelected','runtime.external'),('jbe','ja'),('[r14+0x10]','[r14+0x18]')]:
            asm=self.assembly.replace(old,new)
            symbols={k.replace(old,new):v for k,v in self.symbols.items()}
            with self.subTest(change=(old,new)),self.assertRaises(ValueError):app.plan_program(asm,symbols,self.config)
        with self.assertRaises(ValueError):app.core.plan_program(self.assembly,self.symbols,self.config)

    def test_bpf_guard_payload_and_spill_window(self):
        source=app.go.collector.bpf_source(self.plans,self.config)
        self.assertIn('stack[37]',source)
        self.assertIn('ctx->r14 + 16',source)
        self.assertIn('runtime_guard_error = bpf_probe_read_user',source)
        for p in self.plans:
            for n in p['instructions']:
                if n['op'] in ('guard_cmp','unsupported_runtime'):self.assertIn(n['offset'],p['probe_offsets'])


@unittest.skipUnless(shutil.which('go') and uc,'Actual Go compiler and optional Unicorn required')
class ActualGoCallTests(unittest.TestCase):
    def test_compiled_go_nested_calls_and_independent_instruction_execution(self):
        with tempfile.TemporaryDirectory() as d:
            binary,plans,config=app.build(SCENARIO,Path(d))
            events,bases=emulated_events(binary,plans,config)
            oracle=[json.loads(l) for l in subprocess.check_output([str(binary)],text=True).splitlines()]
            inferred=app.core.infer(events,plans,config,bases)
            stats=dict(received_events=len(events),attempted_events=len(events),lost_events=0,submit_errors=0,state_errors=0,process_returncode=0)
            self.assertTrue(app.evaluate(inferred,oracle,stats,plans)['passed'],inferred['issues'])


if __name__=='__main__':unittest.main()
