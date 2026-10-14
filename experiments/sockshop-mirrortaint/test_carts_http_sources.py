import copy
import unittest
from infer_carts_http_sources import bridge
from infer_field_access_sites import signature


MODEL={'owner':'Item','getters':{
    'getItemId()Ljava/lang/String;':{'field':'Item.itemId'},
    'getQuantity()I':{'field':'Item.quantity'},
    'getUnitPrice()F':{'field':'Item.unitPrice'}}}
METHODS={value['field'].split('.')[-1]:signature(MODEL,key) for key,value in MODEL['getters'].items()}


def sample(messages=('a','b')):
    server=[];client=[]
    for message in messages:
        fields=[]
        for field,value in (('itemId','equal'),('quantity',2),('unitPrice',5.0)):
            server.append({'kind':'read','message_id':message,'owner':'source-'+message,'field':field,
                'declared_field':'Item.'+field,'access_method':METHODS[field],
                'http_uri':'/carts/same-customer/items','seq':len(server)+1,'observed':{'value':value}})
            fields.append({'path':'result#body[0]#'+field,'owner':'target-'+message,
                'field':field,'version':1,'observed':{'value':value}})
        client.extend([{'kind':'http-send','rpc':message,'method':'GET','uri':'http://carts/carts/same-customer/items'},
            {'kind':'rpc-exit','rpc':message,'status':'200','seq':len(client)+2,'fields':fields}])
    return server,client


class CartHttpTests(unittest.TestCase):
    def test_equal_values_and_same_uri_still_use_exact_message_identity(self):
        server,client=sample();edges,unknown=bridge(server,client,MODEL)
        self.assertFalse(unknown);self.assertEqual(len(edges),6)
        self.assertEqual(edges[('a','result#body[0]#quantity')]['owner'],'source-a')
        self.assertEqual(edges[('b','result#body[0]#quantity')]['owner'],'source-b')

    def test_missing_message_is_not_replaced_by_equal_values(self):
        server,client=sample();server=[r for r in server if r['message_id']!='a']
        edges,unknown=bridge(server,client,MODEL)
        self.assertNotIn(('a','result#body[0]#quantity'),edges)
        self.assertTrue(any(r['message']=='a' for r in unknown))

    def test_value_mismatch_does_not_select_another_message(self):
        server,client=sample();server[1]['observed']['value']=99
        edges,unknown=bridge(server,client,MODEL)
        self.assertNotIn(('a','result#body[0]#quantity'),edges)
        self.assertIn(('b','result#body[0]#quantity'),edges)
        self.assertTrue(unknown)

    def test_inconsistent_property_order_is_unknown(self):
        server,client=sample(('a',))
        other=copy.deepcopy(server)
        for r in other:r['owner']='second';r['seq']+=3
        server=server+other
        second=copy.deepcopy(client[1]['fields'])
        for f in second:f['path']=f['path'].replace('[0]','[1]');f['owner']='target-second'
        client[1]['fields']+=second
        # A different owner ordering for just quantity is not silently repaired.
        server[1],server[4]=server[4],server[1]
        edges,unknown=bridge(server,client,MODEL)
        self.assertFalse(edges);self.assertTrue(unknown)

    def test_duplicate_transport_send_is_rejected(self):
        server,client=sample();client.append(copy.deepcopy(client[0]))
        with self.assertRaisesRegex(ValueError,'Duplicate send'):bridge(server,client,MODEL)

    def test_labels_do_not_change_reconstruction(self):
        server,client=sample();expected=bridge(server,client,MODEL)
        for row in client:row['expected_dependency']=False;row['trace_id']='same-for-all'
        self.assertEqual(expected,bridge(server,client,MODEL))


if __name__=='__main__':unittest.main()
