"""Unknown writes must not silently inherit the old spill-slot provenance."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from go_byte_adapter import assembly_rows
from go_object_graph import analyze, terminals, stack_blockers


def graph(*body):
    instructions=('PUSHQ BP','MOVQ SP, BP','SUBQ $0x20, SP',*body)
    rows=[dict(address=0x1000+i,code='90',asm=asm) for i,asm in enumerate(instructions)]
    return analyze(rows,'fixture')


class StackEffectsTests(unittest.TestCase):
    def kinds(self,g,roots):
        return {g['nodes'][k]['kind'] for k in terminals(g,roots)}

    def test_unknown_call_kills_spill_even_without_visible_address_escape(self):
        g=graph('MOVQ BX, 0x8(SP)','CALL external.maybeWrite(SB)',
                'MOVQ 0x8(SP), CX','MOVQ CX, 0(DI)','RET')
        s=g['stores'][0]
        self.assertEqual(self.kinds(g,s['value_inputs']),{'unknown_stack_effect'})
        self.assertNotIn('entry:BX',terminals(g,s['value_inputs']))
        self.assertTrue(s['value_stack_blockers'])

    def test_explicit_alias_store_kills_old_spill(self):
        g=graph('MOVQ BX, 0x8(SP)','LEAQ 0x8(SP), AX','MOVQ DI, 0(AX)',
                'MOVQ 0x8(SP), CX','MOVQ CX, 0(SI)','RET')
        self.assertEqual(self.kinds(g,g['stores'][-1]['value_inputs']),{'unknown_stack_effect'})

    def test_same_value_store_does_not_restore_old_origin(self):
        # Writing BX again could be a new write/version. This pass deliberately
        # does not make a source claim based on value/register equality.
        g=graph('MOVQ BX, 0x8(SP)','LEAQ 0x8(SP), AX','MOVQ BX, 0(AX)',
                'MOVQ 0x8(SP), CX','MOVQ CX, 0(SI)','RET')
        self.assertTrue(g['stores'][-1]['value_stack_blockers'])

    def test_explicit_direct_overwrite_recovers_known_provenance(self):
        g=graph('MOVQ BX, 0x8(SP)','CALL external.maybeWrite(SB)',
                'MOVQ $0x7, 0x8(SP)','MOVQ 0x8(SP), CX','MOVQ CX, 0(DI)','RET')
        s=g['stores'][0]
        self.assertFalse(s['value_stack_blockers'])
        self.assertEqual(self.kinds(g,s['value_inputs']),{'constant'})

    def test_branch_with_unknown_call_keeps_unknown_alternative(self):
        g=graph('MOVQ BX, 0x8(SP)','TESTQ AX, AX','JE 0x1007',
                'CALL external.maybeWrite(SB)','MOVQ 0x8(SP), CX','MOVQ CX, 0(DI)','RET')
        self.assertEqual(self.kinds(g,g['stores'][0]['value_inputs']),{'entry','unknown_stack_effect'})

    def test_loop_does_not_erase_unknown_writer(self):
        g=graph('MOVQ BX, 0x8(SP)','MOVQ 0x8(SP), CX','CALL external.maybeWrite(SB)',
                'TESTQ AX, AX','JNE 0x1004','MOVQ 0x8(SP), CX','MOVQ CX, 0(DI)','RET')
        self.assertTrue(g['stores'][0]['value_stack_blockers'])

    def test_runtime_allocator_contract_is_reported(self):
        g=graph('MOVQ BX, 0x8(SP)','CALL runtime.newobject(SB)',
                'MOVQ 0x8(SP), CX','MOVQ CX, 0(AX)','RET')
        self.assertEqual(terminals(g,g['stores'][0]['value_inputs']),['entry:BX'])
        self.assertIn('runtime.newobject',g['obligations']['trusted_runtime_contracts'])
        self.assertFalse(g['obligations']['stack_alias_contract_verified'])

    def test_barrier_buffer_bounds_are_checked(self):
        for offset,expect_unknown in ((8,False),(16,True),(-8,True)):
            with self.subTest(offset=offset):
                g=graph('MOVQ BX, 0x8(SP)','CALL runtime.gcWriteBarrier2(SB)',
                        f'MOVQ BX, {offset}(R11)','MOVQ 0x8(SP), CX','MOVQ CX, 0(AX)','RET')
                self.assertEqual(bool(g['stores'][-1]['value_stack_blockers']),expect_unknown)

    def test_barrier_identity_lost_across_unknown_call_not_trusted(self):
        g=graph('CALL runtime.gcWriteBarrier2(SB)','MOVQ R11, 0x8(SP)',
                'CALL external.maybeWrite(SB)','MOVQ 0x8(SP), R11','MOVQ AX, 0(R11)','RET')
        self.assertIn(g['stores'][0]['address'],[e['address'] for e in g['memory_effects']])

    def test_unknown_in_address_chain_is_reported(self):
        g=graph('MOVQ BX, 0x8(SP)','CALL external.maybeWrite(SB)',
                'MOVQ 0x8(SP), CX','MOVQ 0(CX), DX','MOVQ DX, 0(AX)','RET')
        self.assertEqual(self.kinds(g,g['stores'][0]['value_inputs']),{'heap_load'})
        self.assertTrue(g['stores'][0]['value_stack_blockers'])


class RealStackEffectsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path=Path(__file__).parent/'fixtures'/'checkout-default-prepOrderItems.asm'
        cls.g=analyze(assembly_rows(path.read_text()),'prepOrderItems')

    def test_item_and_publication_are_no_longer_silently_proved(self):
        g=self.g
        item=next(s for s in g['stores'] if s['asm']=='MOVQ R10, 0x28(AX)')
        self.assertTrue(item['value_stack_blockers'])
        publish=next(s for s in g['stores'] if s['asm']=='MOVQ AX, 0(R8)(DX*8)')
        self.assertTrue(publish['address_stack_blockers'])

    def test_cost_return_survives_explicit_save_and_runtime_contract(self):
        g=self.g
        cost=next(s for s in g['stores'] if s['asm']=='MOVQ R12, 0x30(AX)')
        self.assertFalse(cost['value_stack_blockers'])
        ns=[g['nodes'][k] for k in terminals(g,cost['value_inputs'])]
        self.assertEqual(len(ns),1)
        self.assertTrue(ns[0]['callee'].endswith('.convertCurrency'))


if __name__=='__main__':
    unittest.main()
