"""Collector lifecycle checks with a fake BCC transport, not kernel evidence."""
import ctypes
import json
from pathlib import Path
import signal
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import hybrid_provenance as common


class Event(ctypes.Structure):
    _fields_ = [('pid_tid', ctypes.c_uint64), ('sequence', ctypes.c_uint64),
                ('regs', ctypes.c_uint64 * 16), ('inputs', ctypes.c_uint32 * 8),
                ('outputs', ctypes.c_uint32 * 8), ('stack', ctypes.c_uint64 * 32),
                ('read_data', ctypes.c_ubyte * 32)]


class CaptureTransportTests(unittest.TestCase):
    def capture(self, submit_errors=0, lost_events=0, errno_map=True, use_setup=False):
        timeline = []
        objects = [Event(pid_tid=(123 << 32) | 123, sequence=i) for i in range(2)]
        for obj in objects: obj.read_data[0] = 255

        class Process:
            pid = 123
            returncode = None
            polls = 0

            def send_signal(self, sig):
                assert sig == signal.SIGCONT and timeline[-1] == 'open'
                timeline.append('resume')

            def poll(self):
                self.polls += 1
                if self.polls > 1:
                    self.returncode = 0
                return self.returncode

        class Metrics:
            def __getitem__(self, key):
                return SimpleNamespace(value=[2 + submit_errors, submit_errors, 0, 2 + submit_errors][key.value])

        class Errnos:
            def items(self):
                return [(ctypes.c_int(28), ctypes.c_uint64(submit_errors))] if submit_errors else []

        class Buffer:
            def open_perf_buffer(self, receive, lost_cb, page_cnt):
                self.receive, self.lost = receive, lost_cb
                self.pages = page_cnt
                timeline.append('open')

            def event(self, data):
                return data

        class BPF:
            polls = 0

            def __init__(self, **kwargs):
                self.buffer = Buffer()

            def __getitem__(self, key):
                return {'events': self.buffer, 'metrics': Metrics(), 'submit_errnos': Errnos()}[key]

            def perf_buffer_poll(self, timeout):
                assert 'resume' in timeline
                if self.polls < 2:
                    self.buffer.receive(0, objects[self.polls], ctypes.sizeof(Event))
                if self.polls == 0 and lost_events:
                    self.buffer.lost(0, lost_events)
                self.polls += 1

            def cleanup(self):
                timeline.append('cleanup')

        config = json.loads((common.ROOT / 'scenarios/loop-calls-provenance/config.json').read_text())
        process, bpf = Process(), BPF()
        module = SimpleNamespace(BPF=lambda **kw: bpf, __version__='fake-test')
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            with patch.dict(sys.modules, bcc=module), \
                 patch.object(common.subprocess, 'Popen', return_value=process), \
                 patch.object(common, 'wait_stopped'), \
                 patch.object(common, 'runtime_metadata', return_value={}), \
                 patch.object(common, 'attach_probes', return_value=[]):
                events, stats, _ = common.record_bpf(out / 'demo', [], config, out,
                    source_generator=lambda *_: 'BPF_HASH(submit_errnos, s32, u64, 32);' if errno_map else '',
                    setup_fn=(lambda *args: timeline.append('setup')) if use_setup else None)
            self.assertEqual([e['sequence'] for e in events], [0, 1])
            self.assertTrue(all(e['read_data'] == [255] + [0]*31 for e in events))
            self.assertEqual([json.loads(l) for l in (out / 'events.jsonl').read_text().splitlines()], events)
            self.assertEqual(json.loads((out / 'capture.json').read_text()), stats)
        self.assertEqual(bpf.polls, 4)  # one active poll plus three exit drains
        self.assertEqual(timeline, (['setup'] if use_setup else []) + ['open', 'resume', 'cleanup'])
        self.assertEqual(bpf.buffer.pages, 1024)
        return stats

    def test_buffer_opened_before_resume_and_tail_events_persisted(self):
        stats = self.capture()
        self.assertEqual(stats['received_events'], 2)
        self.assertEqual(stats['submit_error_errnos'], {})
        self.assertEqual(stats['perf_buffer_pages_per_cpu'], 1024)
        self.assertEqual(stats['attempted_events'], stats['received_events'])

    def test_submit_and_lost_errors_preserved_without_repair(self):
        stats = self.capture(submit_errors=301, lost_events=4)
        self.assertEqual(stats['submit_errors'], 301)
        self.assertEqual(stats['submit_error_errnos'], {'28': 301})
        self.assertEqual(stats['lost_events'], 4)
        self.assertEqual(stats['received_events'], 2)
        self.assertFalse(common.evaluate({'results': [], 'issues': []}, [], stats, [])['capture_clean'])

    def test_optional_boundary_setup_precedes_resume_and_serializes_bytes(self):
        self.capture(use_setup=True)

    def test_legacy_collector_without_errno_map(self):
        stats = self.capture(errno_map=False)
        self.assertNotIn('submit_error_errnos', stats)


if __name__ == '__main__':
    unittest.main()
