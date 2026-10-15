"""Behavioral checks for the cost protocol, using a real delayed HTTP server."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import run_sockshop_cost as cost
from sockshop import Client


class CostProtocolTests(unittest.TestCase):
    def test_same_business_configuration_and_only_observer_additions(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            original = root/'original'
            observed = root/'observed'
            original.mkdir()
            observed.mkdir()
            build = root/'build'
            a = cost.spec_for('original', original, build, 1.5, '768m')
            b = cost.spec_for('tracefusion', observed, build, 1.5, '768m')
            for role in a['services']:
                x, y = a['services'][role], b['services'][role]
                self.assertEqual(x['image'], y['image'])
                self.assertIn('@sha256:', x['image'])
                if role in cost.ROLES:
                    self.assertEqual(x['entrypoint'], y['entrypoint'])
                    self.assertEqual(x['environment']['JAVA_OPTS'], cost.JVM)
                    self.assertTrue(y['environment']['JAVA_OPTS'].startswith(cost.JVM+' -javaagent:'))
                    self.assertEqual(x['volumes'][0], y['volumes'][0])
                    self.assertEqual(len(y['volumes'])-len(x['volumes']), 3)
                    x.pop('environment'); y.pop('environment')
                    x.pop('volumes'); y.pop('volumes')
                self.assertEqual(x, y)

    def test_http_timing_and_queue_delay_are_distinct(self):
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                self.rfile.read(int(self.headers['Content-Length']))
                time.sleep(0.3)
                payload = json.dumps({'id': 'order', 'customerId': 'customer', 'items': [],
                                      'total': 4.99, 'customer': {'firstName': 'name'},
                                      'address': {'street': 'street'}, 'card': {'longNum': 'card', 'ccv': '123'}}).encode()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            with tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                prepared = []
                for i in range(4):
                    dest = root/str(i)
                    dest.mkdir()
                    fixture = {'customer_id': 'customer', 'expected_items': {}, 'firstName': 'name',
                               'address': {'street': 'street'}, 'card': {'longNum': 'card', 'ccv': '123'}}
                    prepared.append(({'expected_target': True}, cost.MeasuredClient(dest), fixture, {},
                                     {'case': str(i), 'message': 'trace/'+str(i)}))
                original_submit = cost.submit
                with patch.object(cost, 'submit', side_effect=lambda p, url, dest:
                                  original_submit(p, f'http://127.0.0.1:{server.server_port}', dest)):
                    result = cost.phase(prepared, 0.8, 5, 1, root)
                records = result['requests']
                self.assertEqual(len(records), 4)
                self.assertTrue(all(r['business_passed'] for r in records))
                self.assertGreaterEqual(result['drain_end_ns']-result['start_ns'], 1.2e9)
                last = records[-1]
                self.assertGreater(last['online_start_ns']-last['scheduled_ns'], 200e6)
                self.assertGreater(last['online_end_ns']-last['online_start_ns'], 290e6)
                self.assertLess(last['online_end_ns']-last['online_start_ns'], 800e6)
                self.assertTrue((root/'3/cost-request.json').exists())
        finally:
            server.shutdown()
            server.server_close()
            worker.join()

    def test_missing_acceptance_does_not_create_performance_output(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            args = cost.parser().parse_args(['run', '--out', str(root/'output'),
                                            '--build', str(root/'build'), '--correctness', str(root/'missing')])
            with self.assertRaises(FileNotFoundError):
                cost.run(args)
            self.assertFalse((root/'output').exists())

    def test_percentiles_keep_tail_and_na(self):
        self.assertEqual(cost.percentiles(list(range(1, 101))), {'p50': 50, 'p95': 95, 'p99': 99})
        self.assertEqual(cost.percentiles([]), {'p50': None, 'p95': None, 'p99': None})


if __name__=='__main__':
    unittest.main()
