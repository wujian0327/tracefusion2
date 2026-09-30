import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from http_dataset import build, export_dataset, project
from http_baseline import reconstruct
from http_score import score
from trace_validation import validate_all


def fixture():
    spans, trace = [], 'a' * 32
    def add(service, kind, parent=None, path='/', method='GET', peer=None):
        ident = '%016x' % (len(spans) + 1)
        tags = {'http.method': method, 'http.status_code': '200'}
        tags['http.url' if kind == 'CLIENT' else 'http.target'] = (
            'http://' + peer + path if kind == 'CLIENT' else path)
        s = {'traceId': trace, 'id': ident, 'name': 'fixture', 'kind': kind,
             'localEndpoint': {'serviceName': service}, 'timestamp': 1000000 + len(spans) * 100,
             'duration': 100000 - len(spans) * 200, 'tags': tags}
        if parent: s['parentId'] = parent
        spans.append(s)
        return ident
    root = add('test-client', 'CLIENT', path='/orders', method='POST', peer='front-end')
    front = add('front-end', 'SERVER', root, '/orders', 'POST')
    def call(parent, caller, callee, path, method='GET'):
        client = add(caller, 'CLIENT', parent, path, method, callee)
        return add(callee, 'SERVER', client, path, method)
    call(front, 'front-end', 'user', '/customers/C1')
    call(front, 'front-end', 'user', '/customers/C1/addresses')
    call(front, 'front-end', 'user', '/customers/C1/cards')
    orders = call(front, 'front-end', 'orders', '/orders', 'POST')
    call(orders, 'orders', 'user', '/customers/C1')
    call(orders, 'orders', 'user', '/addresses/A1')
    call(orders, 'orders', 'user', '/cards/K1')
    call(orders, 'orders', 'carts', '/carts/C1/items')
    call(orders, 'orders', 'payment', '/paymentAuth', 'POST')
    shipping = call(orders, 'orders', 'shipping', '/shipping', 'POST')
    # Background is intentionally unlabelled and must stay in algorithm input.
    health = add('user', 'SERVER', path='/health')
    spans[-1]['traceId'] = 'b' * 32
    manifest = [{'trace_id': trace, 'span_id': root, 'customer_id': 'C1',
                 'address_id': 'A1', 'card_id': 'K1'}]
    return spans, manifest, shipping


class HttpEvaluationTests(unittest.TestCase):
    def test_blind_input_keeps_background_and_has_no_private_ids(self):
        spans, manifest, _ = fixture()
        observations, queries, oracle = build(spans, manifest)
        self.assertEqual(len(observations), 22)
        self.assertTrue(any(o['path'] == '/health' for o in observations))
        self.assertEqual(len(oracle['queries'][0]['nodes']), 21)
        self.assertEqual(len(oracle['queries'][0]['edges']), 20)
        text = json.dumps([observations, queries])
        for s in spans:
            self.assertNotIn(s['traceId'], text)
            self.assertNotIn(s['id'], text)
        self.assertNotIn('parent', text)

    def test_projection_ignores_ids_headers_annotations_and_query_string(self):
        spans, _, _ = fixture()
        span = copy.deepcopy(spans[2]); expected = project(span)
        span.update(traceId='c' * 32, id='d' * 16, parentId='e' * 16)
        span['annotations'] = [{'value': 'trace-secret'}]
        span['tags']['http.request.header.traceparent'] = 'trace-secret'
        span['tags']['http.url'] += '?trace_id=trace-secret'
        self.assertEqual(project(span), expected)

    def test_queue_failure_and_async_http_remain_outside_sync_oracle(self):
        spans, manifest, shipping = fixture()
        producer = {'traceId': 'a' * 32, 'id': 'e' * 16, 'parentId': shipping,
                    'localEndpoint': {'serviceName': 'shipping'}, 'kind': 'PRODUCER',
                    'name': 'publish', 'timestamp': 1000000, 'duration': 10, 'tags': {}}
        consumer = dict(producer, id='f' * 16, parentId=producer['id'], kind='CONSUMER',
                        localEndpoint={'serviceName': 'queue-master'}, tags={'error': ''})
        async_http = dict(producer, id='d' * 16, parentId=consumer['id'], kind='SERVER',
                          localEndpoint={'serviceName': 'user'},
                          tags={'http.method': 'GET', 'http.target': '/async-background'})
        spans += [producer, consumer, async_http]
        self.assertEqual(validate_all(spans, manifest)['execution_status'], 'failed')
        report = validate_all(spans, manifest, scope='synchronous-http')
        self.assertEqual(report['status'], 'passed')
        self.assertEqual(report['execution_status'], 'no_recorded_errors')
        observations, _, oracle = build(spans, manifest)
        self.assertTrue(any(o['path'] == '/async-background' for o in observations))
        self.assertEqual(len(oracle['queries'][0]['nodes']), 21)

    def test_missing_http_parent_prevents_oracle_export(self):
        spans, manifest, _ = fixture()
        spans[4]['parentId'] = 'f' * 16
        with self.assertRaises(ValueError): build(spans, manifest)

    def test_duplicate_or_uncovered_queries_prevent_export(self):
        spans, manifest, _ = fixture()
        with self.assertRaises(ValueError): build(spans, manifest * 2)
        with self.assertRaises(ValueError): build(spans, [])

    def test_exact_empty_and_extra_predictions_are_scored(self):
        spans, manifest, _ = fixture()
        observations, _, oracle = build(spans, manifest)
        q = oracle['queries'][0]
        prediction = {'queries': [{'query_id': q['query_id'], 'root_event_id': q['root_event_id'],
                                    'edges': copy.deepcopy(q['edges'])}]}
        self.assertEqual(score(oracle, prediction)['exact_chain_match_rate'], 1)
        self.assertEqual(score(oracle, {'queries': []})['edge_micro']['fn'], 20)
        health = next(o['event_id'] for o in observations if o['path'] == '/health')
        prediction['queries'][0]['edges'].append({'parent': q['root_event_id'], 'child': health, 'relation': 'local'})
        result = score(oracle, prediction)
        self.assertEqual(result['edge_micro']['fp'], 1)
        self.assertEqual(result['request_membership_micro']['fp'], 1)
        prediction['queries'][0]['edges'][0]['child'] = 'unknown'
        with self.assertRaises(ValueError): score(oracle, prediction)

    def test_baseline_can_run_with_only_public_files(self):
        spans, manifest, _ = fixture()
        observations, queries, _ = build(spans, manifest)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'observations.json').write_text(json.dumps(observations))
            (root / 'queries.json').write_text(json.dumps(queries))
            out = root / 'prediction.json'
            p = subprocess.run([sys.executable, str(ROOT / 'scripts/http_baseline.py'),
                                str(root), '--out', str(out)], capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertEqual(len(json.loads(out.read_text())['queries']), 1)
        observations[0]['trace_id'] = 'a' * 32
        with self.assertRaises(ValueError): reconstruct(observations, queries)

    def test_equal_cost_transport_candidates_abstain(self):
        spans, manifest, _ = fixture()
        observations, queries, _ = build(spans, manifest)
        client = next(o for o in observations if o['kind'] == 'CLIENT' and o['peer_service'] == 'payment')
        server = next(o for o in observations if o['kind'] == 'SERVER' and o['service'] == 'payment')
        duplicate = dict(server, event_id='new-ambiguous-event')
        prediction = reconstruct(observations + [duplicate], queries)
        self.assertGreater(prediction['ambiguous_candidate_count'], 0)
        edges = prediction['queries'][0]['edges']
        self.assertFalse(any(e['parent'] == client['event_id'] and e['relation'] == 'transport' for e in edges))

    def test_zip_export_preserves_original_and_separates_views(self):
        spans, manifest, _ = fixture()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); bundle = root / 'run.zip'
            with zipfile.ZipFile(bundle, 'w') as z:
                z.writestr('oracle/spans-final.json', json.dumps(spans))
                z.writestr('oracle/orders.json', json.dumps(manifest))
            before = bundle.read_bytes()
            report = export_dataset(bundle, root / 'dataset')
            self.assertEqual(report['observations'], 22)
            self.assertEqual(bundle.read_bytes(), before)
            self.assertEqual({p.name for p in (root / 'dataset/algorithm-input').iterdir()},
                             {'observations.json', 'queries.json'})
            self.assertTrue((root / 'dataset/oracle/reference.json').exists())


if __name__ == '__main__': unittest.main()
