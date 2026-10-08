"""Compare independently selected plans, real machine execution and HTTP routes."""
from copy import deepcopy
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from test_output_dependence import copy_plan,executed,uc
from test_gin_choice_provenance import project
from gin_byte_boundaries import bind
from gin_byte_provenance import fixtures
from gin_cross_provenance import readiness
from gin_otel_provenance import client
from gin_otel_boundaries import span_chains,read_spans
from gin_provenance_comparison import prepare_methods,probe_signature,summarize,run
from provenance_baselines import baseline_decision

CASES={'full':('output','output'), 'partial':('entry','entry'), 'none':('entry','entry'),
       'correlated':('entry','output'), 'correlated-dependent':('entry','entry')}


def fixture_plan(variant):
    p=copy_plan(variant)
    # Synthetic offsets are used only for unit comparison of probe identities.
    # Native integration below uses actual ELF offsets from the real planner.
    for s in p['sites']:s.setdefault('file_offset',s['address'])
    return p


class BaselineTests(unittest.TestCase):
    def test_independent_decisions_and_exhaustive_control_domain(self):
        for variant,expected in CASES.items():
            p=fixture_plan(variant)
            with patch('output_dependence.analyze_output_dependence',side_effect=AssertionError('Production oracle used')):
                basic=baseline_decision(p,'origin_sets');strong=baseline_decision(p,'path_sensitive')
                exhaustive=baseline_decision(p,'enumerate256')
            self.assertEqual((basic['mode'],strong['mode']),expected,(variant,basic,strong))
            self.assertEqual(strong['output_origin_sets'],exhaustive['output_origin_sets'])
            plans,decisions=prepare_methods(p)
            self.assertEqual(probe_signature(plans['path_sensitive']),probe_signature(plans['auto']))
            if variant=='correlated':self.assertNotEqual(probe_signature(plans['origin_sets']),probe_signature(plans['auto']))

    def test_no_fixture_names_or_concrete_data_in_selection(self):
        p=fixture_plan('correlated');before=baseline_decision(p,'path_sensitive')
        p['binary']='/unknown/name';p['scope']='unrelated';p['fixture_expected']='aux'
        after=baseline_decision(p,'path_sensitive')
        self.assertEqual(before['output_origin_sets'],after['output_origin_sets'])
        self.assertEqual(before['mode'],after['mode'])

    def test_summary_keeps_ties_and_rejects_different_origins(self):
        _,decisions=prepare_methods(fixture_plan('correlated'))
        records={'correlated':{}}
        for method in decisions:
            count=1232 if method=='full' else 344 if method=='origin_sets' else 336
            records['correlated'][method]={'0':dict(
                signature=[dict(ticket=i,byte_sources=['src']*4) for i in range(1,9)],
                metrics=dict(capture=dict(downstream=dict(events=count))))}
        summary=summarize({'correlated':decisions},records)
        self.assertTrue(summary['probe_plans_equal_to_path_sensitive'])
        self.assertEqual(summary['observations'][0]['current_events_saved_against_path_sensitive'],0)
        records['correlated']['auto']['0']['signature'][0]['byte_sources'][0]='aux'
        with self.assertRaises(ValueError):summarize({'correlated':decisions},records)

    def test_build_failure_is_archived_and_not_reported_as_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'failed';out.mkdir()
            with patch('gin_provenance_comparison.build_client',side_effect=RuntimeError('expected build failure')),redirect_stdout(io.StringIO()):
                self.assertEqual(run(out,variants=('correlated',)),1)
            with zipfile.ZipFile(out.with_suffix('.zip')) as z:
                self.assertFalse(json.loads(z.read('failed/run-status.json'))['completed'])
                self.assertIn('expected build failure',z.read('failed/runner-error.txt').decode())
                self.assertNotIn('failed/comparison.json',z.namelist())

    def test_unsafe_scope_and_control_partition_rejected(self):
        for fault in ('effect','bound','shared','flags','comparison','uninitialized','write'):
            p=fixture_plan('correlated');ir=p['instructions']
            if fault=='effect':ir[0]['op']='call'
            elif fault=='bound':p['max_steps']=2
            elif fault=='shared':p['runtime_input_ownership']='shared'
            elif fault=='flags':next(n for n in ir if n['op']=='jne')['op']='js'
            elif fault=='comparison':next(n for n in ir if n['op']=='cmp' and n['args'][0]['kind']=='mem')['args'][1]['value']=1
            elif fault=='uninitialized':
                for n in ir:
                    if n['op']=='mov' and n['args'][-1]['kind']=='mem':n.update(op='nop',args=[])
            else:next(n for n in ir if n['op']=='mov')['args'][-1]['base']='rdi'
            for method in ('origin_sets','path_sensitive'):
                self.assertEqual(baseline_decision(p,method)['status'],'unsupported',(fault,method))

    @unittest.skipUnless(uc,'Unicorn required')
    def test_actual_machine_origins_equal_with_all_selected_modes(self):
        for variant in CASES:
            for control in (0,1,127,128,255):
                d,p=executed(variant,control)
                plans,decisions=prepare_methods(fixture_plan(variant))
                full=bind(d,p);self.assertEqual(full['status'],'resolved',full)
                for method in plans:
                    sparse,sp=project(d,p,plans[method]['observation_mode'])
                    got=bind(sparse,sp);self.assertEqual(got['status'],'resolved',(variant,method,got))
                    self.assertEqual(got['results'][0]['provenance']['byte_sources'],
                                     full['results'][0]['provenance']['byte_sources'])
                local=control!=0 and variant not in ('full','correlated')
                for i,row in enumerate(full['results'][0]['provenance']['byte_sources']):
                    source=2 if local and not (variant=='partial' and i>=2) else 1
                    self.assertEqual(row['origins'],[dict(source=f'request:1:source:{source}',byte=i)])

    @unittest.skipUnless(uc,'Unicorn required')
    def test_required_entry_observation_is_not_guessed(self):
        d,p=executed('correlated-dependent',1)
        sparse,sp=project(d,p,'entry');sparse['events']=[e for e in sparse['events'] if e['op']!='instruction']
        for i,e in enumerate(sparse['events']):e['sequence']=i
        sparse['stats']['submitted']=len(sparse['events'])
        self.assertEqual(bind(sparse,sp)['status'],'unknown')

    @unittest.skipUnless(os.environ.get('GIN_COMPARISON_BUILD'),'Set GIN_COMPARISON_BUILD for native integration')
    def test_real_binary_plans_and_native_http(self):
        root=Path(os.environ['GIN_COMPARISON_BUILD'])/'build'
        for variant in ('kill-full','kill-partial','kill-none','correlated','correlated-dependent'):
            actual=json.loads((root/variant/'plan.json').read_text())
            if variant.startswith('correlated'):
                self.assertEqual(len(actual['runtime_input_sites']),2,'Compiler removed a tested condition')
            logical=variant.removeprefix('kill-');fixture=fixture_plan(logical)
            # Compiler changes must be visible; unit execution uses the same
            # machine instruction bytes as these newly built application leaves.
            def normalized(p):
                return [(n['code'],n['op'],n['args'],n['target']-p['entry'] if 'target' in n else None) for n in p['instructions']]
            self.assertEqual(normalized(actual),normalized(fixture))
            plans,_=prepare_methods(actual)
            self.assertEqual(probe_signature(plans['auto']),probe_signature(plans['path_sensitive']))
            with tempfile.TemporaryDirectory() as tmp:
                caps={};procs={};logs=[]
                try:
                    for role in ('upstream','downstream'):
                        cap=Path(tmp)/role;cap.mkdir();caps[role]=cap;inputs=fixtures(cap)
                        for ticket in range(1,9):(inputs/str(ticket)/'B.txt').write_bytes(b'LOCL')
                        address=readiness(caps['upstream'],procs['upstream'])['address'] if role=='downstream' else ''
                        log=(cap/'target.stdout').open('w');err=(cap/'target.stderr').open('w');logs.extend((log,err))
                        binary=root/('upstream' if role=='upstream' else variant)/'gin-byte-target'
                        p=subprocess.Popen([str(binary)],stdin=subprocess.PIPE,stdout=log,stderr=err,text=True);procs[role]=p
                        p.stdin.write(json.dumps(dict(Inputs=str(inputs),Upstream=address,Service=role,TraceFile=str(cap/'spans.jsonl')))+'\n');p.stdin.close()
                    responses=client(caps['downstream'],root/'client/otel-client')
                    for p in procs.values():self.assertEqual(p.wait(timeout=15),0)
                    self.assertEqual(len(span_chains(read_spans(caps))),8)
                    for r in responses:
                        expected=b'LOCL' if r['ticket']%4>=2 else b'SAME'
                        if variant in ('kill-full','correlated'):expected=b'SAME'
                        elif variant=='kill-partial':expected=expected[:2]+b'ME'
                        self.assertEqual(json.loads(r['body']),dict(result=list(expected)))
                finally:
                    for p in procs.values():
                        if p.poll() is None:p.terminate();p.wait(timeout=10)
                    for log in logs:log.close()


if __name__=='__main__':unittest.main()
