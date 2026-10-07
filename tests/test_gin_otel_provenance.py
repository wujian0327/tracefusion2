from copy import deepcopy
import json
import os
from pathlib import Path
from types import SimpleNamespace
import subprocess
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from test_gin_cross_provenance import evidence,TRACE,OTHER
from gin_cross_boundaries import bind_service,trace_key
from gin_otel_boundaries import span_chains,stitch_otel,negative_span_checks,read_spans,GIN,HTTP,DRIVER
from gin_otel_provenance import client
from gin_cross_provenance import readiness
from gin_byte_provenance import fixtures
import gin_byte_capture


def spans():
    def context(sid,remote=False):
        return dict(TraceID='1'*32 if sid!='0' else '0'*32,SpanID=sid*16,TraceFlags='01' if sid!='0' else '00',Remote=remote)
    def span(service,sid,parent,kind,scope,remote=False):
        return dict(SpanContext=context(sid),Parent=context(parent,remote),SpanKind=kind,
                    StartTime='2026-10-04T00:00:00Z',EndTime='2026-10-04T00:00:01Z',Status=dict(Code='Unset'),
                    Resource=[dict(Key='service.name',Value=dict(Type='STRING',Value=service))],
                    InstrumentationScope=dict(Name=scope,Version='0.63.0' if service!='driver' else ''))
    return dict(driver=[span('driver','a','0',1,DRIVER),span('driver','2','a',3,DRIVER)],
                downstream=[span('downstream','b','2',2,GIN,True),span('downstream','3','b',3,HTTP)],
                upstream=[span('upstream','c','3',2,GIN,True)])


def local(variant='assign'):
    u,up=evidence('upstream',trace=OTHER);d,dp=evidence('downstream',variant)
    dp['trace_mode']='otel';up['trace_mode']='otel'
    for event in d['events']:
        if event['op']=='source' and event['phase']=='pre':event['values'].pop('trace',None)
        if event['op']=='http_header' and event['phase']=='pre':event['values']['trace']['hex']=OTHER.encode().hex()
    a,b=bind_service(u,up),bind_service(d,dp)
    return a,b


class OTelProvenanceTests(unittest.TestCase):
    def test_sdk_child_span_and_field_sources(self):
        for variant in ('assign','partial','overwrite'):
            a,b=local(variant);self.assertEqual(a['status'],'resolved',a);self.assertEqual(b['status'],'resolved',b)
            result=stitch_otel(a,b,spans());self.assertEqual(result['status'],'resolved',result)
            row=result['results'][0]
            expected={'upstream/request:1:source:1'} if variant=='assign' else {'downstream/request:1:source:2'}
            if variant=='partial':expected.add('upstream/request:1:source:1')
            self.assertEqual({s['id'] for s in row['sources']},expected)
            self.assertEqual(row['request_trace'],TRACE);self.assertEqual(row['trace'],OTHER)
            self.assertTrue(all(n['passed'] for n in negative_span_checks(a,b,spans())))

    def test_export_order_is_not_request_order(self):
        a,b=local();docs=spans()
        for rows in docs.values():rows.reverse()
        self.assertEqual(stitch_otel(a,b,docs)['status'],'resolved')

    def test_incomplete_or_ambiguous_sdk_topology_is_unknown(self):
        for failure in ('missing_parent','extra_child','wrong_scope','unsampled','invalid_time','cross_trace','empty','missing_local','duplicate_scope'):
            a,b=local();docs=spans()
            if failure=='missing_parent':docs['driver'].pop(0)
            elif failure=='extra_child':
                extra=deepcopy(docs['upstream'][0]);extra['SpanContext']['SpanID']='d'*16;docs['upstream'].append(extra)
            elif failure=='wrong_scope':docs['upstream'][0]['InstrumentationScope']['Name']='unknown'
            elif failure=='unsampled':docs['upstream'][0]['SpanContext']['TraceFlags']='00'
            elif failure=='invalid_time':docs['upstream'][0]['EndTime']='2025-01-01T00:00:00Z'
            elif failure=='cross_trace':docs['upstream'][0]['Parent']['TraceID']='f'*32
            elif failure=='empty':docs['downstream']=[]
            elif failure=='missing_local':b['results']=[]
            else:b['results']+=deepcopy(b['results'])
            self.assertEqual(stitch_otel(a,b,docs)['status'],'unknown',failure)

    def test_sdk_tree_cannot_replace_field_evidence(self):
        a,b=local();b['results'][0]['transfer']['body']='{"result":[0,0,0,0]}'
        self.assertEqual(stitch_otel(a,b,spans())['status'],'unknown')

    @unittest.skipUnless(os.environ.get('GIN_OTEL_BUILD'),'Set GIN_OTEL_BUILD to built OTel fixture')
    def test_actual_plans_generate_probes(self):
        from gin_byte_adapter import plan_binary,select_observation
        root=Path(os.environ['GIN_OTEL_BUILD']).resolve();go=os.environ.get('TRACEFUSION_GO','go')
        for variant in ('assign','partial','overwrite'):
            for role in ('upstream','downstream'):
                with tempfile.TemporaryDirectory() as tmp:
                    plan=plan_binary(root/variant/role/'gin-byte-target',go,dict(os.environ),Path(tmp),cross_role=role,tracing='otel')
                    self.assertTrue(gin_byte_capture.source(plan,1,SimpleNamespace(st_dev=0,st_ino=0)))
                    self.assertEqual(sorted(s['id'] for p in gin_byte_capture.physical_probes(plan) for s in p['sites']),plan['event_order'])
                    sparse=select_observation(plan,'boundary')
                    self.assertEqual(sparse['binary_sha256'],plan['binary_sha256'])
                    self.assertTrue(gin_byte_capture.source(sparse,1,SimpleNamespace(st_dev=0,st_ino=0)))
                    internal={s['address'] for s in plan['sites'] if s['op']=='instruction'}
                    retained={s['address'] for p in gin_byte_capture.physical_probes(sparse) for s in p['sites']}
                    self.assertFalse(internal & retained)
                    if role=='downstream':
                        self.assertIn('go.opentelemetry.io/otel/propagation.HeaderCarrier.Set',plan['scopes'])
                        reads=[s for s in plan['sites'] if s['op']=='source' and s['phase']=='pre']
                        self.assertEqual(reads[0]['snapshots'],{'path':{'pointer':'rcx','length_reg':'rdi'}})

    @unittest.skipUnless(os.environ.get('GIN_OTEL_BUILD'),'Set GIN_OTEL_BUILD for native HTTP/SDK integration')
    def test_native_http_and_real_sdk_parentage(self):
        root=Path(os.environ['GIN_OTEL_BUILD']).resolve()
        for variant in ('assign','partial','overwrite'):
            with tempfile.TemporaryDirectory() as tmp:
                out=Path(tmp);captures={};procs={};logs=[]
                try:
                    for role in ('upstream','downstream'):
                        cap=out/role;cap.mkdir();captures[role]=cap;inputs=fixtures(cap)
                        upstream=readiness(captures['upstream'],procs['upstream'])['address'] if role=='downstream' else ''
                        log=(cap/'target.stdout').open('w');err=(cap/'target.stderr').open('w');logs.extend([log,err])
                        proc=subprocess.Popen([str(root/variant/role/'gin-byte-target')],stdin=subprocess.PIPE,stdout=log,stderr=err,text=True)
                        procs[role]=proc
                        proc.stdin.write(json.dumps(dict(Inputs=str(inputs),Upstream=upstream,Service=role,TraceFile=str(cap/'spans.jsonl')))+'\n')
                        proc.stdin.close()
                    responses=client(captures['downstream'],root/'client/otel-client')
                    for role,proc in procs.items():
                        self.assertEqual(proc.wait(timeout=15),0,(captures[role]/'target.stderr').read_text())
                    documents=read_spans(captures);chains=span_chains(documents)
                    self.assertEqual(len(chains),8);self.assertEqual(sum(map(len,documents.values())),33)
                    self.assertEqual({trace_key(r['trace']) for r in responses},set(chains))
                    self.assertEqual(len({k[0] for k in chains}),1)
                    self.assertEqual(len({c['downstream_client_span'] for c in chains.values()}),8)
                    for response in responses:
                        self.assertEqual(response['status'],200)
                        self.assertGreater(response['elapsed_ns'],0)
                        self.assertEqual(json.loads(response['body']),{'result':[83,65,77,69]})
                finally:
                    for proc in procs.values():
                        if proc.poll() is None:proc.terminate();proc.wait(timeout=10)
                    for log in logs:log.close()

if __name__=='__main__':unittest.main()
