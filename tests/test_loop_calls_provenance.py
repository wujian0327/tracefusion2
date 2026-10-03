"""C-native and Go-ABI ISA evidence for one shared dynamic call/loop engine."""
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
import loop_calls_provenance as core
import go_loop_calls_provenance as go
from test_interproc_provenance import emulated_events,uc
from test_go_loop_provenance import compile_assembly

C_SCENARIO=core.common.ROOT/'scenarios/loop-calls-provenance'
GO_SCENARIO=core.common.ROOT/'scenarios/go-loop-calls-provenance'
COUNTS=(0,1,2,4)


def oracle(config,counts=COUNTS):
    rows=[]
    for round_id in range(2):
        v=424242+round_id
        for f,name in enumerate(config['functions']):
            for count in counts:
                value=(42 if count==0 else v) if f==0 else count*(v if f==1 else v^0x55)
                fields=[] if count==0 else ['input.secret' if count<=2 else 'input.public_value'] if f==0 else ['input.secret'] if count<=2 else ['input.secret','input.public_value']
                rows.append(dict(sequence=len(rows)+1,function=name,count=count,expected_helper_calls=count*(2 if f==2 else 1),expected_sources=fields,expected_value=value,output=value))
    return rows


def stats(events):
    return dict(backend='unicorn-test-only',received_events=len(events),attempted_events=len(events),lost_events=0,submit_errors=0,state_errors=0,process_returncode=0)


def go_assembly(config):
    pieces=['.intel_syntax noprefix\n.text\n']
    for kind,name in enumerate(config['functions']):
        callee='main.transformIteration' if kind==2 else 'main.readIteration'
        update='mov DWORD PTR [rsp+0x1c],eax' if kind==0 else 'mov edx,DWORD PTR [rsp+0x1c]\nadd edx,eax\nmov DWORD PTR [rsp+0x1c],edx'
        pieces.append(f'''
.globl {name}
.type {name},@function
{name}:
cmp rsp,QWORD PTR [r14+0x10]
jbe .Lslow{kind}
push rbp
mov rbp,rsp
sub rsp,0x20
mov QWORD PTR [rsp+0x30],rax
mov QWORD PTR [rsp+0x38],rbx
mov DWORD PTR [rsp+0x40],ecx
mov DWORD PTR [rsp+0x18],0
mov DWORD PTR [rsp+0x1c],{42 if kind==0 else 0}
.Lloop{kind}:
mov ecx,DWORD PTR [rsp+0x40]
mov edx,DWORD PTR [rsp+0x18]
cmp edx,ecx
jae .Ldone{kind}
mov rax,QWORD PTR [rsp+0x38]
mov ebx,edx
call {callee}
{update}
mov edx,DWORD PTR [rsp+0x18]
inc edx
mov DWORD PTR [rsp+0x18],edx
jmp .Lloop{kind}
.Ldone{kind}:
mov edx,DWORD PTR [rsp+0x1c]
mov rax,QWORD PTR [rsp+0x30]
mov DWORD PTR [rax],edx
add rsp,0x20
pop rbp
ret
.Lslow{kind}:
mov QWORD PTR [rsp+8],rax
call runtime.morestack_noctxt.abi0
jmp {name}
.size {name},.-{name}
''')
    pieces.append('''
.globl main.transformIteration
.type main.transformIteration,@function
main.transformIteration:
cmp rsp,QWORD PTR [r14+0x10]
jbe .Lslow_transform
push rbp
mov rbp,rsp
sub rsp,0x10
call main.readIteration
xor eax,0x55
add rsp,0x10
pop rbp
ret
.Lslow_transform:
mov QWORD PTR [rsp+8],rax
call runtime.morestack_noctxt.abi0
jmp main.transformIteration
.size main.transformIteration,.-main.transformIteration
.globl main.readIteration
.type main.readIteration,@function
main.readIteration:
cmp ebx,2
jae .Lpublic
mov eax,DWORD PTR [rax]
ret
.Lpublic:
mov eax,DWORD PTR [rax+4]
ret
.size main.readIteration,.-main.readIteration
.globl runtime.morestack_noctxt.abi0
.type runtime.morestack_noctxt.abi0,@function
runtime.morestack_noctxt.abi0:
ret
.size runtime.morestack_noctxt.abi0,.-runtime.morestack_noctxt.abi0
.section .note.GNU-stack,"",@progbits
''')
    return ''.join(pieces)


@unittest.skipUnless(uc and shutil.which('gcc'),'Requires GCC/binutils and optional Unicorn')
class LoopedCallTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.folder=Path(cls.temp.name);cls.cases={}
        out=cls.folder/'c';out.mkdir()
        binary,plans,config=core.build(C_SCENARIO,out)
        truth=[json.loads(l) for l in subprocess.check_output([str(binary)],text=True).splitlines()]
        events,bases=emulated_events(binary,plans,config,selections=COUNTS)
        cls.cases['c']=(binary,plans,config,events,bases,truth)
        config=json.loads((GO_SCENARIO/'config.json').read_text())
        binary,plans=compile_assembly(cls.folder/'go-assembly',go_assembly(config),config,planner=go.plan_program)
        events,bases=emulated_events(binary,plans,config,selections=COUNTS)
        cls.cases['go']=(binary,plans,config,events,bases,oracle(config))

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def replay(self,language,events=None):
        binary,plans,config,default,bases,truth=self.cases[language]
        return core.infer(default if events is None else events,plans,config,bases)

    def test_same_engine_native_c_and_independent_go_abi_loops(self):
        outcomes=[]
        for language,case in self.cases.items():
            binary,plans,config,events,bases,truth=case
            result=self.replay(language);score=core.evaluate(result,truth,stats(events),plans)
            self.assertEqual(result['issues'],[],language);self.assertTrue(score['passed'],score)
            self.assertEqual(len(result['results']),24)
            self.assertEqual(score['dynamic_source_relations']['tp'],22)
            outcomes.append([(r['value'],r['sources'],r['summary']['helper_calls']) for r in result['results']])
            self.assertEqual(max(r['summary']['maximum_depth'] for r in result['results']),3)
        self.assertEqual(outcomes[0],outcomes[1])

    def test_same_callsite_four_distinct_instances_and_last_overwrite(self):
        for language in self.cases:
            row=self.replay(language)['results'][3];calls=row['call_instances'][1:]
            self.assertEqual(len(calls),4)
            self.assertEqual(len({c['id'] for c in calls}),4)
            self.assertEqual(len({c['callsite'].split('@exec')[0] for c in calls}),1)
            self.assertEqual({c['parent_id'] for c in calls},{'root'})
            self.assertEqual([r['id'] for r in row['contributing_reads']],['input.public_value@read4'])
            self.assertEqual(row['contributing_reads'][0]['call_instance'],'call4')
            self.assertNotIn('input.secret',{n.get('field') for n in row['dependency_graph']['nodes']})

    def test_accumulation_and_nested_return_parentage(self):
        for language in self.cases:
            rows=self.replay(language)['results'];accum=rows[7];nested=rows[11]
            self.assertEqual({r['call_instance'] for r in accum['contributing_reads']},{'call1','call2','call3','call4'})
            self.assertEqual(len(nested['call_instances']),9)
            by_id={c['id']:c for c in nested['call_instances']}
            self.assertEqual({r['call_instance'] for r in nested['contributing_reads']},{'call2','call4','call6','call8'})
            for i in (2,4,6,8):self.assertEqual(by_id['call%d'%i]['parent_id'],'call%d'%(i-1))
            self.assertTrue({'argument','return'} <= {e['kind'] for e in nested['dependency_graph']['edges']})
            for c in nested['call_instances']:self.assertLessEqual(c['entry_sequence'],c['exit_sequence'])

    def test_zero_iterations_no_helper_or_field_read_and_explicit_scalar_origin(self):
        for language in self.cases:
            rows=self.replay(language)['results']
            for i in (0,4,8,12,16,20):
                self.assertEqual(rows[i]['summary']['helper_calls'],0)
                self.assertEqual(rows[i]['source_reads'],[])
                self.assertEqual(rows[i]['sources'],[])
                self.assertTrue(set(rows[i]['argument_sources'])<={'arg.select'})

    def test_scalar_parameter_origin_is_reported_not_silently_removed(self):
        config=copy.deepcopy(self.cases['c'][2]);config['functions']=['parameter_output']
        assembly='''.intel_syntax noprefix
.text
.globl parameter_output
.type parameter_output,@function
parameter_output:
mov DWORD PTR [rdi],edx
ret
.size parameter_output,.-parameter_output
.section .note.GNU-stack,"",@progbits
'''
        binary,plans=compile_assembly(self.folder/'scalar-parameter',assembly,config,planner=core.plan_program)
        events,bases=emulated_events(binary,plans,config,selections=(0,1))
        result=core.infer(events,plans,config,bases)
        self.assertEqual(result['issues'],[])
        for row in result['results']:
            self.assertEqual(row['argument_sources'],['arg.select'])
            self.assertEqual(row['sources'],[])
            self.assertIn('arg.select',{n['local_node'] for n in row['dependency_graph']['nodes']})

    def test_corrupt_call_return_identity_and_incomplete_evidence_rejected(self):
        for language,case in self.cases.items():
            plans=case[1];template=[r for r in case[3] if r['call_id']==12]
            nested=next(i for i,r in enumerate(template) if r['depth']==3)
            for fault in ('depth','wrong-function','return-address','missing','duplicate','flags','early-end','extra-after-return','thread'):
                events=copy.deepcopy(template)
                if fault=='depth':events[nested]['depth']=1
                elif fault=='wrong-function':events[nested]['function']=events[0]['function']
                elif fault=='return-address':
                    e=events[nested];e['stack'][(e['regs'][7]-e['root_sp']+core.model.STACK_BYTES)//8]^=1
                elif fault=='missing':events.pop(nested)
                elif fault=='duplicate':events.insert(nested,copy.deepcopy(events[nested]))
                elif fault=='flags':events[nested]['flags']^=64
                elif fault=='early-end':events.pop()
                elif fault=='extra-after-return':
                    events.append(copy.deepcopy(events[-1]));events[-1]['sequence']+=1
                else:events[nested]['pid_tid']+=1
                with self.subTest(language=language,fault=fault):self.assertFalse(self.replay(language,events)['results'])

    def test_removing_whole_iteration_and_resequencing_still_fails(self):
        for language,case in self.cases.items():
            plans=case[1];template=[r for r in case[3] if r['call_id']==8]
            instructions={n['offset']:n for n in plans[1]['instructions']}
            callsites=[i for i,r in enumerate(template) if r['depth']==1 and instructions[r['offset']]['op']=='call']
            self.assertEqual(len(callsites),4)
            events=copy.deepcopy(template[:callsites[1]]+template[callsites[2]:])
            for i,e in enumerate(events):e['sequence']=i
            self.assertFalse(self.replay(language,events)['results'])

    def test_budget_loss_and_oracle_call_count_cannot_be_ignored(self):
        for language,case in self.cases.items():
            events,truth,plans=case[3],case[5],case[1]
            with patch.object(core,'MAX_EXECUTED_STEPS',5):self.assertFalse(self.replay(language)['results'])
            result=self.replay(language)
            self.assertFalse(core.evaluate(result,truth,dict(stats(events),lost_events=1),plans)['passed'])
            bad=copy.deepcopy(truth);bad[3]['expected_helper_calls']-=1
            self.assertFalse(core.evaluate(result,bad,stats(events),plans)['passed'])

    def test_go_runtime_slow_path_and_guard_read_error_rejected(self):
        binary,plans,config,events,bases,truth=self.cases['go']
        slow,sb=emulated_events(binary,plans,config,selections=COUNTS,runtime_guard=(1<<64)-1)
        self.assertFalse(core.infer(slow,plans,config,sb)['results'])
        bad=copy.deepcopy([e for e in events if e['call_id']==12]);bad[0]['runtime_guard_error']=-14
        self.assertFalse(self.replay('go',bad)['results'])

    def test_unseen_counts_and_renamed_c_functions(self):
        scenario=self.folder/'renamed-scenario';shutil.copytree(C_SCENARIO,scenario)
        for name in ('main.c','operations.c','model.h','config.json'):
            p=scenario/name;s=p.read_text().replace('loop_call_','renamed_loop_').replace('read_iteration','other_read').replace('transform_iteration','other_transform').replace('{0, 1, 2, 4}','{0, 1, 3, 7}')
            p.write_text(s)
        out=self.folder/'renamed-build';out.mkdir()
        binary,plans,config=core.build(scenario,out)
        events,bases=emulated_events(binary,plans,config,selections=(0,1,3,7))
        truth=[json.loads(l) for l in subprocess.check_output([str(binary)],text=True).splitlines()]
        result=core.infer(events,plans,config,bases)
        self.assertTrue(core.evaluate(result,truth,stats(events),plans)['passed'],result['issues'])

    def test_dynamic_cmov_inside_repeated_go_helper(self):
        config=self.cases['go'][2]
        assembly=go_assembly(config).replace('cmp ebx,2\njae .Lpublic\nmov eax,DWORD PTR [rax]\nret\n.Lpublic:\nmov eax,DWORD PTR [rax+4]\nret',
            'mov ecx,DWORD PTR [rax]\ncmp ebx,2\ncmovae ecx,DWORD PTR [rax+4]\nmov eax,ecx\nret')
        binary,plans=compile_assembly(self.folder/'cmov-go',assembly,config,planner=go.plan_program)
        events,bases=emulated_events(binary,plans,config,selections=COUNTS)
        result=core.infer(events,plans,config,bases)
        self.assertTrue(core.evaluate(result,oracle(config),stats(events),plans)['passed'],result['issues'])
        self.assertEqual(result['results'][3]['contributing_reads'][0]['call_instance'],'call4')
        self.assertEqual(result['results'][3]['contributing_reads'][0]['id'],'input.public_value@read8')


class PlannerRejectionTests(unittest.TestCase):
    def test_recursion_unknown_calls_and_entry_backedge(self):
        config=json.loads((C_SCENARIO/'config.json').read_text());config['functions']=['root']
        for assembly,symbols in [
            ('1000: call 2000 <helper>\n1005: ret\n2000: call 2000 <helper>\n2005: ret',{'root':(0x1000,6),'helper':(0x2000,6)}),
            ('1000: call 3000 <unknown>\n1005: ret',{'root':(0x1000,6)}),
            ('1000: jmp 1000 <root>',{'root':(0x1000,2)})]:
            with self.assertRaises(ValueError):core.plan_program(assembly,symbols,config)


@unittest.skipUnless(shutil.which('go') and uc,'Actual Go compiler and optional Unicorn required')
class ActualGoLoopedCallTests(unittest.TestCase):
    def test_native_go_build_and_independent_instruction_execution(self):
        with tempfile.TemporaryDirectory() as d:
            binary,plans,config=go.build(GO_SCENARIO,Path(d))
            events,bases=emulated_events(binary,plans,config,selections=COUNTS)
            truth=[json.loads(l) for l in subprocess.check_output([str(binary)],text=True).splitlines()]
            result=core.infer(events,plans,config,bases)
            self.assertTrue(core.evaluate(result,truth,stats(events),plans)['passed'],result['issues'])


if __name__=='__main__':unittest.main()
