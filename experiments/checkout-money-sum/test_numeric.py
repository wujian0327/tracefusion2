"""Instruction semantics and capture integrity checks, independent of fixture truth."""
import copy
import sys
from pathlib import Path
import unittest
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from bounded_numeric_flow import analyze, branch_taken
import sum_adapter as adapter


def rows(instructions):
    return [dict(address=0x100+4*i,asm=a,code='90') for i,a in enumerate(instructions)]


def flow(instructions,registers=None,stack=None,outputs=None,calls=()):
    return analyze(rows(instructions+['ADDQ $0x10, SP','POPQ BP','RET']),16,
                   registers or [('R10',8,'l.Units'),('R11',4,'l.Nanos')],
                   stack or [(32,8,'r.Units'),(40,4,'r.Nanos')],
                   outputs or {'Units':('AX',8),'Nanos':('BX',4)},calls,[])


class NumericTests(unittest.TestCase):
    def test_additions_join_only_their_operand_fields(self):
        f=flow(['MOVQ R10, AX','ADDQ 0x20(SP), AX','MOVL R11, BX','ADDL 0x28(SP), BX'])
        self.assertEqual(f['paths'][0]['origins'],{'Units':['l.Units','r.Units'],'Nanos':['l.Nanos','r.Nanos']})

    def test_three_operand_multiply_kills_previous_destination(self):
        f=flow(['MOVQ 0x20(SP), AX','IMULQ $0x2, R10, AX','SARQ $0x3, AX','MOVL R11, BX'])
        self.assertEqual(f['paths'][0]['origins']['Units'],['l.Units'])

    def test_partial_stack_write_retains_untouched_bytes(self):
        f=flow(['MOVL R11, 0x20(SP)','MOVQ 0x20(SP), AX','MOVL R11, BX'])
        self.assertEqual(f['paths'][0]['origins']['Units'],['l.Nanos','r.Units'])

    def test_register_32bit_write_zero_extends_and_replaces_old_origin(self):
        f=flow(['MOVQ 0x20(SP), AX','MOVL R11, AX','MOVL R11, BX'])
        self.assertEqual(f['paths'][0]['origins']['Units'],['l.Nanos'])

    def test_sign_extension_and_constant_updates_keep_input_origin(self):
        f=flow(['MOVSXD R11, AX','INCQ AX','DECQ AX','MOVL R11, BX'])
        self.assertEqual(f['paths'][0]['origins']['Units'],['l.Nanos'])

    def test_zeroing_clears_old_origins(self):
        f=flow(['MOVQ R10, AX','XORL AX, AX','MOVL R11, BX'])
        self.assertEqual(f['paths'][0]['origins']['Units'],[])

    def test_readonly_contract_preserves_spill_but_clobbers_registers(self):
        f=flow(['MOVQ R10, 0x8(SP)','CALL helper(SB)','MOVQ 0x8(SP), AX','MOVL 0x28(SP), BX'],calls=['helper(SB)'])
        self.assertEqual(f['paths'][0]['origins']['Units'],['l.Units'])
        with self.assertRaises(ValueError):flow(['CALL helper(SB)','MOVQ R10, AX','MOVL R11, BX'],calls=['helper(SB)'])

    def test_unsupported_call_alias_loop_and_unknown_output_fail_closed(self):
        for code in (['CALL unknown(SB)'],['MOVQ R10, 0x8(AX)'],['JMP 0x100'],['MOVQ DX, AX','MOVL R11, BX']):
            with self.subTest(code=code),self.assertRaises(ValueError):flow(code)

    def test_flags_signed_unsigned_predicates(self):
        self.assertTrue(branch_taken('JGE',0))
        self.assertFalse(branch_taken('JGE',1<<7))
        self.assertTrue(branch_taken('JGE',(1<<7)|(1<<11)))
        self.assertFalse(branch_taken('JG',1<<6))
        self.assertTrue(branch_taken('JLE',1<<6))
        self.assertTrue(branch_taken('JBE',1))
        self.assertFalse(branch_taken('JA',1))

    def test_equal_return_origins_drop_branch(self):
        code=['MOVQ R10, AX','MOVL R11, BX','TESTQ AX, AX','JE 0x114','INCQ AX']
        f=flow(code)
        self.assertEqual(len(f['paths']),2)
        self.assertEqual(f['selected_branches'],[])


def capture():
    a={'Units':['l.Units','r.Units'],'Nanos':['l.Nanos','r.Nanos']}
    b={'Units':['l.Nanos','l.Units','r.Nanos','r.Units'],'Nanos':['l.Nanos','r.Nanos']}
    paths=[dict(id=i,branches=[dict(address=104,taken=bool(i))],return_address=108,origins=o) for i,o in enumerate((a,b))]
    sites=[dict(id=0,address=100,kind='entry'),dict(id=1,address=104,kind='branch',op='JE'),dict(id=2,address=108,kind='exit')]
    p=dict(binary_sha256='synthetic',flow=dict(paths=paths,semantics='data'),sites=sites,all_sites=sites,
           event_order=[0,1,2],strategy='selected',right_units=216,right_nanos=224,error_return_sp_offset=80)
    events=[dict(timestamp=i+1,pid_tid=1<<32|2,g=100,site=i,kind=s['kind'],a=0,b=0,c=0,d=0) for i,s in enumerate(sites)]
    events[0].update(a=1,b=0,c=1,d=0);events[1]['a']=0x40;events[2]['a']=2
    d=dict(binary_sha256='synthetic',returncode=0,capture_errors=[],events=events,
           stats=dict(submitted=3,probe_hits=3,pid_rejections=0,lost=0,read_errors=0,submit_errors=0,namespace_errors=0))
    return p,d


class CaptureTests(unittest.TestCase):
    def test_selected_and_boundary_candidates_do_not_use_values_to_filter(self):
        p,d=capture();r=adapter.infer(p,d)
        self.assertEqual(r['status'],'exact_data_origins')
        self.assertEqual(len(r['candidates'][0]['Units']),4)
        p=adapter.strategy_plan(p,'boundaries');del d['events'][1];d['stats'].update(submitted=2,probe_hits=2)
        self.assertEqual(adapter.infer(p,d)['status'],'ambiguous')

    def test_missing_control_cannot_be_reported_as_known(self):
        p,d=capture();del d['events'][1];d['stats'].update(submitted=2,probe_hits=2)
        self.assertEqual(adapter.infer(p,d)['status'],'unknown')

    def test_loss_wrong_binary_and_invocation_rejected(self):
        for mutation in (lambda d:d['stats'].update(lost=1),lambda d:d.update(binary_sha256='wrong'),lambda d:d['events'][-1].update(g=999)):
            p,d=capture();mutation(d)
            with self.assertRaises(ValueError):adapter.infer(p,d)

    def test_error_pointer_inconsistent_with_success_model_is_unknown(self):
        p,d=capture();d['events'][-1]['c']=1
        self.assertEqual(adapter.infer(p,d)['status'],'unknown')

    def test_signed_values_and_capture_addresses(self):
        self.assertEqual(adapter.signed(0xffffffff,32),-1)
        self.assertEqual(adapter.signed(0xffffffffffffffff,64),-1)
        p,_=capture();c=adapter.source(p,9,SimpleNamespace(st_dev=4,st_ino=123))
        self.assertIn('word64(e,ctx->sp+216)',c)
        self.assertIn('word32(e,ctx->sp+224)',c)
        self.assertIn('word64(e,ctx->sp+80)',c)
        self.assertIn('e->a=ctx->flags;',c)


if __name__=='__main__':unittest.main()
