"""Synthetic communication proof guards; real JVM captures are separate."""
import copy
import hashlib
import json
import unittest
from http_exchange_protocol import bridges,validate_local


class ExchangeTests(unittest.TestCase):
    def fixture(self,role='A',two=False):
        plan={'http_exchange':{'version':1,'scope':'blocking-http-json-one-exchange-per-connection','input_role':'external'if role=='A'else'intermediate','adapter_sha256':'adapter','server_sha256':'server'},'json_schema':{'DTO':[{'field':'DTO.'+f,'property':f,'descriptor':'Ljava/lang/String;'}for f in ('value','fallback')]}}
        events=[{'kind':'start'}]
        for index in range(1,3 if two else 2):
            trace='1'*32;span=str(index)*16
            for direction in ('request','response'):
                client=role=='A';phase=('write'if client else'read')if direction=='request'else('read'if client else'write')
                raw='{"value":"SAME","fallback":"SAME"}';r={'message':trace+'/'+span,'transport_protocol':'w3c-trace-context','trace_id':trace,'request_span_id':span,'span_id':span if client else'3'*16,'parent_span_id':None if client else span,'trace_flags':'01','wire_traceparent':'00-'+trace+'-'+span+'-01','carrier':role+str(index),'connection':['127.0.0.1',str(40000+index),'127.0.0.1','8888'],'direction':direction,'phase':phase,'wire_utf8':raw,'wire_sha256':hashlib.sha256(raw.encode()).hexdigest(),'method':'POST','path':'/call','status':0 if direction=='request' else 200,'normal_complete':True,'adapter_sha256':'adapter','server_sha256':'server'}
                events.append(dict(r,kind='http-exchange'))
                events.append(dict(r,kind='http-json',fields=[{'field':'DTO.'+f,'owner':role+str(index),'version':0,'path':'/'+f,'descriptor':'Ljava/lang/String;','observed':{'value':'SAME','object':role+f+str(index)}}for f in ('value','fallback')]))
        events.append({'kind':'metrics'});self.seal(plan,events,role)
        return plan,events
    def seal(self,plan,events,role='A'):
        for i,r in enumerate(events,1):r.update(seq=i,http_exchange_version=1,capture_session='cap'+role,process_instance='proc'+role)
        events[0]['plan_sha256']=hashlib.sha256((json.dumps(plan,indent=2)+'\n').encode()).hexdigest();events[-1]['http_exchange_event_count']=len(events)
    def test_same_trace_concrete_messages_remain_separate(self):
        a,ar=self.fixture(two=True);b,br=self.fixture('B',True);_,links=bridges({'A':a,'B':b},{'A':ar,'B':br});self.assertEqual(len(links),8);self.assertEqual(len({tuple(x['connection'])for x in links}),2)
    def test_cross_jvm_object_numbers_not_compared(self):
        a,ar=self.fixture();b,br=self.fixture('B');_,links=bridges({'A':a,'B':b},{'A':ar,'B':br});self.assertEqual(len(links),4)
    def test_equal_value_pointer_swap_rejects(self):
        p,rs=self.fixture();rs[2]['fields'][0]['path']='/fallback';rs[2]['fields'][1]['path']='/value'
        with self.assertRaisesRegex(ValueError,'mapping differs'):validate_local(p,rs)
    def test_missing_io_even_after_resequencing(self):
        p,rs=self.fixture();rs.pop(1);self.seal(p,rs)
        with self.assertRaisesRegex(ValueError,'Missing completed'):validate_local(p,rs)
    def test_missing_codec_even_after_resequencing(self):
        p,rs=self.fixture();rs.pop(2);self.seal(p,rs)
        with self.assertRaisesRegex(ValueError,'Missing completed'):validate_local(p,rs)
    def test_wrong_wire_header(self):
        p,rs=self.fixture();rs[1]['wire_traceparent']=rs[2]['wire_traceparent']='00-'+'1'*32+'-'+'9'*16+'-01'
        with self.assertRaisesRegex(ValueError,'wire header'):validate_local(p,rs)
    def test_no_match_on_value_without_endpoints(self):
        a,ar=self.fixture();b,br=self.fixture('B')
        for r in br:
            if 'connection'in r:r['connection'][1]='44444'
        _,links=bridges({'A':a,'B':b},{'A':ar,'B':br});self.assertEqual(links,[])
    def test_no_match_on_trace_without_concrete_span(self):
        a,ar=self.fixture();b,br=self.fixture('B')
        for r in br:
            if 'message'in r:r.update(message='1'*32+'/'+'9'*16,request_span_id='9'*16,wire_traceparent='00-'+'1'*32+'-'+'9'*16+'-01')
        _,links=bridges({'A':a,'B':b},{'A':ar,'B':br});self.assertEqual(links,[])
    def test_foreign_process_event_rejects(self):
        p,rs=self.fixture();rs[2]['process_instance']='foreign'
        with self.assertRaisesRegex(ValueError,'capture/process'):validate_local(p,rs)
    def test_same_capture_namespace_two_services_rejects(self):
        a,ar=self.fixture();b,br=self.fixture('B');self.seal(b,br,'A')
        with self.assertRaisesRegex(ValueError,'share a capture'):bridges({'A':a,'B':b},{'A':ar,'B':br})
    def test_wrong_implementation_hash(self):
        p,rs=self.fixture();rs[1]['adapter_sha256']='different'
        with self.assertRaisesRegex(ValueError,'implementation'):validate_local(p,rs)
    def test_aborted_io_is_not_normal(self):
        p,rs=self.fixture();rs[1]['normal_complete']=False
        with self.assertRaisesRegex(ValueError,'Incomplete'):validate_local(p,rs)
    def test_same_connection_reused_for_distinct_message_rejects(self):
        a,ar=self.fixture(two=True);b,br=self.fixture('B',True)
        for rs in (ar,br):
            for r in rs:
                if 'connection'in r:r['connection'][1]='40001'
        with self.assertRaisesRegex(ValueError,'reused'):bridges({'A':a,'B':b},{'A':ar,'B':br})
    def test_wrong_body_hash(self):
        p,rs=self.fixture();rs[1]['wire_utf8']='{}'
        with self.assertRaisesRegex(ValueError,'body hash'):validate_local(p,rs)
    def test_no_unknown_field_silently_dropped(self):
        p,rs=self.fixture();rs[2]['fields'].pop()
        with self.assertRaisesRegex(ValueError,'coverage'):validate_local(p,rs)
    def test_intermediate_request_cannot_be_promoted_by_query_boundary(self):
        from infer_distributed_fields import Reconstruction
        g=Reconstruction.__new__(Reconstruction);g.exchange_audits={'B':{}};g.plans={'B':{'http_exchange':{'input_role':'intermediate'}}};g.nodes={('B',1,'/value'):{'service':'B','kind':'http-json','direction':'request','phase':'read'}};g.edges={}
        self.assertEqual(g.origins(('B',1,'/value'),boundary={'service':'B'}),([],False))
    def test_external_request_remains_valid_boundary(self):
        from infer_distributed_fields import Reconstruction
        g=Reconstruction.__new__(Reconstruction);g.exchange_audits={'A':{}};g.plans={'A':{'http_exchange':{'input_role':'external'}}};g.nodes={('A',1,'/value'):{'service':'A','kind':'http-json','direction':'request','phase':'read'}};g.edges={}
        self.assertEqual(g.origins(('A',1,'/value'),boundary={'service':'A'}),([('A',1,'/value')],True))
    def test_equal_valued_new_local_reference_cannot_forward_without_write(self):
        from infer_distributed_fields import Reconstruction
        g=Reconstruction.__new__(Reconstruction);g.exchange_audits={'A':{}};g.plans={'A':{}};g.edges={}
        source=('A',1,'/value');target=('A',2,'/value');base={'service':'A','owner':'dto','field':'DTO.value','version':0,'descriptor':'Ljava/lang/String;','kind':'http-json'}
        g.nodes={source:dict(base,seq=1,observed={'object':'s1','value':'SAME'}),target:dict(base,seq=2,observed={'object':'s2','value':'SAME'})};g.providers={('A',('dto','DTO.value',0)):[source]}
        g.alias(target);self.assertNotIn(target,g.edges);self.assertIn('outside counted',g.nodes[target]['unknown'])


if __name__=='__main__':unittest.main()
