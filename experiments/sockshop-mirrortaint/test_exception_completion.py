import unittest
from control_dependencies import Control,ControlFlow
from execution_dependency_state import Frame,State,Value

G=frozenset({('field',1,0)});P=frozenset({('field',2,0)});I=frozenset({('field',3,0)})

def source(n,origins):return Value({'value':n},origins)

class CompletionTests(unittest.TestCase):
    def control(self,ins,state=None):
        m={'owner':'T','name':'root','desc':'()V','access':8,'try_catches':1,'exception_handlers':[{'start':0,'end':1,'handler':1,'type':None}],'instructions':[ins,{'op':177}]}
        f=Frame('f');s=state or State(f);c=Control(ControlFlow(m),f,s,lambda v:v.observed.get('object'));return f,s,c
    def call(self):return self.control({'op':182,'owner':'C','name':'work','desc':'(II)V'})
    def test_callee_condition_not_all_payload_parameters(self):
        f,s,c=self.call();c.consumed=[source(1,G),source(7,P),Value({'object':'recv'})];s.exception_control=Value(selectors=G);s.exception_control_ready=True
        c.caught(1);self.assertEqual(c.current().selectors,G);self.assertFalse(c.current().unknown)
    def test_empty_completion_proof_is_not_missing_proof(self):
        f,s,c=self.call();c.consumed=[source(7,P),Value({'object':'recv'})];s.exception_control_ready=True
        c.caught(1);self.assertFalse(c.current().selectors);self.assertFalse(c.current().unknown)
    def test_unexplained_nonnull_call_does_not_invent_known_selectors(self):
        f,s,c=self.call();c.consumed=[source(7,P),Value({'object':'recv'})]
        c.caught(1);self.assertTrue(c.current().unknown);self.assertFalse(c.current().selectors)
    def test_null_receiver_is_callsite_guard_without_callee(self):
        f,s,c=self.call();c.consumed=[source(7,P),source(None,G)]
        c.caught(1,'java.lang.NullPointerException');self.assertEqual(c.current().selectors,G);self.assertFalse(c.current().unknown)
    def test_putfield_payload_is_not_null_receiver_guard(self):
        f,s,c=self.control({'op':181});c.consumed=[source(7,P),source(None,G)]
        c.caught(1,'java.lang.NullPointerException');self.assertEqual(c.current().selectors,G)
    def test_getfield_receiver_source_is_guard(self):
        f,s,c=self.control({'op':180});c.consumed=[source(None,G)]
        c.caught(1,'java.lang.NullPointerException');self.assertEqual(c.current().selectors,G)
    def test_null_array_excludes_index_and_stored_value(self):
        f,s,c=self.control({'op':83});c.consumed=[source(None,P),source(2,I),source(None,G)]
        c.caught(1,'java.lang.NullPointerException');self.assertEqual(c.current().selectors,G)
    def test_array_bounds_excludes_stored_payload(self):
        f,s,c=self.control({'op':83});c.consumed=[source(None,P),source(2,I),Value({'object':'array'},selectors=G)]
        c.caught(1,'java.lang.ArrayIndexOutOfBoundsException');self.assertEqual(c.current().selectors,G|I)
    def test_array_type_guard_retains_stored_reference_choice(self):
        f,s,c=self.control({'op':83});c.consumed=[Value({'object':'item'},selectors=P),source(0,I),Value({'object':'array'},selectors=G)]
        c.caught(1,'java.lang.ArrayStoreException');self.assertEqual(c.current().selectors,G|I|P)
    def test_negative_size_uses_size_source(self):
        f,s,c=self.control({'op':189});c.consumed=[source(-1,I)]
        c.caught(1,'java.lang.NegativeArraySizeException');self.assertEqual(c.current().selectors,I)
    def test_guard_unknown_survives_concrete_exception(self):
        f,s,c=self.control({'op':180});c.consumed=[Value({'value':None},unknown=True)]
        c.caught(1,'java.lang.NullPointerException');self.assertTrue(c.current().unknown)
    def test_explicit_throw_uses_exception_reference_not_unrelated_payload(self):
        f,s,c=self.control({'op':191});c.consumed=[Value({'object':'original'},selectors=G)]
        c.abort();self.assertEqual(s.exception_control.selectors,G);self.assertTrue(s.exception_control_ready)
    def test_nested_abort_keeps_callee_proof_without_readding_arguments(self):
        f,s,c=self.call();c.consumed=[source(7,P),Value({'object':'recv'})];s.exception_control=Value(selectors=G);s.exception_control_ready=True
        c.abort();self.assertEqual(s.exception_control.selectors,G)
    def test_catch_consumes_pending_state_and_join_cleans_scope(self):
        f,s,c=self.call();c.consumed=[Value({'object':'recv'})];s.exception_control=Value(selectors=G);s.exception_control_ready=True
        c.caught(1);self.assertFalse(s.exception_control_ready);self.assertFalse(s.exception_control.selectors)
        c.at(c.graph.exit);self.assertFalse(c.current().selectors)
    def test_stale_unready_state_is_not_used(self):
        f,s,c=self.control({'op':180});s.exception_control=Value(selectors=P);c.consumed=[source(None,G)]
        c.caught(1,'java.lang.NullPointerException');self.assertEqual(c.current().selectors,G)
    def test_verified_library_guard_excludes_message_payload(self):
        f,s,c=self.control({'op':184,'owner':'Library','name':'check','desc':'(II)V'});c.consumed=[source(7,P),source(1,G)];c.verified_exception_guard=Value(selectors=G)
        c.caught(1);self.assertEqual(c.current().selectors,G);self.assertFalse(c.current().unknown)
    def test_operation_guard_is_cleared_before_next_instruction(self):
        f,s,c=self.control({'op':180});c.verified_exception_guard=Value(selectors=P);c.exception_type='old';c.at(0)
        self.assertIsNone(c.verified_exception_guard);self.assertIsNone(c.exception_type)
    def test_unknown_callee_completion_remains_unknown(self):
        f,s,c=self.call();c.consumed=[source(7,P),Value({'object':'recv'})];s.exception_control=Value(selectors=G,unknown=True);s.exception_control_ready=True
        c.caught(1);self.assertEqual(c.current().selectors,G);self.assertTrue(c.current().unknown)

    def test_missing_required_guard_operand_rejects(self):
        f,s,c=self.control({'op':180})
        with self.assertRaises(ValueError):c.caught(1,'java.lang.NullPointerException')
    def test_null_call_cannot_claim_a_different_exception(self):
        f,s,c=self.call();c.consumed=[source(7,P),source(None,G)]
        with self.assertRaises(ValueError):c.caught(1,'java.lang.IllegalArgumentException')

    def test_ambient_scope_marker_is_not_an_independent_null_condition(self):
        from control_dependencies import Region
        f,s,c=self.control({'op':180});c.regions.append(Region(-1,1,Value(selectors=G),set(),0))
        v=c.apply(Value({'object':'stable'}));self.assertEqual(v.selectors,G)
        self.assertFalse(c.guard_selection([v]).selectors)
    def test_intrinsic_alias_selection_is_not_removed_with_ambient_context(self):
        from control_dependencies import Region
        f,s,c=self.control({'op':180});c.regions.append(Region(-1,1,Value(selectors=G),set(),0))
        v=c.apply(Value({'object':'selected'},selectors=G))
        self.assertEqual(c.guard_selection([v]).selectors,G)
    def test_merge_seals_choice_in_local_after_scope_ends(self):
        from control_dependencies import Region
        f,s,c=self.control({'op':180});c.regions.append(Region(-1,1,Value(selectors=G),{0},0));f.locals[0]=Value({'object':'selected'})
        c.at(1);self.assertFalse(c.current().selectors);self.assertEqual(c.guard_selection([f.locals[0]]).selectors,G)
    def test_transient_tracking_does_not_accumulate_dead_values(self):
        from control_dependencies import Region
        f,s,c=self.control({'op':180});c.regions.append(Region(-1,1,Value(selectors=G),set(),0))
        for _ in range(20):c.apply(Value({'object':'temporary'}))
        c.at(0);self.assertFalse(c.ambient)
    def test_unknown_is_not_cleared_as_ambient_annotation(self):
        from control_dependencies import Region
        f,s,c=self.control({'op':180});c.regions.append(Region(-1,1,Value(selectors=G),set(),0))
        self.assertTrue(c.guard_selection([c.apply(Value({'object':'o'},unknown=True))]).unknown)
    def test_typed_completion_uses_first_covering_catch_before_finally(self):
        from exception_completion import handler_partition
        h=[{'handler':3,'type':'java/lang/IllegalArgumentException'},{'handler':5,'type':None}]
        self.assertEqual(handler_partition(h,{'java/lang/IllegalArgumentException'}),({3},set()))
    def test_unknown_type_cannot_exclude_finally(self):
        from exception_completion import handler_partition
        h=[{'handler':3,'type':'java/lang/IllegalArgumentException'},{'handler':5,'type':None}]
        self.assertEqual(handler_partition(h,None),({3,5},set()))
    def test_different_exception_categories_keep_different_guards(self):
        f,s,c=self.control({'op':0});c.graph.method['exception_handlers']=[]
        c.normal_outcome(Value(selectors=G),exception_types={'java/lang/NullPointerException'})
        c.normal_outcome(Value(selectors=I),exception_types={'java/lang/ArrayIndexOutOfBoundsException'})
        channels={next(iter(t)):v.selectors for v,t in c.normal_completions()}
        self.assertEqual(channels,{'java/lang/NullPointerException':G,'java/lang/ArrayIndexOutOfBoundsException':I})

if __name__=='__main__':unittest.main()
