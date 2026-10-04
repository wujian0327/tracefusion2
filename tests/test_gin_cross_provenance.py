from copy import deepcopy
import json
import os
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from test_gin_byte_provenance import evidence as local_evidence,combine
from gin_cross_boundaries import bind_service,stitch,trace_key
from gin_cross_provenance import negative_checks
import gin_byte_capture

TRACE='00-'+'1'*32+'-'+'2'*16+'-01'
OTHER='00-'+'1'*32+'-'+'3'*16+'-01'


def evidence(role,variant='assign',use_c=False,trace=TRACE,g=0x888,offset=0,ticket=1):
    doc,p=local_evidence(variant,use_c if role=='upstream' else False,g=g,offset=offset,ticket=ticket)
    p['cross_role']=role;sites=p['sites'];events=doc['events']
    def value(ptr,b):return dict(pointer=ptr,hex=b.hex(),key=f'{ptr:x}:{len(b)}')
    def event(op,phase,registers=None,values=None):
        sid=len(sites);sites.append(dict(id=sid,op=op,phase=phase,pair=-1,address=0xA000+sid,snapshots={}))
        e=deepcopy(events[0]);e.update(site=sid,op=op,phase=phase,values=values or {})
        if registers:e['registers'].update(registers)
        return e
    context=[event('trace','pre'),event('trace','post',values={'trace':value(0xF000,trace.encode())})]
    if role=='downstream':
        before=next(e for e in events if e['op']=='source' and e['phase']=='pre')
        after=next(e for e in events if e['op']=='source' and e['phase']=='post')
        before['values']['trace']=value(0xF000,trace.encode())
        before['values']['path']=value(0xE000,b'http://127.0.0.1:1234/account/summary')
        body=b'{"result":[83,65,77,69]}';ptr=0xD000
        transport=[event('http_header','pre',values={'key':value(0xC000,b'traceparent'),'trace':value(0xF000,trace.encode())}),
            event('http_header','post'),event('http_body','pre'),
            event('http_body','post',{'rax':ptr,'rbx':len(body),'rcx':len(body),'rdi':0},{'body':value(ptr,body)}),
            event('decode','pre',{'rax':ptr,'rbx':len(body),'rcx':len(body),'rdi':123,'rsi':after['values']['value']['pointer']},{'body':value(ptr,body)}),
            event('decode','post',{'rax':0})]
        index=events.index(after);events[index:index]=transport
    events[1:1]=context
    for i,e in enumerate(events):e['sequence']=i;e['timestamp']=i;e['pid']=10 if role=='upstream' else 20
    doc['stats']['submitted']=len(events);p['event_order']=[s['id'] for s in sites]
    return doc,p


class CrossServiceTests(unittest.TestCase):
    def test_three_variants_link_sources_and_drop_fully_overwritten_upstream(self):
        for variant in ('assign','partial','overwrite'):
            for use_c in (False,True):
                u,up=evidence('upstream',use_c=use_c);d,dp=evidence('downstream',variant)
                a,b=bind_service(u,up),bind_service(d,dp)
                self.assertEqual(a['status'],'resolved',a);self.assertEqual(b['status'],'resolved',b)
                result=stitch(a,b);self.assertEqual(result['status'],'resolved',result)
                row=result['results'][0];sources={s['id'] for s in row['sources']}
                remote='upstream/request:1:source:'+('3' if use_c else '1');local='downstream/request:1:source:2'
                expected={remote} if variant=='assign' else {remote,local} if variant=='partial' else {local}
                self.assertEqual(sources,expected)
                self.assertEqual(row['transfer_contributes'],variant!='overwrite')
                self.assertTrue(all(n['passed'] for n in negative_checks(a,b)))
                if variant=='overwrite':self.assertTrue(all(not n['id'].startswith('upstream/') for n in row['graph']['nodes']))

    def test_same_trace_and_values_require_distinct_parent_ids(self):
        u1,up=evidence('upstream');u2,_=evidence('upstream',use_c=True,trace=OTHER,g=0x999,offset=0x10000,ticket=2)
        d1,dp=evidence('downstream','partial');d2,_=evidence('downstream','partial',trace=OTHER,g=0x999,offset=0x10000,ticket=2)
        a,b=bind_service(combine([u1,u2]),up),bind_service(combine([d1,d2]),dp)
        result=stitch(a,b);self.assertEqual(result['status'],'resolved',result)
        self.assertEqual(len(result['results']),2)
        self.assertEqual([r['upstream_request'] for r in result['results']],[1,2])
        duplicate=deepcopy(b);duplicate['results'][1]['transfer']['trace']=TRACE
        bad=stitch(a,duplicate)
        self.assertEqual([r['status'] for r in bad['results']],['unknown','unknown'])

    def test_byte_transfer_preserves_only_retained_upstream_dependencies(self):
        # Stress the graph join with an already validated partial upstream,
        # even though the first real two-service fixture uses assign upstream.
        u,up=evidence('upstream','partial');d,dp=evidence('downstream','partial')
        a,b=bind_service(u,up),bind_service(d,dp);result=stitch(a,b)
        self.assertEqual(result['status'],'resolved',result)
        self.assertEqual({s['id'] for s in result['results'][0]['sources']},
                         {'upstream/request:1:source:1','downstream/request:1:source:2'})

    def test_broken_raw_transport_or_decoder_evidence_rejected(self):
        for failure in ('header','body','decoded_object','decode_error','missing_decode','trace'):
            d,p=evidence('downstream')
            if failure=='header':
                e=next(e for e in d['events'] if e['op']=='http_header' and e['phase']=='pre');e['values']['trace']['hex']=OTHER.encode().hex()
            elif failure=='body':
                e=next(e for e in d['events'] if e['op']=='http_body' and e['phase']=='post');e['values']['body']['hex']='00'+e['values']['body']['hex'][2:]
            elif failure=='decoded_object':next(e for e in d['events'] if e['op']=='decode' and e['phase']=='pre')['registers']['rsi']+=4
            elif failure=='decode_error':next(e for e in d['events'] if e['op']=='decode' and e['phase']=='post')['registers']['rax']=1
            elif failure=='trace':next(e for e in d['events'] if e['op']=='trace' and e['phase']=='post')['values']['trace']['hex']='00'
            else:d['events'].remove(next(e for e in d['events'] if e['op']=='decode' and e['phase']=='pre'))
            for i,e in enumerate(d['events']):e['sequence']=i
            d['stats']['submitted']=len(d['events'])
            self.assertEqual(bind_service(d,p)['status'],'unknown',failure)

    def test_missing_zero_or_unsupported_trace_ids_rejected(self):
        for value in ('',TRACE.replace('1'*32,'0'*32),TRACE.replace('2'*16,'0'*16),TRACE[:-2]+'00'):
            with self.assertRaises(ValueError):trace_key(value)

    @unittest.skipUnless(os.environ.get('GIN_CROSS_BUILD'),'Set GIN_CROSS_BUILD to a built two-service directory')
    def test_real_two_service_plans_generate_all_probes(self):
        from gin_byte_adapter import plan_binary
        root=Path(os.environ['GIN_CROSS_BUILD']).resolve();go=os.environ.get('TRACEFUSION_GO','go')
        for variant in ('assign','partial','overwrite'):
            for role in ('upstream','downstream'):
                with tempfile.TemporaryDirectory() as tmp:
                    p=plan_binary(root/variant/role/'gin-byte-target',go,dict(os.environ),Path(tmp),cross_role=role)
                    code=gin_byte_capture.source(p,1,SimpleNamespace(st_dev=0,st_ino=0))
                    self.assertTrue(code)
                    self.assertEqual(sorted(s['id'] for probe in gin_byte_capture.physical_probes(p) for s in probe['sites']),p['event_order'])
                    expected={'trace'}|({'http_header','http_body','decode'} if role=='downstream' else set())
                    self.assertTrue(expected.issubset({s['op'] for s in p['sites']}))

if __name__=='__main__':unittest.main()
