"""Go ABI loop ISA fixtures; assembled independently, not compiled from Go."""
import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import go_loop_provenance as app
import interproc_model as model
from test_interproc_provenance import emulated_events, uc

SCENARIO=app.go.common.ROOT/'scenarios/go-loop-provenance'
COUNTS=(0,1,2,4)

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
start main.goLoopTransform
mov edx,DWORD PTR [rbx]
test ecx,ecx
je .Ltransform_done
.Ltransform_body:
dec ecx
xor edx,0x55
add edx,3
test ecx,ecx
jne .Ltransform_body
.Ltransform_done:
mov DWORD PTR [rax],edx
ret
end main.goLoopTransform

start main.goLoopOverwrite
xor edx,edx
mov esi,42
jmp .Loverwrite_cond
.Loverwrite_body:
cmp edx,2
mov esi,DWORD PTR [rbx]
cmovae esi,DWORD PTR [rbx+4]
inc edx
.Loverwrite_cond:
cmp edx,ecx
jb .Loverwrite_body
mov DWORD PTR [rax],esi
ret
end main.goLoopOverwrite

start main.goLoopAccumulate
xor edx,edx
xor edi,edi
xchg ax,ax
jmp .Laccum_cond
.Laccum_body:
mov esi,DWORD PTR [rbx]
cmp edx,2
cmovae esi,DWORD PTR [rbx+4]
add edi,esi
inc edx
.Laccum_cond:
cmp edx,ecx
jb .Laccum_body
mov DWORD PTR [rax],edi
ret
end main.goLoopAccumulate
.section .note.GNU-stack,"",@progbits
'''


def compile_assembly(folder,assembly,config,planner=app.plan_program):
    folder.mkdir()
    (folder/'model.S').write_text(assembly)
    (folder/'main.c').write_text('int main(void) { return 0; }\n')
    binary=folder/'loops'
    subprocess.run(['gcc','-fPIE','-pie',str(folder/'main.c'),str(folder/'model.S'),'-o',str(binary)],check=True,capture_output=True)
    disasm=subprocess.check_output(['objdump','-d','-M','intel','--no-show-raw-insn',str(binary)],text=True)
    symbols={}
    for line in subprocess.check_output(['nm','-S','--defined-only',str(binary)],text=True).splitlines():
        w=line.split()
        if len(w)==4 and w[2] in ('t','T'):symbols[w[3]]=(int(w[0],16),int(w[1],16))
    return binary,planner(disasm,symbols,config)


def oracle(config,counts=COUNTS,mask=0x55):
    rows=[]
    for round_id in range(2):
        v=424242+round_id
        for f,name in enumerate(config['functions']):
            for count in counts:
                if f==0:
                    value=v
                    for _ in range(count):value=((value^mask)+3)&0xffffffff
                    fields=['input.secret']
                elif f==1:
                    value=v if count else 42
                    fields=[] if count==0 else ['input.secret' if count<=2 else 'input.public_value']
                else:
                    value=count*v
                    fields=[] if count==0 else ['input.secret'] if count<=2 else ['input.secret','input.public_value']
                rows.append(dict(sequence=len(rows)+1,function=name,count=count,expected_value=value,output=value,expected_sources=fields))
    return rows


def stats(events):
    return dict(received_events=len(events),attempted_events=len(events),lost_events=0,submit_errors=0,state_errors=0,process_returncode=0)


@unittest.skipUnless(uc and shutil.which('gcc'),'Requires GCC and optional Unicorn')
class GoLoopISATests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.folder=Path(cls.temp.name)
        cls.config=json.loads((SCENARIO/'config.json').read_text())
        cls.binary,cls.plans=compile_assembly(cls.folder/'normal',ASSEMBLY,cls.config)
        cls.events,cls.bases=emulated_events(cls.binary,cls.plans,cls.config,selections=COUNTS)

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def replay(self,events=None):
        return app.go.core.infer(self.events if events is None else events,self.plans,self.config,self.bases)

    def test_zero_one_many_iterations_with_independent_value_and_field_truth(self):
        result=self.replay();score=app.evaluate(result,oracle(self.config),stats(self.events),self.plans)
        self.assertEqual(result['issues'],[])
        self.assertTrue(score['passed'],score)
        self.assertEqual(len(result['results']),24)
        self.assertEqual(score['dynamic_source_relations'],dict(tp=22,fp=0,fn=0,precision=1.0,recall=1.0))
        self.assertNotIn('read_instance_relations',score)
        self.assertEqual(result['results'][4]['sources'],[])
        self.assertEqual(result['results'][8]['sources'],[])

    def test_cmov_reads_unselected_memory_but_only_selected_value_contributes(self):
        row=self.replay()['results'][7]
        self.assertEqual(len(row['source_reads']),8)
        self.assertEqual([r['id'] for r in row['contributing_reads']],['input.public_value@read8'])
        nodes=row['dependency_graph']['nodes']
        self.assertEqual({n['field'] for n in nodes if n.get('kind')=='source-read'},{'input.public_value'})

    def test_accumulation_and_transform_preserve_execution_versions(self):
        rows=self.replay()['results']
        self.assertEqual({r['id'] for r in rows[11]['contributing_reads']},
                         {'input.secret@read1','input.secret@read3','input.public_value@read6','input.public_value@read8'})
        xors=[n for n in rows[3]['dependency_graph']['nodes'] if n.get('asm','').startswith('xor ')]
        self.assertEqual(len(xors),4);self.assertEqual(len({n['id'] for n in xors}),4)
        self.assertEqual(len(rows[3]['source_reads']),1)

    def test_deleted_iteration_flags_and_goroutine_changes_fail(self):
        template=[e for e in self.events if e['call_id']==12]
        ins={n['offset']:n for n in self.plans[2]['instructions']}
        cmov=next(i for i,e in enumerate(template) if ins[e['offset']]['op'].startswith('cmov'))
        for fault in ('missing','duplicate','flags','g','return'):
            events=copy.deepcopy(template)
            if fault=='missing':events.pop(cmov)
            elif fault=='duplicate':events.insert(cmov,copy.deepcopy(events[cmov]))
            elif fault=='flags':events[cmov]['flags']^=1
            elif fault=='g':events[cmov]['regs'][14]+=1
            else:events.pop()
            with self.subTest(fault=fault):self.assertFalse(self.replay(events)['results'])
        body=[i for i,e in enumerate(template) if ins[e['offset']]['asm'].startswith('mov esi,')]
        self.assertGreaterEqual(len(body),2)
        events=copy.deepcopy(template[:body[0]]+template[body[1]:])
        for i,e in enumerate(events):e['sequence']=i
        self.assertFalse(self.replay(events)['results'])
        with patch.object(app.go.core,'MAX_EXECUTED_STEPS',5):self.assertFalse(self.replay(template)['results'])

    def test_unseen_counts_renamed_functions_and_changed_transform(self):
        config=copy.deepcopy(self.config);assembly=ASSEMBLY.replace('0x55','0x66')
        for i,name in enumerate(config['functions']):
            new=name.replace('goLoop','otherLoop');assembly=assembly.replace(name,new);config['functions'][i]=new
        binary,plans=compile_assembly(self.folder/'variant',assembly,config)
        counts=(0,1,3,7);events,bases=emulated_events(binary,plans,config,selections=counts)
        result=app.go.core.infer(events,plans,config,bases)
        self.assertTrue(app.evaluate(result,oracle(config,counts,0x66),stats(events),plans)['passed'])

    def test_no_loop_calls_loss_and_missing_repetition_cannot_pass(self):
        config=copy.deepcopy(self.config);config['functions']=['main.root']
        for asm in ('1000: ret','1000: call 2000 <main.helper>\n1005: ret'):
            with self.assertRaises(ValueError):app.plan_program(asm,{'main.root':(0x1000,6)},config)
        result=self.replay()
        self.assertFalse(app.evaluate(result,oracle(self.config),dict(stats(self.events),lost_events=1),self.plans)['passed'])
        result['results'][3]['summary']['backward_edges']=0
        self.assertFalse(app.evaluate(result,oracle(self.config),stats(self.events),self.plans)['passed'])

    def test_inc_dec_carry_and_cmov_upper_bits_match_independent_cpu(self):
        config=copy.deepcopy(self.config);config['functions']=['main.edge']
        # Test old CF=0 and CF=1, overflow and wrap, and not-taken CMOV32
        # clearing upper bits. Replay compares all observed flags/registers.
        code=r'''
.intel_syntax noprefix
.text
.globl main.edge
.type main.edge,@function
main.edge:
mov esi,DWORD PTR [rbx]
mov edx,0
cmp edx,1
mov ecx,0x7fffffff
inc ecx
mov ecx,0x80000000
dec ecx
cmp edx,0
mov ecx,0xffffffff
inc ecx
dec ecx
mov rdi,-1
cmovb edi,esi
mov DWORD PTR [rax],edi
ret
.size main.edge,.-main.edge
.section .note.GNU-stack,"",@progbits
'''
        binary,plans=compile_assembly(self.folder/'edge',code,config,planner=app.go.core.plan_program)
        events,bases=emulated_events(binary,plans,config)
        result=app.go.core.infer(events,plans,config,bases)
        self.assertEqual(result['issues'],[])
        self.assertTrue(all(r['value']==0xffffffff and r['sources']==[] for r in result['results']))


@unittest.skipUnless(shutil.which('go') and uc,'Actual Go compiler and optional Unicorn required')
class ActualGoLoopTests(unittest.TestCase):
    def test_compiled_go_loops_independent_execution_and_native_truth(self):
        with tempfile.TemporaryDirectory() as d:
            binary,plans,config=app.build(SCENARIO,Path(d))
            events,bases=emulated_events(binary,plans,config,selections=COUNTS)
            truth=[json.loads(l) for l in subprocess.check_output([str(binary)],text=True).splitlines()]
            result=app.go.core.infer(events,plans,config,bases)
            self.assertTrue(app.evaluate(result,truth,stats(events),plans)['passed'],result['issues'])


if __name__=='__main__':unittest.main()
