"""Static graph tests; these are not BPF capture or dynamic accuracy tests."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from go_byte_adapter import assembly_rows
from go_object_graph import analyze, terminals


def sample(*instructions):
    return [dict(address=0x1000+i,code='90',asm=asm) for i,asm in enumerate(instructions)]


class ObjectGraphTests(unittest.TestCase):
    def graph(self,*body):
        # Historical conditional graph remains a diagnostic comparison only.
        return analyze(sample('PUSHQ BP','MOVQ SP, BP','SUBQ $0x20, SP',*body),'fixture',stack_policy='assume_private')

    def test_overwrite_kills_previous_source(self):
        g=self.graph('MOVQ AX, 0x8(SP)','MOVQ BX, 0x8(SP)',
                     'MOVQ 0x8(SP), CX','MOVQ CX, 0(DI)','RET')
        self.assertEqual(terminals(g,g['stores'][0]['value_inputs']),['entry:BX'])

    def test_branch_retains_both_sources(self):
        g=self.graph('TESTQ AX, AX','JE 0x1007','MOVQ BX, CX',
                     'JMP 0x1008','MOVQ DI, CX','MOVQ CX, 0(SI)','RET')
        self.assertEqual(terminals(g,g['stores'][0]['value_inputs']),['entry:BX','entry:DI'])

    def test_loop_reaches_fixed_point_without_enumeration(self):
        g=self.graph('XORL CX, CX','MOVQ 0(DI)(CX*8), AX',
                     'MOVQ AX, 0(SI)(CX*8)','LEAQ 0x1(CX), CX',
                     'CMPQ CX, BX','JL 0x1004','RET')
        store=g['stores'][0]
        self.assertEqual(len(terminals(g,store['value_inputs'])),1)
        self.assertEqual(len(terminals(g,store['index_inputs'])),2)

    def test_call_result_does_not_inherit_all_arguments(self):
        g=self.graph('MOVQ BX, DI','CALL example.transform(SB)','MOVQ AX, 0(SI)','RET')
        ids=terminals(g,g['stores'][0]['value_inputs'])
        self.assertEqual(len(ids),1)
        self.assertEqual(g['nodes'][ids[0]]['kind'],'opaque_call_result')
        self.assertEqual(g['nodes'][ids[0]]['inputs'],[])
        self.assertFalse(g['obligations']['runtime_capture_complete'])

    def test_gc_barrier_preserves_gprs_but_not_buffer_register(self):
        g=self.graph('MOVQ BX, CX','CALL runtime.gcWriteBarrier2(SB)',
                     'MOVQ CX, 0(AX)','MOVQ R11, 0x8(AX)','RET')
        self.assertEqual(terminals(g,g['stores'][0]['value_inputs']),['entry:BX'])
        k=terminals(g,g['stores'][1]['value_inputs'])[0]
        self.assertEqual(g['nodes'][k]['kind'],'barrier_buffer')

    def test_ordinary_call_clobbers_register_origin(self):
        g=self.graph('MOVQ BX, CX','CALL example.external(SB)','MOVQ CX, 0(SI)','RET')
        k=terminals(g,g['stores'][0]['value_inputs'])[0]
        self.assertEqual(g['nodes'][k]['kind'],'call_clobber')

    def test_constant_store_is_not_unknown_or_missing_source(self):
        g=self.graph('MOVQ $0x7, 0(AX)','RET')
        k=terminals(g,g['stores'][0]['value_inputs'])[0]
        self.assertEqual(g['nodes'][k]['value'],7)

    def test_unknown_instruction_and_indirect_call_rejected(self):
        for op in ('XCHGQ AX, BX','CALL CX','MOVL AX, 0x8(SP)','MOVQ AX, 0x9(SP)'):
            with self.subTest(op=op),self.assertRaises(ValueError):
                self.graph(op,'RET')

    def test_stack_address_escape_remains_explicit_obligation(self):
        g=self.graph('MOVQ BX, 0x8(SP)','LEAQ 0x8(SP), AX','CALL example.mutate(SB)',
                     'MOVQ 0x8(SP), CX','MOVQ CX, 0(DI)','RET')
        self.assertEqual(g['status'],'conditional_static_candidates')
        self.assertEqual(g['obligations']['stack_addresses'][0]['offset'],8)
        self.assertIn('validation required',g['obligations']['call_memory_effects'])

    def test_modified_argument_in_prologue_rejected(self):
        with self.assertRaisesRegex(ValueError,'argument registers'):
            analyze(sample('MOVQ AX, DI','SUBQ $0x20, SP','RET'),'bad')


class RealCheckoutGraphTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.graphs={}
        for name in ('prepOrderItems','convertCurrency'):
            asm=(Path(__file__).parent/'fixtures'/('checkout-default-'+name+'.asm')).read_text()
            cls.graphs[name]=analyze(assembly_rows(asm),name,stack_policy='assume_private')

    def test_order_pointer_stores_and_publication(self):
        g=self.graphs['prepOrderItems']
        # These assertions are independent expected answers from source audit,
        # not configuration consumed by analyze(). Offsets match DWARF checks
        # performed separately against the original ELF.
        def allocated(s):
            return any(g['nodes'][k]['kind']=='allocation' for k in terminals(g,s['base_inputs']))
        cost=[s for s in g['stores'] if s['memory']['offset']==48 and allocated(s)
              and any('convertCurrency' in g['nodes'][k].get('callee','') for k in terminals(g,s['value_inputs']))]
        self.assertEqual(len(cost),1)
        base=terminals(g,cost[0]['base_inputs'])
        item=[s for s in g['stores'] if s['memory']['offset']==40 and terminals(g,s['base_inputs'])==base]
        self.assertEqual(len(item),1)
        load=g['nodes'][terminals(g,item[0]['value_inputs'])[0]]
        self.assertEqual(load['kind'],'heap_load')
        self.assertEqual(load['memory']['scale'],8)
        self.assertEqual(terminals(g,load['base_inputs']),['entry:DI'])
        publish=[s for s in g['stores'] if s['memory']['index'] and terminals(g,s['value_inputs'])==base]
        self.assertEqual(len(publish),1)
        self.assertEqual(terminals(g,publish[0]['index_inputs']),terminals(g,load['index_inputs']))

    def test_product_price_argument_retains_nil_alternative(self):
        g=self.graphs['prepOrderItems']
        call=next(c for c in g['calls'] if c['callee'].endswith('.convertCurrency'))
        ns=[g['nodes'][k] for k in terminals(g,call['arguments']['DI'])]
        self.assertEqual({n['kind'] for n in ns},{'heap_load','constant'})
        load=next(n for n in ns if n['kind']=='heap_load')
        self.assertEqual(load['memory']['offset'],104)
        base=[g['nodes'][k] for k in terminals(g,load['base_inputs'])]
        self.assertEqual(len(base),1)
        self.assertTrue(base[0]['callee'].endswith('.GetProduct'))

    def test_conversion_request_from_and_success_return(self):
        g=self.graphs['convertCurrency']
        stores=[s for s in g['stores'] if s['memory']['offset']==40 and s['memory']['base']=='AX']
        self.assertEqual(len(stores),1)
        self.assertEqual(terminals(g,stores[0]['value_inputs']),['entry:DI'])
        call=next(c for c in g['calls'] if c['callee'].endswith('.Convert'))
        self.assertEqual(terminals(g,call['arguments']['DI']),terminals(g,stores[0]['base_inputs']))
        rets=[g['nodes'][k] for r in g['returns'] for k in terminals(g,r['registers']['AX'])]
        self.assertEqual({r['kind'] for r in rets},{'constant','opaque_call_result'})
        self.assertTrue(any(r.get('callee','').endswith('.Convert') for r in rets))

    def test_changing_real_spill_changes_extracted_dependency(self):
        path=Path(__file__).parent/'fixtures'/'checkout-default-prepOrderItems.asm'
        rows=assembly_rows(path.read_text())
        spill=[r for r in rows if r['asm']=='MOVQ AX, 0x58(SP)']
        self.assertEqual(len(spill),1)
        # Synthetic decoder-level mutation, not claimed to match the ELF.
        spill[0]['asm']='MOVQ $0x0, 0x58(SP)'
        g=analyze(rows,'mutated',stack_policy='assume_private')
        store=next(s for s in g['stores'] if s['asm']=='MOVQ R12, 0x30(AX)')
        ns=[g['nodes'][k] for k in terminals(g,store['value_inputs'])]
        self.assertEqual(len(ns),1)
        self.assertEqual(ns[0]['kind'],'constant')
        self.assertEqual(ns[0]['value'],0)


if __name__=='__main__':
    unittest.main()
