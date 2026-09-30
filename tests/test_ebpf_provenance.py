import json
from pathlib import Path
import socket
import struct
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import ebpf_provenance as app
import ebpf_capture as capture
import sockshop_ebpf as runner


def packet(seq, data=b'', flags=16, stamp=1, ident=1):
    return {'seq': seq, 'data': data, 'flags': flags, 'time_us': stamp, 'packet': ident}


def frame(src, dst, sport, dport, seq, flags, payload=b''):
    tcp = struct.pack('!HHIIBBHHH', sport, dport, seq, 0, 5 << 4, flags, 65535, 0, 0) + payload
    ip = struct.pack('!BBHHHBBH4s4s', 0x45, 0, 20 + len(tcp), 0, 0, 64, 6, 0,
                     socket.inet_aton(src), socket.inet_aton(dst))
    return b'\0' * 12 + b'\x08\x00' + ip + tcp


def message(body, response=False):
    data = json.dumps(body).encode()
    first = b'HTTP/1.1 201 Created' if response else b'POST /orders HTTP/1.1'
    return first + b'\r\nContent-Type: application/json\r\nContent-Length: ' + str(len(data)).encode() + b'\r\n\r\n' + data


def transaction(ident, client, server, start, end, request, response):
    def m(value, a, b):
        return {'json': value, 'start_us': a, 'end_us': b, 'packet_ids': [a, b]}
    return {'id': ident, 'client': client, 'server': server, 'method': 'POST', 'target': '/orders',
            'request': m(request, start, start + 1), 'response': m(response, end - 1, end)}


class ReassemblyTests(unittest.TestCase):
    def test_reordered_segments_retransmissions_and_sequence_wrap(self):
        data, evidence = app.reassemble([
            packet(0xfffffffe, flags=2), packet(2, b'def', stamp=4),
            packet(0xffffffff, b'abc', stamp=2), packet(0xffffffff, b'abc', stamp=5)])
        self.assertEqual(data, b'abcdef')
        self.assertEqual(len(evidence), 2)

    def test_gap_conflict_missing_handshake_and_fin_loss_fail_closed(self):
        cases = [
            [packet(100, flags=2), packet(102, b'b')],
            [packet(100, flags=2), packet(101, b'a'), packet(101, b'b')],
            [packet(101, b'abc')],
            [packet(100, flags=2), packet(101, b'a'), packet(105, flags=17)],
        ]
        for packets in cases:
            with self.subTest(packets=packets), self.assertRaises(ValueError):
                app.reassemble(packets)

    def test_chunked_keepalive_and_interim_response(self):
        data = (b'HTTP/1.1 100 Continue\r\n\r\n'
                b'HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n'
                b'7\r\n{"x":1}\r\n0\r\nTrailer: yes\r\n\r\n' + message({'x': 2}, True))
        parsed = app.http_messages(data, [(0, len(data), 1, 1)], response=True)
        self.assertEqual([p['status'] for p in parsed], [100, 200, 201])
        self.assertEqual(parsed[1]['json'], {'x': 1})
        self.assertEqual(parsed[2]['json'], {'x': 2})

    def test_incomplete_or_ambiguous_http_framing_is_rejected(self):
        cases = [message({'x': 1}, True)[:-1],
                 b'HTTP/1.1 200 OK\r\n\r\nabc',
                 b'HTTP/1.1 200 OK\r\nContent-Length: 0\r\nTransfer-Encoding: chunked\r\n\r\n',
                 b'HTTP/1.1 200 OK\r\nContent-Length: 0\r\nContent-Length: 0\r\n\r\n']
        for data in cases:
            with self.subTest(data=data), self.assertRaises(ValueError):
                app.http_messages(data, [(0, len(data), 1, 1)], response=True)

    def test_pcap_to_order_query_and_no_fake_accuracy(self):
        order = {'id': 'order1', 'card': {'longNum': '4111111111111111', 'ccv': '123'}}
        req, res = message({}), message(order, True)
        src, dst = '10.0.0.1', '10.0.0.2'
        frames = [frame(src, dst, 20000, 8079, 100, 2), frame(dst, src, 8079, 20000, 800, 18),
                  frame(src, dst, 20000, 8079, 101, 24, req),
                  frame(dst, src, 8079, 20000, 801 + 30, 24, res[30:]),
                  frame(dst, src, 8079, 20000, 801, 24, res[:30])]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'packets.pcap'
            with path.open('wb') as f:
                f.write(struct.pack('<IHHIIII', 0xa1b2c3d4, 2, 4, 0, 0, 262144, 1))
                for i, raw in enumerate(frames):
                    f.write(struct.pack('<IIII', i + 1, 0, len(raw), len(raw))); f.write(raw)
            report = app.analyze(path, {dst: 'front-end'}, Path(tmp) / 'analysis', [{'order_id': 'order1'}])
            self.assertEqual(report['transactions'], 1)
            self.assertEqual(report['sinks_observed'], 2)
            self.assertIsNone(report['field_lineage_accuracy'])
            self.assertEqual(report['reconstruction_issues'], [])

    def test_truncated_pcap_is_not_silent(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'packets.pcap'
            p.write_bytes(struct.pack('<IHHIIII', 0xa1b2c3d4, 2, 4, 0, 0, 262144, 1) + b'broken')
            with self.assertRaises(ValueError):
                list(app.read_pcap(p))


class GraphTests(unittest.TestCase):
    def setUp(self):
        self.card = {'longNum': '4111111111111111', 'ccv': '123'}
        self.order = {'id': 'order1', 'card': self.card}
        self.tx = [transaction('outer', 'external-client', 'front-end', 1, 100, {}, self.order),
                   transaction('inner', 'front-end', 'orders', 10, 90, {}, self.order),
                   transaction('source', 'orders', 'user', 20, 30, {}, self.card),
                   transaction('payment', 'orders', 'payment', 40, 50, self.card, {'authorised': True})]

    def test_source_reachable_but_payment_ack_not_card_source(self):
        graph = app.build_graph(self.tx)
        result = app.query_graph(graph, self.tx, [{'order_id': 'order1'}])[0]
        self.assertTrue(any(n['transaction'] == 'source' for n in result['nodes']))
        self.assertFalse(any(n['transaction'] == 'payment' for n in result['nodes']))
        self.assertFalse(result['unique_origin_proven'])

    def test_equal_repeated_reads_remain_multiple_candidates(self):
        self.tx.append(transaction('source2', 'orders', 'user', 31, 39, {}, self.card))
        graph = app.build_graph(self.tx)
        result = app.query_graph(graph, self.tx, [{'order_id': 'order1'}])[0]
        self.assertTrue({'source', 'source2'} <= {n['transaction'] for n in result['nodes']})
        self.assertFalse(result['unique_origin_proven'])

    def test_old_or_future_equal_values_not_joined(self):
        self.tx.extend([transaction('old', 'orders', 'user', 2, 5, {}, self.card),
                        transaction('future', 'orders', 'user', 101, 110, {}, self.card)])
        graph = app.build_graph(self.tx)
        result = app.query_graph(graph, self.tx, [{'order_id': 'order1'}])[0]
        self.assertFalse({'old', 'future'} & {n['transaction'] for n in result['nodes']})

    def test_concurrent_contexts_are_not_asserted_to_be_causal(self):
        self.tx.append(transaction('other', 'external-client', 'orders', 11, 95, {}, self.order))
        graph = app.build_graph(self.tx)
        candidates = [e for e in graph['edges'] if e['kind'] == 'candidate_exact_value']
        self.assertTrue(any(set(e['contexts']) == {'inner', 'other'} for e in candidates))
        self.assertTrue(all('NOT proven' in e['meaning'] for e in candidates))

    def test_transformed_value_not_fabricated_as_exact_match(self):
        self.tx[2]['response']['json'] = {'longNum': 'different_value'}
        graph = app.build_graph(self.tx)
        result = app.query_graph(graph, self.tx, [{'order_id': 'order1'}])[0]
        self.assertFalse(any(n['transaction'] == 'source' for n in result['nodes']))

    def test_missing_sink_and_missing_capture_statistics_cannot_pass(self):
        graph = app.build_graph(self.tx)
        result = app.query_graph(graph, self.tx, [{'order_id': 'missing'}])
        self.assertTrue(all(r['status'] == 'sink_not_observed' for r in result))
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp); (out / 'analysis').mkdir()
            app.save(out / 'analysis/transactions.json', [])
            report = runner.validate_capture(out, [], {}, {'reconstruction_issues': []})
            self.assertEqual(report['status'], 'incomplete')

    def test_filter_is_ip_scoped_and_retains_all_tcp_segments(self):
        source = capture.filter_source({'10.0.0.2': 'front-end'})
        self.assertIn('167772162u', source)
        self.assertNotIn('TF2_IP_FILTER', source)
        self.assertNotIn('GET', source)
        with self.assertRaises(ValueError):
            capture.filter_source({})


if __name__ == '__main__':
    unittest.main()
