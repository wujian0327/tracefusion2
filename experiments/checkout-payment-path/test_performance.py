"""Protocol, isolation, corruption and paired-statistics checks; no kernel claims."""
import copy
import ctypes as ct
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import subprocess
import sys
from unittest.mock import patch

import payment_adapter as adapter
import performance as p
from test_replay import fixture


def serial_fixture():
    plan, doc = fixture()
    second = copy.deepcopy(doc['events'])
    for e in second:
        e['timestamp'] += len(doc['events'])
    return plan, doc['events'] + second


def encode(event):
    raw = adapter.Raw()
    for name in ('timestamp', 'pid_tid', 'g', 'site', 'error', 'flags', 'a', 'b', 'c', 'd', 'tag'):
        setattr(raw, name, event[name])
    for i, name in enumerate(adapter.GPRS):
        raw.registers[i] = event['registers'][name]
    return ct.string_at(ct.byref(raw), ct.sizeof(raw)) + b'\0' * 4


class ProtocolTests(unittest.TestCase):
    def test_serial_calls_reuse_addresses_but_not_replay_state(self):
        plan, events = serial_fixture()
        groups = p.split_invocations(list(reversed(events)), 2)
        results = []
        for group in groups:
            doc = dict(binary_sha256=plan['binary_sha256'], events=group, capture_errors=[], returncode=0,
                       stats=dict(submitted=len(group), lost=0, read_errors=0, submit_errors=0, namespace_errors=0))
            results.append(adapter.infer(plan, doc))
        self.assertEqual([r['status'] for r in results], ['exact_data_origins'] * 2)
        self.assertEqual(results[0]['origins'], results[1]['origins'])
        self.assertNotEqual(results[0]['source_identity'], results[1]['source_identity'])

    def test_missing_completion_is_not_repaired_by_next_start(self):
        _, events = serial_fixture()
        events = [e for i, e in enumerate(events) if not (e['kind'] == 'end' and i < len(events)//2)]
        with self.assertRaisesRegex(ValueError, 'previous completion'):
            p.split_invocations(events, 2)

    def test_missing_whole_call_stays_in_denominator(self):
        _, doc = fixture()
        with self.assertRaisesRegex(ValueError, 'invocation evidence'):
            p.split_invocations(doc['events'], 2)

    def test_cross_g_event_rejected(self):
        _, events = serial_fixture()
        events[20]['g'] += 1
        with self.assertRaisesRegex(ValueError, 'Cross-process/G'):
            p.split_invocations(events, 2)

    def test_duplicate_timestamp_rejected(self):
        _, events = serial_fixture()
        events[1]['timestamp'] = events[0]['timestamp']
        with self.assertRaisesRegex(ValueError, 'event order'):
            p.split_invocations(events, 2)

    def test_lost_samples_and_inconsistent_counts_rejected(self):
        stats = dict(submitted=2, samples=2, lost=0, read_errors=0, submit_errors=0, namespace_errors=0)
        p.check_capture(stats)
        for key, value in (('lost', 1), ('samples', 1), ('namespace_errors', 1)):
            with self.subTest(key=key), self.assertRaises(ValueError):
                p.check_capture(dict(stats, **{key: value}))

    def test_raw_roundtrip_replay_and_truncation(self):
        plan, events = serial_fixture()
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            sizes = {}
            with (folder/'samples.bin').open('wb') as f:
                for event in events:
                    data = encode(event)
                    f.write(p.SAMPLE_HEADER.pack(0, len(data))); f.write(data)
                    sizes[str(len(data))] = sizes.get(str(len(data)), 0) + 1
            decoded, got_sizes = p.decode_samples(folder/'samples.bin', plan)
            self.assertEqual(len(decoded), len(events))
            self.assertEqual(dict(got_sizes), sizes)
            stats = dict(submitted=len(events), samples=len(events), lost=0, read_errors=0, submit_errors=0, namespace_errors=0)
            p.save(folder/'capture.json', dict(capture_errors=[], returncode=0, binary_sha256=plan['binary_sha256'],
                                             total_stats=stats, total_samples=len(events), sample_sizes=sizes, warmup_samples=len(events)//2))
            truth = dict(sink_present=True, application_error=False, warmups=1, requests=1, output=[13,0],
                         origins={'Units':sorted(prefix+'.'+field for prefix in ('shipping','items[0].Cost','items[1].Cost') for field in ('Units','Nanos')),
                                  'Nanos':['items[0].Cost.Nanos','items[1].Cost.Nanos','shipping.Nanos']})
            p.save(folder/'truth.json', truth)
            result = p.replay_trial(plan, folder, 1, 1)
            self.assertEqual(result['metrics']['exact_fields'], 2)
            self.assertEqual(result['inference_requests'], 1)
            self.assertEqual(len((folder/'inference.jsonl').read_text().splitlines()), 2)
            bad_truth=copy.deepcopy(truth)
            bad_truth['origins']['Units']=[]
            p.save(folder/'truth.json',bad_truth)
            with self.assertRaisesRegex(ValueError,'failed queries retained'):
                p.replay_trial(plan,folder,1,1)
            failed=json.loads((folder/'evaluation.json').read_text())
            self.assertFalse(failed['all_passed'])
            self.assertEqual(failed['metrics']['query_fields'],2)
            self.assertEqual(failed['metrics']['wrong_definite_fields'],1)
            self.assertEqual(failed['metrics']['exact_fields'],1)
            data = (folder/'samples.bin').read_bytes()
            (folder/'samples.bin').write_bytes(data[:-1])
            with self.assertRaisesRegex(ValueError, 'Truncated'):
                p.decode_samples(folder/'samples.bin', plan)


class StatisticsTests(unittest.TestCase):
    def rows(self):
        rows = []
        for block, native in enumerate((10, 100)):
            for policy in p.POLICIES:
                latency = (20,100)[block] if policy == 'selected' else native
                row = dict(block=block, policy=policy, passed=True, p50_ns=latency, p95_ns=latency,
                           target_cpu_seconds=native, collector_cpu_seconds=1,
                           target_sampled_peak_rss_bytes=100, collector_sampled_peak_rss_bytes=200,
                           measured_events=10, measured_perf_bytes=2120, inference_ns=100)
                rows.append(row)
        return rows

    def test_pairing_uses_native_from_same_block(self):
        result = p.summarize(self.rows(), 2)
        self.assertEqual(result['aggregates']['selected']['p50_ratio_paired_median'], 1.5)
        self.assertEqual(result['aggregates']['selected']['p50_ns_block_median'], 60)
        self.assertEqual(result['aggregates']['native']['p50_ns_block_median'], 55)

    def test_incomplete_or_failed_block_rejected(self):
        rows = self.rows()
        with self.assertRaises(ValueError): p.summarize(rows[:-1], 2)
        rows[0]['passed'] = False
        with self.assertRaises(ValueError): p.summarize(rows, 2)

    def test_schedule_and_nearest_rank(self):
        self.assertEqual(p.schedule(10, 123), p.schedule(10, 123))
        self.assertTrue(all(set(b['policies']) == set(p.POLICIES) for b in p.schedule(10,123)))
        self.assertEqual(p.percentile(list(range(1,101)), .95), 95)
        self.assertEqual(p.percentile([1], .5), 1)

    def test_missing_metric_does_not_use_partial_block_median(self):
        rows=self.rows()
        rows[-1]['target_sampled_peak_rss_bytes']=None
        result=p.summarize(rows,2)['aggregates']['selected']
        self.assertIsNone(result['target_sampled_peak_rss_bytes_block_median'])
        self.assertEqual(result['missing_metric_trials']['target_sampled_peak_rss_bytes'],1)


class LifecycleTests(unittest.TestCase):
    # A fake gated executable verifies transport boundaries and failure cleanup.
    # It is not a checkout workload or native Go/BPF performance result.
    def fake(self, folder, fail=False):
        binary = folder/'fake-target'
        binary.write_text('''#!/usr/bin/env python3
import json, os, pathlib, sys, time
out=pathlib.Path(os.environ['TRACEFUSION_PERFORMANCE_OUT'])
assert sys.stdin.buffer.read(1)==b'x'
def save(name,data): (out/name).write_text(json.dumps(data))
save('warmup.done',{})
assert sys.stdin.buffer.read(1)==b'm'
''' + ('sys.exit(7)\n' if fail else '''time.sleep(.03)
save('measure.done',{})
assert sys.stdin.buffer.read(1)==b'q'
save('measurements.json',dict(warmups=1,requests=2,latency_ns=[100,200],wall_ns=300,cpu_start=dict(user_us=0,system_us=0),cpu_end=dict(user_us=10,system_us=20)))
save('truth.json',dict(warmups=1,requests=2))
'''))
        binary.chmod(0o755)
        return binary, dict(binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest())

    def test_native_phase_gates_and_resource_windows(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); binary,plan=self.fake(root)
            with patch.object(p,'rss',return_value=123456):
                capture=p.collect_trial(binary,plan,root/'trial','native',1,2,2)
            self.assertEqual(capture['returncode'],0)
            self.assertEqual(capture['measured_samples'],0)
            self.assertGreater(capture['collector_window_wall_ns'],0)
            self.assertGreater(capture['target_sampled_peak_rss_bytes'],0)
            self.assertTrue((root/'trial'/'measurements.json').exists())

    def test_unavailable_rss_is_recorded_not_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); binary,plan=self.fake(root)
            with patch.object(p,'rss',side_effect=OSError('proc unavailable')):
                capture=p.collect_trial(binary,plan,root/'trial','native',1,2,2)
            self.assertIsNone(capture['target_sampled_peak_rss_bytes'])
            self.assertIn('target',capture['rss_unavailable'])

    def test_standalone_collector_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);binary,plan=self.fake(root)
            p.save(root/'plan.json',plan)
            run=subprocess.run([sys.executable,str(Path(p.__file__)), '_collect','--binary',str(binary),
                                '--plan',str(root/'plan.json'),'--policy','native','--output',str(root/'trial'),
                                '--warmups','1','--requests','2','--timeout','2'],capture_output=True,text=True,timeout=10)
            self.assertEqual(run.returncode,0,run.stderr)
            self.assertEqual(json.loads((root/'trial'/'capture.json').read_text())['returncode'],0)

    def test_failed_target_retains_diagnostics(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); binary,plan=self.fake(root,True)
            with self.assertRaisesRegex(ValueError,'exited before'):
                p.collect_trial(binary,plan,root/'trial','native',1,2,2)
            capture=json.loads((root/'trial'/'capture.json').read_text())
            self.assertEqual(capture['returncode'],7)
            self.assertTrue(capture['capture_errors'])


if __name__=='__main__': unittest.main()
