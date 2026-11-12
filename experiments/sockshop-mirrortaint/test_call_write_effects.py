import unittest
from analysis_status import AnalysisLimit
from call_write_effects import WriteEffects,Path
from control_dependencies import Control,ControlFlow,field_selection
from execution_dependency_state import Frame,State,Value

FROZEN=frozenset({('field',7,0)})

def method(code,desc='(LHolder;)V',access=8,owner='T',name='update'):
    return dict(owner=owner,name=name,desc=desc,access=access,try_catches=0,exception_handlers=[],instructions=code)

def nested(slot=0):
    return [{'op':25,'var':slot},{'op':180,'owner':'Holder','name':'child','desc':'LChild;'},
            {'op':4},{'op':181,'owner':'Child','name':'value','desc':'I'},{'op':177}]

class FootprintTests(unittest.TestCase):
    def setup(self,callee=None,args=('h',),desc='(LHolder;)V',code=None,targets=None):
        code=code or [{'op':3},{'op':153,'target':len(args)+3},*[{'op':25,'var':i}for i in range(len(args))],
                      {'op':184,'owner':'T','name':'update','desc':desc},{'op':177}]
        root=method(code,'('+''.join('LHolder;'for _ in args)+')V',name='root')
        f=Frame('unit');s=State(f)
        c=Control(ControlFlow(root),f,s,lambda v:v.observed.get('object'),callee or {'T.update'+desc:method(nested(),desc)},call_targets=targets)
        for i,o in enumerate(args):f.locals[i]=Value({'object':o})
        f.pc=1;c.at(0)
        return f,s,c

    def branch(self,f,c):c.branch(c.graph.code[1],[Value({'value':0},FROZEN)],{'taken':True,'seq':20})
    def link(self,s,o='h',child='child',version=1):s.field_write((o,'Holder.child',version),Value({'object':child}))
    def test_original_nested_counterexample(self):
        f,s,c=self.setup();self.link(s);self.branch(f,c)
        self.assertEqual(set(s.control_fields),{('child','Child.value')})
        self.assertEqual(field_selection(s,('child','Child.value',1),Value({'value':7})).selectors,FROZEN)
    def test_direct_write_does_not_mark_ignored_actual(self):
        desc='(LHolder;LHolder;)V'
        m=method([{'op':25,'var':1},{'op':4},{'op':181,'owner':'Holder','name':'value','desc':'I'},{'op':177}],desc)
        f,s,c=self.setup({'T.update'+desc:m},('first','second'),desc);self.branch(f,c)
        self.assertEqual(set(s.control_fields),{('second','Holder.value')})
    def test_argument_permutation_across_two_calls(self):
        desc='(LHolder;LHolder;)V'
        outer=method([{'op':25,'var':1},{'op':184,'owner':'T','name':'inner','desc':'(LHolder;)V'},{'op':177}],desc)
        f,s,c=self.setup({'T.update'+desc:outer,'T.inner(LHolder;)V':method(nested())},('ignored','h'),desc)
        self.link(s);self.branch(f,c);self.assertEqual(set(s.control_fields),{('child','Child.value')})
    def test_local_alias_in_callee(self):
        m=method([{'op':25,'var':0},{'op':58,'var':1},*nested(1)])
        f,s,c=self.setup({'T.update(LHolder;)V':m});self.link(s);self.branch(f,c)
        self.assertEqual(set(s.control_fields),{('child','Child.value')})
    def test_deeper_field_path(self):
        m=method([{'op':25,'var':0},{'op':180,'owner':'Holder','name':'child','desc':'LChild;'},
                  {'op':180,'owner':'Child','name':'next','desc':'LChild;'},*nested()[2:]])
        f,s,c=self.setup({'T.update(LHolder;)V':m});self.link(s);s.field_write(('child','Child.next',1),Value({'object':'deep'}));self.branch(f,c)
        self.assertEqual(set(s.control_fields),{('deep','Child.value')})
    def test_instance_receiver_and_wide_descriptor_slots(self):
        desc='(JLHolder;DLHolder;)V'
        m=method(nested(6),desc,0)
        effects=WriteEffects({'Worker.update'+desc:m},lambda m,p:(),())
        writes,unknown=effects.summary('Worker.update'+desc)
        self.assertEqual(writes,{Path(3,(('Holder.child','LChild;'),('Child.value','I')))})
        self.assertFalse(unknown)
    def test_interface_union_preserves_actual_parameter_mapping(self):
        code=[{'op':3},{'op':153,'target':6},{'op':25,'var':0},{'op':25,'var':1},{'op':25,'var':2},
              {'op':185,'owner':'Api','name':'apply','desc':'(LHolder;LHolder;)V'},{'op':177}]
        desc='(LHolder;LHolder;)V'
        a=method(nested(1),desc,0,'A','apply');b=method(nested(2),desc,0,'B','apply')
        f,s,c=self.setup({'A.apply'+desc:a,'B.apply'+desc:b},('worker','h1','h2'),code=code,
                         targets={'T.root(LHolder;LHolder;LHolder;)V@5':['A.apply'+desc,'B.apply'+desc]})
        self.link(s,'h1','c1');self.link(s,'h2','c2');self.branch(f,c)
        self.assertEqual(set(s.control_fields),{('c1','Child.value'),('c2','Child.value')})
    def test_missing_link_not_replaced_by_future_read(self):
        f,s,c=self.setup()
        with self.assertRaises(AnalysisLimit):self.branch(f,c)
        self.assertFalse(s.control_fields)
    def test_poisoned_link_rejects(self):
        f,s,c=self.setup();self.link(s);s.poisoned.add('h')
        with self.assertRaises(AnalysisLimit):self.branch(f,c)
    def test_unknown_link_rejects(self):
        f,s,c=self.setup();s.field_write(('h','Holder.child',1),Value({'object':'child'},unknown=True))
        with self.assertRaises(AnalysisLimit):self.branch(f,c)
    def test_null_link_rejects(self):
        f,s,c=self.setup();s.field_write(('h','Holder.child',1),Value({'value':None}))
        with self.assertRaises(AnalysisLimit):self.branch(f,c)
    def test_rewritten_path_edge_rejects(self):
        m=method([{'op':25,'var':0},{'op':1},{'op':181,'owner':'Holder','name':'child','desc':'LChild;'},*nested()])
        f,s,c=self.setup({'T.update(LHolder;)V':m});self.link(s)
        with self.assertRaises(AnalysisLimit):self.branch(f,c)
        self.assertFalse(s.control_fields)
    def test_alias_across_formals_detects_rewritten_edge(self):
        desc='(LHolder;LHolder;)V'
        m=method([{'op':25,'var':0},{'op':1},{'op':181,'owner':'Holder','name':'child','desc':'LChild;'},*nested(1)],desc)
        f,s,c=self.setup({'T.update'+desc:m},('h','h'),desc);self.link(s)
        with self.assertRaises(AnalysisLimit):self.branch(f,c)
    def test_distinct_actuals_do_not_manufacture_edge_conflict(self):
        desc='(LHolder;LHolder;)V'
        m=method([{'op':25,'var':0},{'op':1},{'op':181,'owner':'Holder','name':'child','desc':'LChild;'},*nested(1)],desc)
        f,s,c=self.setup({'T.update'+desc:m},('other','h'),desc);self.link(s);self.branch(f,c)
        self.assertEqual(set(s.control_fields),{('other','Holder.child'),('child','Child.value')})
    def test_unknown_nested_call_cannot_certify_path(self):
        m=method([{'op':184,'owner':'External','name':'touch','desc':'()V'},*nested()])
        f,s,c=self.setup({'T.update(LHolder;)V':m});self.link(s)
        c.write_effects.opaque={'External.touch()V'}
        with self.assertRaises(AnalysisLimit):self.branch(f,c)
    def test_returned_alias_is_explicit_limit(self):
        m=method([{'op':25,'var':0},{'op':184,'owner':'T','name':'helper','desc':'(LHolder;)LChild;'},
                  {'op':4},{'op':181,'owner':'Child','name':'value','desc':'I'},{'op':177}])
        f,s,c=self.setup({'T.update(LHolder;)V':m});self.link(s)
        with self.assertRaises(AnalysisLimit):self.branch(f,c)
    def test_reference_read_is_prior_state_not_whole_trace_lookup(self):
        f,s,c=self.setup();s.reference_reads.append((('h','Holder.child',1),Value({'object':'child'}),10));self.branch(f,c)
        self.assertIn(('child','Child.value'),s.control_fields)
    def test_disagreeing_same_version_read_rejects(self):
        f,s,c=self.setup();self.link(s);s.reference_reads.append((('h','Holder.child',1),Value({'object':'different'}),10))
        with self.assertRaises(AnalysisLimit):self.branch(f,c)
    def test_frame_formals_are_not_rebound_by_local_assignment(self):
        f,s,c=self.setup();self.link(s);f.locals[0]=Value({'object':'new'})
        # Actual ALOAD uses current local; callee never resolves against a root
        # formal ordinal without the call-site operand binding.
        self.link(s,'new','newchild');self.branch(f,c)
        self.assertEqual(set(s.control_fields),{('newchild','Child.value')})

    def test_future_reference_witness_cannot_close_earlier_branch(self):
        f,s,c=self.setup();s.reference_reads.append((('h','Holder.child',1),Value({'object':'child'}),21))
        with self.assertRaises(AnalysisLimit):self.branch(f,c)
        self.assertFalse(s.control_fields)
    def test_missing_interface_candidate_does_not_silently_disappear(self):
        f,s,c=self.setup();self.link(s)
        c.call_targets={'T.root(LHolder;)V@3':['Missing.update(LHolder;)V']}
        with self.assertRaises(AnalysisLimit):self.branch(f,c)
    def test_actual_aliases_deduplicate_physical_cell_without_value_pairing(self):
        desc='(LHolder;LHolder;)V'
        m=method(nested(0)[:-1]+nested(1),desc)
        f,s,c=self.setup({'T.update'+desc:m},('h','h'),desc);self.link(s);self.branch(f,c)
        self.assertEqual(set(s.control_fields),{('child','Child.value')})
    def test_missing_one_of_multiple_paths_is_atomic(self):
        desc='(LHolder;LHolder;)V'
        m=method(nested(0)[:-1]+nested(1),desc)
        f,s,c=self.setup({'T.update'+desc:m},('h','missing'),desc);self.link(s)
        with self.assertRaises(AnalysisLimit):self.branch(f,c)
        self.assertFalse(s.control_fields)
    def test_write_free_recursion_has_no_invented_field_effect(self):
        m=method([{'op':25,'var':0},{'op':184,'owner':'T','name':'update','desc':'(LHolder;)V'},{'op':177}])
        f,s,c=self.setup({'T.update(LHolder;)V':m});self.branch(f,c)
        self.assertFalse(s.control_fields)
    def test_recursive_write_footprint_is_not_closed(self):
        m=method(nested()[:-1]+[{'op':25,'var':0},{'op':184,'owner':'T','name':'update','desc':'(LHolder;)V'},{'op':177}])
        f,s,c=self.setup({'T.update(LHolder;)V':m});self.link(s)
        with self.assertRaises(AnalysisLimit):self.branch(f,c)
    def test_static_cycle_in_reference_address_is_not_silently_skipped(self):
        f,s,c=self.setup();self.link(s)
        # The public resolver must reject a def cycle even if another candidate
        # receiver is concrete; a partial set is not a closed footprint.
        with self.assertRaises(AnalysisLimit):c._receivers({2},set(),20,set(),(2,))

    def test_dynamic_bootstrap_is_not_a_closed_empty_effect(self):
        m=method([{'op':186,'desc':'()Ljava/lang/Runnable;'},{'op':87},{'op':177}])
        f,s,c=self.setup({'T.update(LHolder;)V':m});self.branch(f,c)
        self.assertTrue(s.control_barriers)
        self.assertTrue(field_selection(s,('child','Child.value',1),Value({'value':7}),1).unknown)
    def test_bodyless_method_is_not_a_closed_empty_effect(self):
        m=method([])
        effects=WriteEffects({'T.update(LHolder;)V':m},lambda m,p:(),())
        self.assertEqual(effects.summary('T.update(LHolder;)V')[1],{'T.update(LHolder;)V'})

if __name__=='__main__':unittest.main()
