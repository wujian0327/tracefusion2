"""Identity/sequence/ambiguity guards for the cached root-return lookup."""
import unittest
from collections import defaultdict
from infer_distributed_fields import Reconstruction


class AliasIndexTest(unittest.TestCase):
    def graph(self,providers,returns=None,target_frame='root',target_message=None):
        g=Reconstruction.__new__(Reconstruction);g.edges={};g.plans={'s':{'response_binding':{'path':'/x'}}};g.root_return_messages={'s':returns or {'root':['m']}};g.providers=defaultdict(list);g.nodes={}
        for i,(seq,frame,message,parent,value)in enumerate(providers):
            key=('s',i);g.nodes[key]={'service':'s','owner':'o','field':'C.x','version':1,'seq':seq,'kind':'http-json','direction':'response','root_frame':frame,'message':message,'parent_message':parent,'observed':{'value':value}};g.providers[('s',('o','C.x',1))].append(key)
        g.nodes['target']={'service':'s','owner':'o','field':'C.x','version':1,'seq':10,'root_frame':target_frame,'message':target_message,'observed':{'value':'equal'}};return g
    def test_actual_frame_excludes_equal_other_frame(self):
        g=self.graph([(1,'other','m',None,'equal'),(2,'root','z',None,'equal')]);g.alias('target');self.assertEqual(g.edges['target'],[('s',1)])
    def test_multiple_same_coordinate_providers_remain_ambiguous(self):
        g=self.graph([(1,'root',None,None,'equal'),(2,'root',None,None,'equal')]);g.alias('target');self.assertNotIn('target',g.edges);self.assertIn('Multiple',g.nodes['target']['unknown'])
    def test_future_provider_is_not_predecessor(self):
        g=self.graph([(11,'root',None,None,'equal')]);g.alias('target');self.assertNotIn('target',g.edges)
    def test_message_requires_concrete_parent(self):
        g=self.graph([(1,None,'rpc','m','equal')]);g.alias('target');self.assertEqual(g.edges['target'],[('s',0)])
    def test_duplicate_root_returns_rejected(self):
        for messages in (['m','m'],['m','other']):
            g=self.graph([(1,None,'rpc','m','equal')],{'root':messages})
            with self.assertRaisesRegex(ValueError,'Ambiguous root-return'):g.alias('target')
    def test_same_coordinate_changed_value_is_unknown(self):
        g=self.graph([(1,'root',None,None,'changed')]);g.alias('target');self.assertNotIn('target',g.edges);self.assertIn('Value changed',g.nodes['target']['unknown'])


if __name__=='__main__':unittest.main()
