import unittest
from plan_collection_service import analyze


def method(code,handlers=()):
    return {'access':8,'desc':'(I)I','instructions':[dict(index=i,**n) for i,n in enumerate(code)],'try_catches':len(handlers),'exception_handlers':list(handlers)}


class CollectionCFGTests(unittest.TestCase):
    def test_many_diamonds_join_instead_of_enumerating_paths(self):
        code=[{'op':3},{'op':54,'var':1}]
        for _ in range(64):
            start=len(code);code += [{'op':21,'var':0},{'op':153,'target':start+4},{'op':4},{'op':54,'var':1}]
        code += [{'op':21,'var':1},{'op':172}]
        graph,operands,states,steps=analyze(method(code))
        self.assertEqual(len(states),len(code))
        self.assertLess(steps,5000)
        self.assertGreater(len(operands[len(code)-2][0]),1)

    def test_missing_exception_table_fails_closed(self):
        m=method([{'op':3},{'op':172}]);m['try_catches']=1
        with self.assertRaisesRegex(ValueError,'exception table'):analyze(m)

    def test_backward_branch_rejected(self):
        with self.assertRaisesRegex(ValueError,'Loops/back edges'):
            analyze(method([{'op':21,'var':0},{'op':154,'target':0},{'op':3},{'op':172}]))

    def test_handler_receives_prethrow_locals_and_exception_stack(self):
        c=[{'op':3},{'op':54,'var':1},{'op':1},{'op':191},{'op':58,'var':2},{'op':21,'var':1},{'op':172}]
        _,_,states,_=analyze(method(c,[{'start':2,'end':4,'handler':4,'type':'java/lang/Throwable'}]))
        self.assertEqual(len(states[4][0]),1)
        self.assertIn(1,states[4][1])


if __name__=='__main__':unittest.main()
