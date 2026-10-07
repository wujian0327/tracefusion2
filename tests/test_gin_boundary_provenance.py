"""Sparse observation regression, using traces authored independently of replay."""
from copy import deepcopy
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from test_go_byte_provenance import evidence as loop_evidence
from test_gin_byte_provenance import evidence,combine
from gin_byte_adapter import select_observation
from gin_byte_boundaries import bind
from byte_provenance import infer
from gin_otel_compare import comparison_signature,summarize
import gin_byte_capture


def project(document):
    d=deepcopy(document)
    d['events']=[e for e in d['events'] if e['op']!='instruction']
    for i,e in enumerate(d['events']):e['sequence']=i
    d['stats']['submitted']=len(d['events'])
    return d


def boundary(plan):
    return select_observation(dict(plan,scope=plan.get('scope','Synthetic fixture')),'boundary')


class BoundaryTests(unittest.TestCase):
    def test_interleaved_selection_and_overwrite_match_full_per_byte(self):
        for variant in ('assign','partial','overwrite'):
            a,p=evidence(variant,ticket=1)
            c,_=evidence(variant,True,g=0x999,offset=0x10000,ticket=2)
            doc=combine([a,c]);full=bind(doc,p);sparse=bind(project(doc),boundary(p))
            self.assertEqual(sparse['status'],'resolved',sparse)
            self.assertEqual(sparse['concurrency'],full['concurrency'])
            for f,b in zip(full['results'],sparse['results']):
                for key in ('sources','byte_sources','source_versions','overwritten_sources','noncontributing_reads','total_writes','output'):
                    self.assertEqual(f['provenance'][key],b['provenance'][key],(variant,key))
                self.assertTrue(all(s['event_sequence'] is None and s['evidence']=='modeled-from-boundaries'
                                    for s in b['provenance']['instruction_steps']))

    def test_loop_index_and_processing_replayed_from_entry(self):
        for reverse in (False,True):
            for use_c in (False,True):
                d,p,oracle=loop_evidence(reverse,use_c)
                result=infer(project(d),boundary(p))
                self.assertEqual(result['status'],'resolved_under_instruction_model',result)
                self.assertEqual(result['byte_sources'],oracle['byte_sources'])
                self.assertEqual(result['output'],oracle['output'])

    def test_missing_or_contradictory_evidence_rejected(self):
        for failure in ('contract','internal_event','missing_entry','unknown_pointer','return','json'):
            d,p=evidence();b=boundary(p);reduced=project(d)
            if failure=='contract':b.pop('replay_contract')
            elif failure=='internal_event':reduced=d
            elif failure=='missing_entry':
                reduced['events']=[e for e in reduced['events'] if not(e['op']=='work' and e['phase']=='pre')]
                for i,e in enumerate(reduced['events']):e['sequence']=i
                reduced['stats']['submitted']=len(reduced['events'])
            elif failure=='unknown_pointer':
                e=next(e for e in reduced['events'] if e['op']=='work' and e['phase']=='pre')
                v=e['values']['src'];v.update(pointer=0xF000,key='f000:4');e['registers']['rbx']=0xF000
            elif failure=='return':next(e for e in reduced['events'] if e['op']=='work' and e['phase']=='post')['registers']['rax']+=1
            else:next(e for e in reduced['events'] if e['op']=='json' and e['phase']=='pre')['values']['value']['hex']='00000000'
            self.assertEqual(bind(reduced,b)['status'],'unknown',failure)
        d,p=evidence()
        self.assertEqual(bind(project(d),p)['status'],'unknown','Full mode must still require instruction evidence')

    def test_internal_probe_addresses_are_not_attached(self):
        _,p=evidence();b=boundary(p)
        probes=gin_byte_capture.physical_probes(b)
        removed={s['address'] for s in p['sites'] if s['op']=='instruction'}
        self.assertFalse(removed & {s['address'] for probe in probes for s in probe['sites']})
        attached=[s['id'] for probe in probes for s in probe['sites']]
        self.assertEqual(sorted(attached),b['event_order'])
        code=gin_byte_capture.source(b,1,SimpleNamespace(st_dev=0,st_ino=0))
        self.assertTrue(code)
        self.assertTrue(all('site' not in n for n in b['instructions']))
        self.assertTrue(all('site' in n for n in p['instructions']))

    def test_pair_comparison_rejects_byte_origin_or_binary_changes(self):
        full=dict(round=1,mode='full',signature=[['A',0],['B',1]],binary_sha256={'up':'abc'},
                  events=100,instruction_events=60,mean_request_ms=2)
        sparse=dict(full,mode='boundary',events=40,instruction_events=0,mean_request_ms=1)
        report=summarize([full,sparse]);self.assertEqual(report['event_reduction_fraction'],0.6)
        for changed in (dict(sparse,signature=[['B',1],['A',0]]),dict(sparse,binary_sha256={'up':'def'})):
            with self.assertRaises(ValueError):summarize([full,changed])

    def test_signature_ignores_run_specific_ids_but_preserves_byte_origins(self):
        def fixture(root,rid,trace,reverse=False):
            cap=root/'downstream/capture';cap.mkdir(parents=True)
            (cap/'client-responses.json').write_text(json.dumps([dict(trace=trace,ticket=1)]))
            source='upstream/request:%d:source:1'%rid
            nodes=[dict(id=source,kind='source',path=str(root/'upstream/capture/inputs/1/A.txt'))];edges=[]
            for i in range(4):
                byte=3-i if reverse else i;s=source+'/byte:'+str(byte);target='downstream/request:%d:output-byte:%d'%(rid,i)
                nodes.extend([dict(id=s,kind='source-byte',byte=byte),dict(id=target,kind='output-byte')])
                edges.append(dict(source=s,target=target,kind='data'))
            row=dict(downstream_request=rid,request_trace=trace,body='same',transfer_contributes=True,graph=dict(nodes=nodes,edges=edges))
            (root/'joined.json').write_text(json.dumps(dict(status='resolved',results=[row])))
            return comparison_signature(root)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);a=fixture(root/'a',1,'trace1');b=fixture(root/'b',9,'trace2')
            self.assertEqual(a,b)
            self.assertNotEqual(a,fixture(root/'c',9,'trace3',True))


if __name__=='__main__':unittest.main()
