from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from go_receiver_summary import summarize_receiver
from go_object_graph import analyze
from go_byte_adapter import assembly_rows


def rows(*body):
    instructions=('PUSHQ BP','MOVQ SP, BP','SUBQ $0x20, SP',*body)
    return [dict(address=0x1000+i,code='90',asm=asm) for i,asm in enumerate(instructions)]


class ReceiverSummaryTests(unittest.TestCase):
    def test_loaded_pointer_forwarding_is_not_no_write_proof(self):
        s=summarize_receiver(rows('MOVQ 0x8(AX), AX','CALL DX','RET'),'fixture')
        self.assertTrue(s['direct_receiver_read_only_under_conditions'])
        self.assertEqual(s['direct_receiver_reads'][0]['offset'],8)
        self.assertTrue(s['loaded_values_forwarded'])
        self.assertFalse(s['transitive_no_write_proved'])
        self.assertFalse(s['may_preserve_caller_spills'])

    def test_direct_receiver_write_rejected(self):
        s=summarize_receiver(rows('MOVQ BX, 0x8(AX)','XORL AX, AX','RET'),'fixture')
        self.assertEqual(s['status'],'receiver_summary_rejected')
        self.assertTrue(s['direct_receiver_writes'])

    def test_raw_pointer_forwarding_rejected(self):
        s=summarize_receiver(rows('CALL DX','RET'),'fixture')
        self.assertTrue(s['receiver_address_escapes'])
        self.assertFalse(s['direct_receiver_read_only_under_conditions'])

    def test_raw_receiver_used_as_indirect_target_rejected(self):
        s=summarize_receiver(rows('MOVQ AX, BP','XORL AX, AX','CALL BP','RET'),'fixture')
        self.assertTrue(any(e['via']=='indirect_call_target' for e in s['receiver_address_escapes']))

    def test_pointer_spill_and_reload_do_not_hide_escape(self):
        s=summarize_receiver(rows('MOVQ AX, 0x40(SP)','XORL AX, AX',
            'MOVQ 0x40(SP), DI','CALL DX','RET'),'fixture')
        self.assertTrue(any(e.get('location')=='DI' for e in s['receiver_address_escapes']))

    def test_outgoing_stack_argument_escape_rejected(self):
        s=summarize_receiver(rows('MOVQ AX, 0x8(SP)','XORL AX, AX','CALL DX','RET'),'fixture')
        self.assertTrue(any(e['via']=='potential_stack_argument' for e in s['receiver_address_escapes']))

    def test_publication_through_store_rejected(self):
        s=summarize_receiver(rows('MOVQ AX, 0(DI)','XORL AX, AX','RET'),'fixture')
        self.assertTrue(any(e['via']=='indirect_store' for e in s['receiver_address_escapes']))

    def test_return_in_later_abi_register_rejected(self):
        s=summarize_receiver(rows('MOVQ AX, R8','XORL AX, AX','RET'),'fixture')
        self.assertTrue(any(e.get('location')=='R8' for e in s['receiver_address_escapes']))

    def test_pointer_arithmetic_not_silently_misreported(self):
        s=summarize_receiver(rows('LEAQ 0x8(AX), AX','MOVQ 0(AX), AX','RET'),'fixture')
        self.assertTrue(s['unsupported_conditions'])
        self.assertFalse(s['direct_receiver_read_only_under_conditions'])

    def test_exposed_local_frame_invalidates_summary_condition(self):
        s=summarize_receiver(rows('MOVQ AX, 0x40(SP)','LEAQ 0x40(SP), AX',
            'CALL DX','MOVQ 0x40(SP), AX','MOVQ 0(AX), AX','RET'),'fixture')
        self.assertTrue(s['unsupported_conditions'])

    def test_indirect_calls_still_rejected_by_default_object_analysis(self):
        with self.assertRaisesRegex(ValueError,'Indirect call'):
            analyze(rows('CALL DX','RET'),'fixture')

    def test_unmodeled_instruction_rejected(self):
        with self.assertRaisesRegex(ValueError,'Unsupported instruction'):
            summarize_receiver(rows('XCHGQ AX, BX','RET'),'fixture')


class RealRPCReceiverSummaryTests(unittest.TestCase):
    def test_real_wrappers_read_fields_but_leave_transitive_effects_unknown(self):
        for name in ('GetProduct','Convert'):
            with self.subTest(name=name):
                path=Path(__file__).parent/'fixtures'/('checkout-default-'+name+'.asm')
                s=summarize_receiver(assembly_rows(path.read_text()),name)
                self.assertTrue(s['direct_receiver_read_only_under_conditions'])
                self.assertEqual([(r['offset'],r['width']) for r in s['direct_receiver_reads']],[(0,8),(8,8)])
                self.assertEqual(s['frame_size'],128)
                self.assertEqual(len(s['indirect_calls']),1)
                self.assertEqual(s['indirect_calls'][0]['target_load_offsets'],[0,24])
                self.assertEqual(s['indirect_calls'][0]['receiver_related_register_loads']['AX'],[8])
                self.assertTrue(s['loaded_values_forwarded'])
                self.assertFalse(s['may_preserve_caller_spills'])


if __name__=='__main__':
    unittest.main()
