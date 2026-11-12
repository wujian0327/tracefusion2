import unittest
from control_dependencies import ControlFlow,Control,selection,selected,field_selection
from execution_dependency_state import Value,Frame,State
from infer_execution_kernel import infer_execution


class ControlTests(unittest.TestCase):
    def method(self, code):
        return {'instructions':code,'access':8,'desc':'()V','exception_handlers':[],'try_catches':0}

    def setup_control(self, code):
        f=Frame('unit');s=State(f);c=Control(ControlFlow(self.method(code)),f,s,lambda v:v.observed.get('object'))
        return f,s,c

    def test_constant_data_not_condition_data(self):
        source=Value({'value':1},frozenset({('field',1,0)}),frozenset({('field',2,0)}))
        out=selected(Value({'value':7}),selection([source]))
        self.assertFalse(out.origins);self.assertEqual(out.selectors,source.origins|source.selectors)

    def test_known_number_unknown_dependency(self):
        out=selected(Value({'value':7}),selection([Value({'value':1},unknown=True)]))
        self.assertTrue(out.unknown)

    def test_false_arm_local_phi_and_join_cleanup(self):
        f,s,c=self.setup_control([{'op':153,'target':3},{'op':3},{'op':54,'var':0},{'op':177}])
        f.locals[0]=Value({'value':7},frozenset({('field',1,0)}))
        c.branch({'op':153,'target':3},[Value({'value':0},frozenset({('field',2,0)}))],{'taken':True})
        c.at(3)
        self.assertEqual(f.locals[0].selectors,frozenset({('field',2,0)}))
        self.assertFalse(c.apply(Value({'value':9})).selectors)

    def test_ternary_stack_phi(self):
        f,s,c=self.setup_control([{'op':153,'target':3},{'op':4},{'op':167,'target':4},{'op':5},{'op':172}])
        c.branch({'op':153,'target':3},[Value({'value':0},frozenset({('field',3,0)}))],{'taken':True})
        f.stack.append(Value({'value':2}));c.at(4)
        self.assertEqual(f.pop().selectors,frozenset({('field',3,0)}))
        self.assertFalse(c.current().selectors)

    def test_loop_scope_is_iteration_union_not_frame_union(self):
        f,s,c=self.setup_control([{'op':153,'target':3},{'op':132,'var':0,'increment':1},{'op':167,'target':0},{'op':177}])
        f.locals[0]=Value({'value':0})
        c.branch({'op':153,'target':3},[Value({'value':1},frozenset({('field',1,0)}))],{'taken':False})
        c.at(0)
        c.branch({'op':153,'target':3},[Value({'value':0},frozenset({('field',2,0)}))],{'taken':True})
        self.assertEqual(len(c.regions),1);c.at(3)
        self.assertEqual(f.locals[0].selectors,frozenset({('field',1,0),('field',2,0)}))
        self.assertFalse(c.current().selectors)

    def test_unconditional_write_clears_old_conditional_phi(self):
        f,s,c=self.setup_control([{'op':177}]);dep=Value(selectors=frozenset({('field',1,0)}))
        s.control_fields[('object','T.value')]=dep
        self.assertEqual(field_selection(s,('object','T.value',1),Value({'value':7})).selectors,dep.selectors)
        s.field_write(('object','T.value',2),Value({'value':7}))
        self.assertFalse(field_selection(s,('object','T.value',2),s.fields[('object','T.value',2)]).selectors)

    def test_distinct_frames_do_not_share_control(self):
        f,s,c=self.setup_control([{'op':153,'target':3},{'op':3},{'op':54,'var':0},{'op':177}])
        c.branch({'op':153,'target':3},[Value({'value':0},frozenset({('field',1,0)}))],{'taken':True})
        other=Frame('next');d=Control(c.graph,other,s,lambda v:None)
        self.assertFalse(d.current().selectors)

    def test_potential_opaque_effect_preserves_only_new_established_values(self):
        f,s,c=self.setup_control([{'op':177}])
        s.control_barriers.append((10,Value(selectors=frozenset({('field',1,0)}),unknown=True),('unclosed',)))
        self.assertTrue(field_selection(s,('o','T.value',1),Value({'value':7}),5).unknown)
        self.assertFalse(field_selection(s,('o','T.value',2),Value({'value':7}),11).unknown)

    def test_branch_contradiction_rejects(self):
        f,s,c=self.setup_control([{'op':153,'target':2},{'op':177},{'op':177}])
        with self.assertRaises(ValueError):c.branch({'op':153,'target':2},[Value({'value':1})],{'taken':True})

    def test_missing_operand_is_not_replaced_by_taken_bit(self):
        f,s,c=self.setup_control([{'op':153,'target':2},{'op':177},{'op':177}])
        with self.assertRaises(ValueError):c.branch({'op':153,'target':2},[Value()],{'taken':True})

    def test_impossible_integer_operand_is_rejected(self):
        from control_dependencies import branch_taken
        with self.assertRaises(ValueError):branch_taken(153,[Value({'value':2**40})],lambda v:None)
        with self.assertRaises(ValueError):branch_taken(153,[Value({'value':1.0})],lambda v:None)

    def test_missing_reference_ids_are_not_equal_by_default(self):
        from control_dependencies import branch_taken
        with self.assertRaises(ValueError):branch_taken(165,[Value(),Value()],lambda v:None)
        with self.assertRaises(ValueError):branch_taken(165,[Value({'value':'SAME'}),Value({'value':'SAME'})],lambda v:None)
        self.assertTrue(branch_taken(198,[Value({'value':None})],lambda v:None))

    def test_unadmitted_control_rejects(self):
        with self.assertRaises(ValueError):ControlFlow(self.method([{'op':170}]))

    def test_unclosed_cross_join_write_address_is_not_certified(self):
        f,s,c=self.setup_control([{'op':177}])
        with self.assertRaises(ValueError):c.write_value(Value({'value':7}),Value({'object':'o'},selectors=frozenset({('field',1,0)})))

    def test_untaken_interface_call_uses_all_planned_write_targets(self):
        code=[{'op':4},{'op':153,'target':6},{'op':25,'var':1},{'op':25,'var':0},{'op':4},
              {'op':185,'owner':'Api','name':'apply','desc':'(LBox;I)V'},{'op':177}]
        method=self.method(code);method.update(owner='T',name='root',desc='(LBox;LApi;)V')
        impl={'access':0,'desc':'(LBox;I)V','try_catches':0,'exception_handlers':[],
              'instructions':[{'op':25,'var':1},{'op':21,'var':2},{'op':181,'owner':'Box','name':'value','desc':'I'},{'op':177}]}
        f=Frame('unit');s=State(f);c=Control(ControlFlow(method),f,s,lambda v:v.observed.get('object'),{'Worker.apply(LBox;I)V':impl},call_targets={'T.root(LBox;LApi;)V@5':['Worker.apply(LBox;I)V']})
        f.locals[0]=Value({'object':'box'});f.locals[1]=Value({'object':'worker'});f.pc=1
        c.branch(code[1],[Value({'value':0},frozenset({('field',1,0)}))],{'taken':True})
        c.at(6)
        self.assertEqual(field_selection(s,('box','Box.value',1),Value({'value':7})).selectors,frozenset({('field',1,0)}))

    def test_legacy_v1_executes_same_control_transfer(self):
        entry='T.root()LT;'
        code=[{'op':25,'var':0},{'op':180,'owner':'T','name':'condition','desc':'I'},
              {'op':153,'target':7},{'op':25,'var':0},{'op':4},
              {'op':181,'owner':'T','name':'value','desc':'I'},{'op':167,'target':10},
              {'op':25,'var':0},{'op':5},{'op':181,'owner':'T','name':'value','desc':'I'},
              {'op':25,'var':0},{'op':176}]
        method={'instructions':code,'access':0,'desc':'()LT;','try_catches':0,'exception_handlers':[]}
        plan={'entry':entry,'collection_method':method,'execution_kernel':{'version':1,'runtime_profiles':[{'java_runtime_version':'unit','class_sha256':{}}],'step_limit':100,'evidence_policy':'unit','constructors':{}},'response_binding':{'source_calls':[]}}
        source={'owner':'o1','field':'T.condition','version':1,'observed':{'value':1}}
        target={'owner':'o1','field':'T.value','version':1,'observed':{'value':1},'path':'/value'}
        rows=[{'kind':'execution-runtime','java_runtime_version':'unit','class_sha256':{}},
              {'kind':'enter','frame':'f1','method':entry,'receiver':'o1','args':[]},
              {'kind':'binding-source','frame':'f1','fields':[source]},
              {'kind':'read','frame':'f1','site':entry+'@1',**source},
              {'kind':'branch','frame':'f1','site':entry+'@2','taken':False},
              {'kind':'write','frame':'f1','site':entry+'@5',**target},
              {'kind':'binding-return','frame':'f1','result':{'object':'o1'},'fields':[target]},
              {'kind':'exit','frame':'f1','result':{'object':'o1'}}]
        for i,r in enumerate(rows,1):r['seq']=i
        result=infer_execution(plan,rows)['answers'][0]
        self.assertTrue(result['known']);self.assertFalse(result['origins']);self.assertEqual(result['selectors'],[[3,0]])


if __name__=='__main__':unittest.main()
