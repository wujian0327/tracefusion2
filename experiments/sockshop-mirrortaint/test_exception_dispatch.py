import copy
import unittest
from exception_dispatch import first_handler
from analysis_status import AnalysisLimit

class DispatchTests(unittest.TestCase):
    def setUp(self):
        self.table=[{'start':0,'end':2,'handler':3,'type':'app/Base'}, {'start':0,'end':2,'handler':4,'type':None}]
        def node(name,i,parent,loader=None):return {'id':i,'name':name,'loader':loader,'super':parent,'class_sha256':'a'*64}
        self.chain=[node('app/Leaf','leaf','mid','L'),node('app/Mid','mid','base','L'),node('app/Base','base','throw','L'),node('java/lang/Throwable','throw','obj'),node('java/lang/Object','obj',None)]
        self.fact={'version':1,'method':'app/Root.run()V','caller':node('app/Root','root','obj','L'),'exception':{'object':'e'},'actual_type':'app/Leaf','hierarchy':self.chain,'targets':[self.chain[2],None]}
        self.hashes={n['name']:'a'*64 for n in self.chain if n['loader']};self.hashes['app/Root']='a'*64
        self.parents={n['name']:{'super':self.chain[i+1]['name']}for i,n in enumerate(self.chain[:-1])if n['loader']}
    def call(self,table=None):return first_handler(self.fact,table or self.table,0,{'object':'e'},'app.Leaf','app/Root.run()V',self.hashes,{},self.parents)
    def test_multilevel_base_first(self):self.assertEqual(self.call(),3)
    def test_catch_all(self):self.fact['targets']=[None];self.assertEqual(self.call([self.table[1]]),4)
    def test_first_handler_order(self):
        self.fact['targets']=[None,self.chain[2]];self.assertEqual(self.call([self.table[1],self.table[0]]),4)
    def test_unhandled(self):
        self.fact['targets']=[self.chain[2]];self.assertIsNone(self.call([{**self.table[0],'start':1}]))
    def test_missing_witness(self):
        self.fact=None
        with self.assertRaises(ValueError):self.call()
    def test_wrong_exception_identity(self):
        self.fact['exception']['object']='other'
        with self.assertRaises(ValueError):self.call()
    def test_incomplete_hierarchy(self):
        self.fact['hierarchy']=self.chain[:-1]
        with self.assertRaises(ValueError):self.call()
    def test_wrong_hash(self):
        self.fact['hierarchy'][0]['class_sha256']='b'*64
        with self.assertRaises(ValueError):self.call()
    def test_same_name_other_loader_rejected(self):
        self.fact['targets'][0]={**self.chain[2],'loader':'other','id':'other'}
        with self.assertRaises(AnalysisLimit):self.call()
    def test_missing_metadata_limited(self):
        del self.hashes['app/Leaf']
        with self.assertRaises(AnalysisLimit):self.call()
    def test_forged_complete_chain_rejected_by_metadata(self):
        self.chain[0]['super']='base';self.fact['hierarchy']=[self.chain[0],*self.chain[2:]]
        with self.assertRaises(ValueError):self.call()
    def test_missing_superclass_metadata_limited(self):
        del self.parents['app/Leaf']
        with self.assertRaises(AnalysisLimit):self.call()
