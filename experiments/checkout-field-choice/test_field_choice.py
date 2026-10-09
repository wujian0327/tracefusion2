"""Synthetic instruction/transport tests; independent of the Go fixture truth."""
import copy
import ctypes as ct
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from bounded_field_flow import analyze
import field_choice as f


def rows():
    asm=['CMPQ SP, 0x10(R14)','JBE 0x999','PUSHQ BP','MOVQ SP, BP','SUBQ $0x10, SP',
         'MOVQ AX, 0x20(SP)','MOVQ BX, 0x28(SP)','MOVB CL, 0x30(SP)',
         'LEAQ 0x100(IP), AX','CALL runtime.newobject(SB)','MOVQ $0x3, 0x30(AX)',
         'LEAQ 0x200(IP), CX','MOVQ CX, 0x28(AX)','MOVQ 0x20(SP), CX','MOVQ 0x38(CX), CX',
         'MOVZX 0x30(SP), DX','TESTL DL, DL','JE 0x150','MOVQ 0x28(SP), DX','MOVQ 0x38(DX), CX',
         'MOVQ CX, 0x38(AX)','ADDQ $0x10, SP','POPQ BP','RET']
    return [dict(address=0x100+i*4,asm=a,code='0fb6542430' if a.startswith('MOVZX') else '90') for i,a in enumerate(asm)]


def fixture(taken=True,values=(14,14)):
    flow=analyze(rows(),56)
    sites=[dict(id=0,kind='entry',address=flow['entry']),
           dict(id=1,kind='branch',address=flow['selected_branches'][0],op='JE'),
           dict(id=2,kind='exit',address=flow['paths'][0]['return_address'])]
    plan=dict(binary_sha256='synthetic',field_offset=56,flow=flow,sites=sites,event_order=[0,1,2],strategy='selected')
    events=[]
    for i,kind in enumerate(('entry','branch','exit')):
        e=dict(timestamp=i+1,pid_tid=(9<<32)|10,g=512,site=i,kind=kind,a=0,b=0,c=0,d=0)
        if kind=='entry':e.update(a=1000,b=2000,c=values[0],d=values[1])
        if kind=='branch':e['a']=0x40 if taken else 0
        if kind=='exit':e.update(a=3000,b=values[0 if taken else 1])
        events.append(e)
    stats=dict(submitted=3,probe_hits=3,pid_rejections=0,lost=0,read_errors=0,submit_errors=0,namespace_errors=0)
    return plan,dict(binary_sha256='synthetic',capture_errors=[],returncode=0,stats=stats,events=events)


class StaticFlowTests(unittest.TestCase):
    def test_output_dependency_follows_last_assignment(self):
        flow=analyze(rows(),56)
        self.assertEqual([p['sink']['input_index'] for p in flow['paths']],[0,1])
        self.assertEqual([len(p['loads']) for p in flow['paths']],[1,2])
        self.assertEqual(flow['selected_branches'],[0x144])

    def test_source_mapping_changes_when_binary_spills_are_swapped(self):
        code=rows();code[5]['asm']='MOVQ BX, 0x20(SP)';code[6]['asm']='MOVQ AX, 0x28(SP)'
        self.assertEqual([p['sink']['input_index'] for p in analyze(code,56)['paths']],[1,0])

    def test_dead_second_load_does_not_become_sink_source(self):
        code=rows();code[19]['asm']='MOVQ 0x38(DX), DX'
        flow=analyze(code,56)
        self.assertEqual([p['sink']['input_index'] for p in flow['paths']],[0,0])
        self.assertEqual(flow['selected_branches'],[])

    def test_unknown_calls_arithmetic_aliasing_and_loops_rejected(self):
        changes=((9,'CALL unknown.helper(SB)'),(16,'ADDQ $0x1, CX'),
                 (12,'MOVQ CX, 0x38(BX)'),(17,'JE 0x134'),(20,'MOVB CL, 0x38(AX)'),
                 (13,'MOVQ $0x0, SP'),(20,'MOVQ CX, 0x100(AX)'))
        for index,asm in changes:
            code=rows();code[index]['asm']=asm
            with self.subTest(asm=asm),self.assertRaises(ValueError):analyze(code,56)

    def test_post_teardown_load_rejected(self):
        code=rows();code[22]['asm']='MOVQ 0x20(SP), CX'
        with self.assertRaises(ValueError):analyze(code,56)


class DynamicFlowTests(unittest.TestCase):
    def test_equal_values_different_executed_branch(self):
        for taken,expected in ((True,[0]),(False,[1])):
            p,d=fixture(taken);r=f.infer(p,d)
            self.assertEqual(r['source_candidates'],expected)
            self.assertEqual(r['status'],'exact_field_source')
            self.assertEqual(r['source_field_addresses'],[1056 if taken else 2056])

    def test_boundaries_preserve_both_candidates_even_with_different_values(self):
        p,d=fixture(False,(14,38));p=f.strategy_plan(p,'boundaries')
        del d['events'][1];d['stats'].update(submitted=2,probe_hits=2)
        r=f.infer(p,d)
        self.assertEqual(r['source_candidates'],[0,1]);self.assertEqual(r['status'],'ambiguous')

    def test_missing_required_branch_does_not_produce_exact_source(self):
        p,d=fixture();del d['events'][1];d['stats'].update(submitted=2,probe_hits=2)
        r=f.infer(p,d)
        self.assertEqual(r['status'],'unknown');self.assertEqual(r['source_candidates'],[])

    def test_value_mismatch_does_not_validate_model(self):
        p,d=fixture();d['events'][-1]['b']=999
        self.assertEqual(f.infer(p,d)['status'],'unknown')

    def test_wrong_flag_cannot_pass_independent_truth_for_equal_values(self):
        p,d=fixture(True);r=f.infer(p,d)
        truth={k:r[k] for k in ('input_objects','input_values','output_object','output_value','source_candidates')}
        truth.update(case='synthetic',source_field_address=1056)
        d['events'][1]['a']=0
        with self.assertRaises(ValueError):f.evaluate(p,f.infer(p,d),truth)

    def test_loss_invocation_and_reused_output_rejected(self):
        for change in (lambda d:d['stats'].update(lost=1),
                       lambda d:d['events'][-1].update(g=0),
                       lambda d:d['events'][-1].update(a=1000),
                       lambda d:d.update(binary_sha256='other')):
            p,d=fixture();change(d)
            with self.assertRaises(ValueError):f.infer(p,d)

    def test_perf_layout_flags_and_negative_values(self):
        self.assertEqual(ct.sizeof(f.Raw),64)
        raw=f.Raw();raw.site=1;raw.a=0x40
        buf=ct.create_string_buffer(bytes(raw)+b'\0'*4)
        for size in (64,68):self.assertEqual(f.decode_record(ct.addressof(buf),size,{1:dict(kind='branch')})['a'],0x40)
        with self.assertRaises(ValueError):f.decode_record(ct.addressof(buf),60,{1:dict(kind='branch')})
        self.assertEqual(f.signed((1<<64)-3),-3)
        p,_=fixture();source=f.source(p,99,SimpleNamespace(st_dev=1,st_ino=2))
        self.assertIn('e->a=ctx->flags;',source)
        self.assertIn('e->c=word(e,e->a+56)',source)
        self.assertNotIn('snapshot(',source)


if __name__=='__main__':unittest.main()
