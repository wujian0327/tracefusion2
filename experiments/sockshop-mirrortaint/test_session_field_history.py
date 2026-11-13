"""Synthetic protocol/index units; real JVM evidence is tested by round_two.py."""
import copy
import hashlib,json
from dataclasses import FrozenInstanceError
import unittest
from execution_dependency_state import Value
from session_field_history import SessionHistory
from method_value_protocol import validate as methods


class HistoryTests(unittest.TestCase):
    def make(self,capture='cap',process='proc',extra=()):
        plan={'entry':'C.read()LO;','execution_kernel':{'methods':{'C.read()LO;':{}}},'session_history':{'version':1,'scope':'sequential-http-external-input-and-application-roots','roots':['C.read()LO;'],'data_fields':['I.value'],'control_fields':['I.key']}}
        events=[{'kind':'start','mode':'full'},{'kind':'write','owner':'o1','field':'C.value','version':1,'observed':{'object':None,'value':100},'descriptor':'I','frame':'f1','site':'C.write()V@1'},*copy.deepcopy(extra),{'kind':'metrics'}]
        for i,r in enumerate(events,1):r.update(seq=i,session_history_version=1,capture_session=capture,process_instance=process)
        events[-1]['session_history_event_count']=len(events)
        events[0]['plan_sha256']=hashlib.sha256((json.dumps(plan,indent=2)+'\n').encode()).hexdigest()
        return SessionHistory(plan,events),events
    def publish(self,h,rs,unknown=False,origins=frozenset({('http',1,'/value')}),completion='normal'):
        h.publish(rs[1],Value(rs[1]['observed'],origins,unknown=unknown),completion)
    def read(self,h,version=1,owner='o1'):
        return {'owner':owner,'field':'C.value','version':version,'observed':{'object':None,'value':100},'descriptor':'I','kind':'read','seq':100,'capture_session':h.namespace[0],'process_instance':h.namespace[1]}
    def test_exact_version_no_same_value_fallback(self):
        h,rs=self.make();self.publish(h,rs);self.assertIsNone(h.lookup(self.read(h,2),101,'q'))
    def test_new_object_equal_value_is_not_old_object(self):
        h,rs=self.make();self.publish(h,rs);self.assertIsNone(h.lookup(self.read(h,owner='o2'),101,'q'))
    def test_different_capture_same_object_number(self):
        a,ars=self.make();b,brs=self.make(capture='other');self.publish(a,ars)
        self.assertIsNone(b.lookup(self.read(b),101,'q'))
        with self.assertRaisesRegex(ValueError,'Foreign session'):a.lookup(self.read(b),101,'q')
    def test_different_process_same_object_number(self):
        a,ars=self.make();b,brs=self.make(process='other');self.publish(a,ars)
        self.assertIsNone(b.lookup(self.read(b),101,'q'))
        with self.assertRaisesRegex(ValueError,'Foreign session'):a.lookup(self.read(b),101,'q')
    def test_foreign_write_is_not_publishable(self):
        a,ars=self.make();b,brs=self.make(capture='other')
        with self.assertRaisesRegex(ValueError,'another evidence'):a.publish(brs[1],Value(brs[1]['observed']),'normal')
    def test_immutable_observed_payload(self):
        h,rs=self.make();self.publish(h,rs);rs[1]['observed']['value']=999
        value,_=h.lookup(self.read(h),101,'q');value.observed['value']=777
        self.assertEqual(h.lookup(self.read(h),101,'q')[0].observed['value'],100)
    def test_frozen_record(self):
        h,rs=self.make();self.publish(h,rs)
        with self.assertRaises(FrozenInstanceError):next(iter(h.versions.values())).unknown=True
    def test_unknown_is_not_empty_known(self):
        h,rs=self.make();self.publish(h,rs,True,origins=frozenset())
        value,_=h.lookup(self.read(h),101,'q');self.assertTrue(value.unknown);self.assertFalse(value.origins)
    def test_duplicate_version_rejected(self):
        h,rs=self.make();self.publish(h,rs)
        with self.assertRaisesRegex(ValueError,'twice'):self.publish(h,rs)
    def test_strong_overwrite_preserves_old_record(self):
        h,rs=self.make(extra=[{'kind':'write','owner':'o1','field':'C.value','version':2,'observed':{'object':None,'value':100},'descriptor':'I','frame':'f2','site':'C.write()V@1'}]);self.publish(h,rs)
        h.publish(rs[2],Value(rs[2]['observed'],frozenset({('http',2,'/value')})),'normal')
        self.assertEqual(h.lookup(self.read(h),101,'q')[0].origins,frozenset({('http',1,'/value')}))
        self.assertEqual(h.lookup(self.read(h,2),101,'q')[0].origins,frozenset({('http',2,'/value')}))
    def test_constant_kill_requires_real_new_write(self):
        h,rs=self.make(extra=[{'kind':'write','owner':'o1','field':'C.value','version':2,'observed':{'object':None,'value':100},'descriptor':'I','frame':'f2','site':'C.write()V@1'}]);self.publish(h,rs)
        h.publish(rs[2],Value(rs[2]['observed']),'normal');v,_=h.lookup(self.read(h,2),101,'q')
        self.assertFalse(v.unknown);self.assertFalse(v.origins);self.assertTrue(h.lookup(self.read(h),101,'q')[0].origins)
    def test_unknown_effect_barrier_and_later_strong_write(self):
        h,rs=self.make(extra=[{'kind':'write','owner':'o1','field':'C.value','version':2,'observed':{'object':None,'value':100},'descriptor':'I','frame':'f2','site':'C.write()V@1'}]);self.publish(h,rs);h.invalidate(['o1'],2)
        self.assertTrue(h.lookup(self.read(h),101,'q')[0].unknown)
        h.publish(rs[2],Value(rs[2]['observed']),'normal');self.assertFalse(h.lookup(self.read(h,2),101,'q')[0].unknown)
    def test_aborted_root_does_not_certify_write(self):
        h,rs=self.make();self.publish(h,rs,completion='aborted');self.assertTrue(h.lookup(self.read(h),101,'q')[0].unknown)
    def test_opaque_effect_crosses_reference_from_prior_root(self):
        h,rs=self.make(extra=[{'kind':'write','owner':'o1','field':'C.cell','version':1,'observed':{'object':'o2'},'descriptor':'LC;','frame':'f1','site':'C.write()V@2'},
                             {'kind':'write','owner':'o2','field':'C.value','version':1,'observed':{'object':None,'value':100},'descriptor':'I','frame':'f1','site':'C.write()V@3'}])
        h.publish(rs[2],Value(rs[2]['observed']),'normal');h.publish(rs[3],Value(rs[3]['observed'],frozenset({('http',1,'/value')})),'normal')
        h.invalidate(['o1'],10)
        self.assertTrue(h.lookup(self.read(h,owner='o2'),101,'next-root')[0].unknown)
        self.assertFalse(h.versions[(h.namespace,('o2','C.value',1))].unknown)
    def test_read_cannot_precede_write(self):
        h,rs=self.make();self.publish(h,rs)
        with self.assertRaisesRegex(ValueError,'precedes'):h.lookup(self.read(h),2,'q')
    def test_header_namespace_tamper(self):
        h,rs=self.make();rs[1]['capture_session']='foreign'
        with self.assertRaisesRegex(ValueError,'identity differs'):SessionHistory({'entry':'C.read()LO;','execution_kernel':{'methods':{'C.read()LO;':{}}},'session_history':h.config},rs)
    def test_descriptor_mismatch(self):
        h,rs=self.make();self.publish(h,rs);read=self.read(h);read['descriptor']='J'
        with self.assertRaisesRegex(ValueError,'descriptor'):h.lookup(read,101,'q')
    def test_overlapping_request_stacks_are_rejected(self):
        h,rs=self.make();h.root({'method':'C.read()LO;','parent':None,'seq':1,'frame':'f1'},{'seq':4})
        with self.assertRaisesRegex(ValueError,'Overlapping'):h.root({'method':'C.read()LO;','parent':None,'seq':3,'frame':'f2'},{'seq':5})
    def test_actual_source_identity_reused_across_snapshots(self):
        h,rs=self.make();f={'owner':'i1','field':'I.value','version':0,'descriptor':'I','path':'/value','observed':{'object':None,'value':100}}
        source={'seq':2,'message':'http-r1','fields':[f]};h.external[('http-r1',('i1','I.value',0))]=[(source,f)]
        a=h.input({'seq':3,'message':'http-r1','frame':'write'},f,4);b=h.input({'seq':4,'message':'http-r1','frame':'read'},f,5)
        self.assertEqual(a.origins,b.origins);self.assertEqual(a.origins,frozenset({('http',2,'/value')}))
    def test_missing_external_source_is_unknown(self):
        h,rs=self.make();v=h.input({'seq':3,'message':'missing','frame':'f'},dict(self.read(h),path='/value'),4);self.assertTrue(v.unknown)


class SessionMethodTests(unittest.TestCase):
    def test_void_root_uses_its_actual_descriptor(self):
        plan={'entry':'C.read()LO;','frame_methods':['C.write()V'],'session_history':{'roots':['C.write()V']}}
        rows=[{'kind':'start','method_value_version':1},{'kind':'enter','frame':'f','method':'C.write()V','method_descriptor':'()V','args':[]},{'kind':'binding-return','frame':'f','method_descriptor':'()V','result':{'object':None,'value':None,'void':True}},{'kind':'exit','frame':'f','method_descriptor':'()V','result':{'object':None,'value':None,'void':True}}]
        methods(plan,rows);legacy=copy.deepcopy(plan);legacy.pop('session_history')
        with self.assertRaisesRegex(ValueError,'descriptor'):methods(legacy,rows)


if __name__=='__main__':unittest.main()
