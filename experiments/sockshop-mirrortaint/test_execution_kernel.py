import unittest
from execution_dependency_state import Value, Frame, State
from plan_collection_service import analyze
from plan_execution_kernel import constructor_writes


class ExecutionKernelTests(unittest.TestCase):
    def test_loop_definitions_reach_fixed_point_without_path_enumeration(self):
        code=[{'op':3},{'op':54,'var':1},{'op':21,'var':1},{'op':21,'var':0},
              {'op':162,'target':7},{'op':132,'var':1,'increment':1},{'op':167,'target':2},
              {'op':21,'var':1},{'op':172}]
        method={'access':8,'desc':'(I)I','try_catches':0,'exception_handlers':[],'instructions':[dict(index=i,**x) for i,x in enumerate(code)]}
        deps,operands,states,steps=analyze(method,allow_loops=True)
        self.assertEqual(len(states),len(code));self.assertLess(steps,len(code)**2)
        self.assertEqual(operands[2][0],frozenset({0,5}))
        with self.assertRaisesRegex(ValueError,'Unsupported instruction|Loops/back edges'):analyze(method)

    def test_constructor_with_hidden_write_or_call_not_summarized(self):
        method={'desc':'(Ljava/lang/String;)V','instructions':[{'op':25,'var':0},{'op':183,'owner':'java/lang/Object','name':'<init>','desc':'()V'},
            {'op':25,'var':0},{'op':25,'var':1},{'op':181,'owner':'Box','name':'text','desc':'Ljava/lang/String;'},{'op':177}]}
        self.assertEqual(constructor_writes(method),{'Box.text':0})
        method['instructions'].insert(-1,{'op':184,'owner':'External','name':'effect','desc':'()V'})
        with self.assertRaisesRegex(ValueError,'constructor effects'):constructor_writes(method)

    def test_actual_field_versions_keep_overwrites_separate(self):
        state=State(Frame('root'));source=Value({'value':'same'},frozenset({('first',0)}))
        state.field_write(('o1','Box.text',1),source)
        state.field_write(('o1','Box.text',2),Value({'value':'same'}))
        self.assertEqual(state.fields[('o1','Box.text',1)].origins,source.origins)
        self.assertEqual(state.fields[('o1','Box.text',2)].origins,frozenset())
        with self.assertRaisesRegex(ValueError,'Duplicate actual field version'):state.field_write(('o1','Box.text',2),source)

    def test_opaque_reference_effect_cannot_be_certified_from_equal_values(self):
        state=State(Frame('root'));state.opaque_effect([Value({'object':'o1'}),Value({'object':'boxed','value':'same'})])
        self.assertEqual(state.poisoned,{'o1'})


if __name__=='__main__':unittest.main()
