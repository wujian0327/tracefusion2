#!/usr/bin/env python3
"""Offline IPv4/TCP/HTTP evidence reconstruction; NOT a taint tracker.

Only wire transport edges are directly observed. Equal-value intra-service
edges are candidates, never execution-level field-lineage ground truth.
"""
import argparse
from collections import defaultdict
import gzip
import hashlib
import io
import json
from pathlib import Path
import socket
import struct

MAX_STREAM = 8 * 1024 * 1024


def save(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n')


def read_pcap(path):
    with Path(path).open('rb') as f:
        header = f.read(24)
        if len(header) != 24 or struct.unpack('<IHHIIII', header) != (
                0xa1b2c3d4, 2, 4, 0, 0, 262144, 1):
            raise ValueError('Expected this recorder\'s little-endian Ethernet PCAP')
        number = 0
        while True:
            h = f.read(16)
            if not h:
                return
            if len(h) != 16:
                raise ValueError('Truncated PCAP record header')
            sec, usec, length, original = struct.unpack('<IIII', h)
            if length != original or length > 262144:
                raise ValueError('Truncated or oversized PCAP packet')
            packet = f.read(length)
            if len(packet) != length:
                raise ValueError('Truncated PCAP packet data')
            number += 1
            yield number, sec * 10**6 + usec, packet


def tcp_packet(raw):
    if len(raw) < 14 or raw[12:14] != b'\x08\x00':
        return None
    ip = raw[14:]
    if len(ip) < 20 or ip[0] >> 4 != 4 or ip[9] != 6:
        return None
    ihl, total = (ip[0] & 15) * 4, int.from_bytes(ip[2:4], 'big')
    if int.from_bytes(ip[6:8], 'big') & 0x3fff:
        raise ValueError('IPv4 fragmentation unsupported')
    if ihl < 20 or total > len(ip) or total < ihl + 20:
        raise ValueError('Incomplete IPv4/TCP packet')
    tcp = ip[ihl:total]
    thl = (tcp[12] >> 4) * 4
    if thl < 20 or thl > len(tcp):
        raise ValueError('Invalid TCP header')
    sport, dport, seq, ack = struct.unpack('!HHII', tcp[:12])
    return {'src': socket.inet_ntoa(ip[12:16]), 'dst': socket.inet_ntoa(ip[16:20]),
            'sport': sport, 'dport': dport, 'seq': seq, 'ack': ack,
            'flags': tcp[13], 'data': tcp[thl:]}


def reassemble(packets):
    syns = {p['seq'] for p in packets if p['flags'] & 2}
    if len(syns) != 1:
        raise ValueError('Missing/ambiguous SYN; midstream reconstruction is refused')
    initial = (next(iter(syns)) + 1) & 0xffffffff
    segments = []
    fin_offsets = set()
    for p in packets:
        offset = ((p['seq'] + bool(p['flags'] & 2)) - initial) & 0xffffffff
        if p['data']:
            if offset + len(p['data']) > MAX_STREAM:
                raise ValueError('Stream exceeds bounded capture window')
            segments.append((offset, p['data'], p['time_us'], p['packet']))
        if p['flags'] & 1:
            fin_offsets.add(offset + len(p['data']))
    segments.sort(key=lambda x: (x[0], x[2]))
    content, evidence = bytearray(), []
    for offset, data, stamp, packet in segments:
        if offset > len(content):
            raise ValueError('TCP sequence gap; refusing to concatenate missing bytes')
        overlap = min(len(content) - offset, len(data))
        if content[offset:offset + overlap] != data[:overlap]:
            raise ValueError('Conflicting TCP retransmission')
        if overlap < len(data):
            start = len(content)
            content.extend(data[overlap:])
            evidence.append((start, len(content), stamp, packet))
    if fin_offsets and fin_offsets != {len(content)}:
        raise ValueError('Missing stream tail or inconsistent FIN')
    return bytes(content), evidence


def chunked_body(data, start):
    pos, body = start, bytearray()
    while True:
        end = data.find(b'\r\n', pos)
        if end < 0:
            raise ValueError('Incomplete chunk header')
        size = int(data[pos:end].split(b';')[0], 16)
        if size < 0 or size > MAX_STREAM:
            raise ValueError('Invalid chunk size')
        pos = end + 2
        if size == 0:
            if data[pos:pos + 2] == b'\r\n':
                return bytes(body), pos + 2
            end = data.find(b'\r\n\r\n', pos)
            if end < 0:
                raise ValueError('Incomplete chunk trailers')
            return bytes(body), end + 4
        if data[pos + size:pos + size + 2] != b'\r\n':
            raise ValueError('Incomplete chunk body')
        body.extend(data[pos:pos + size])
        if len(body) > MAX_STREAM:
            raise ValueError('HTTP body exceeds limit')
        pos += size + 2


def http_messages(data, evidence, response=False):
    messages, pos = [], 0
    while pos < len(data):
        start = pos
        end = data.find(b'\r\n\r\n', pos)
        if end < 0:
            raise ValueError('Incomplete HTTP headers')
        lines = data[pos:end].decode('iso-8859-1').split('\r\n')
        first = lines[0].split(' ', 2)
        headers = {}
        for line in lines[1:]:
            if ':' not in line:
                raise ValueError('Malformed HTTP header')
            k, v = line.split(':', 1)
            k, v = k.lower(), v.strip()
            if k in headers and k in ('content-length', 'transfer-encoding'):
                raise ValueError('Ambiguous HTTP framing headers')
            headers[k] = v
        if len(first) < 3:
            raise ValueError('Invalid HTTP start line')
        if response:
            if not first[0].startswith('HTTP/1.'):
                raise ValueError('Unsupported response protocol')
            status = int(first[1])
        elif not first[2].startswith('HTTP/1.') or first[0] not in (
                'GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS'):
            raise ValueError('Unsupported request protocol/method (including HEAD)')
        else:
            status = None
        pos = end + 4
        if 'transfer-encoding' in headers and 'content-length' in headers:
            raise ValueError('Ambiguous transfer-encoding plus content-length')
        if response and (100 <= status < 200 or status in (204, 304)):
            body = b''
        elif headers.get('transfer-encoding', '').lower() == 'chunked':
            body, pos = chunked_body(data, pos)
        elif 'transfer-encoding' in headers:
            raise ValueError('Unsupported transfer encoding')
        elif 'content-length' in headers:
            size = int(headers['content-length'])
            if size < 0 or size > MAX_STREAM or pos + size > len(data):
                raise ValueError('Incomplete/oversized HTTP body')
            body, pos = data[pos:pos + size], pos + size
        elif not response:
            body = b''
        else:
            raise ValueError('Close-delimited response is unsupported; not guessing boundaries')
        encoding = headers.get('content-encoding', 'identity').lower()
        if body and encoding == 'gzip':
            with gzip.GzipFile(fileobj=io.BytesIO(body)) as gz:
                body = gz.read(MAX_STREAM + 1)
            if len(body) > MAX_STREAM:
                raise ValueError('Decompressed HTTP body exceeds limit')
        elif body and encoding != 'identity':
            raise ValueError('Unsupported content encoding: ' + encoding)
        relevant = [e for e in evidence if e[0] < pos and e[1] > start]
        if not relevant:
            raise ValueError('No packet evidence for HTTP message')
        try:
            parsed = json.loads(body)
        except (ValueError, UnicodeError):
            parsed = None
        messages.append({'start_line': lines[0], 'status': status,
                         'headers': headers, 'json': parsed,
                         'body_text': body.decode('utf-8', errors='replace'),
                         'body_sha256': hashlib.sha256(body).hexdigest(),
                         'start_us': min(e[2] for e in relevant),
                         'end_us': max(e[2] for e in relevant),
                         'packet_ids': sorted({e[3] for e in relevant})})
    return messages


def reconstruct(path, ip_to_service):
    connections, current, issues = [], {}, []
    for number, stamp, raw in read_pcap(path):
        try:
            p = tcp_packet(raw)
        except ValueError as exc:
            issues.append({'packet': number, 'error': str(exc)})
            continue
        if p is None:
            continue
        if p['dst'] in ip_to_service and p['dport'] in (80, 8079):
            key = (p['src'], p['sport'], p['dst'], p['dport'])
            side = 'request'
        elif p['src'] in ip_to_service and p['sport'] in (80, 8079):
            key = (p['dst'], p['dport'], p['src'], p['sport'])
            side = 'response'
        else:
            continue
        p.update(packet=number, time_us=stamp)
        conn = current.get(key)
        if (conn is None or (side == 'request' and p['flags'] & 2 and
                conn.get('isn') is not None and conn['isn'] != p['seq'])):
            conn = {'key': key, 'request': [], 'response': [], 'isn': None,
                    'id': 'c%05d' % len(connections)}
            connections.append(conn)
            current[key] = conn
        if side == 'request' and p['flags'] & 2:
            conn['isn'] = p['seq']
        conn[side].append(p)
    transactions = []
    for conn in connections:
        if not any(p['data'] for side in ('request', 'response') for p in conn[side]):
            continue
        try:
            requests = http_messages(*reassemble(conn['request']))
            responses = http_messages(*reassemble(conn['response']), response=True)
            responses = [r for r in responses if not 100 <= r['status'] < 200]
            if len(requests) != len(responses):
                raise ValueError('Request/response count mismatch; FIFO pairing refused')
            for n, (req, res) in enumerate(zip(requests, responses)):
                method, target, _ = req['start_line'].split(' ', 2)
                if res['end_us'] < req['start_us']:
                    raise ValueError('Response precedes request')
                transactions.append({'id': conn['id'] + '-%03d' % n,
                    'client': ip_to_service.get(conn['key'][0], 'external-client'),
                    'server': ip_to_service[conn['key'][2]],
                    'connection': list(conn['key']), 'method': method, 'target': target,
                    'request': req, 'response': res})
        except (ValueError, OSError, EOFError) as exc:
            issues.append({'connection': conn['id'], 'endpoints': list(conn['key']), 'error': str(exc)})
    return transactions, issues


def leaves(value, path='$'):
    if isinstance(value, dict):
        for k, v in value.items():
            yield from leaves(v, path + '[' + json.dumps(k, ensure_ascii=False) + ']')
    elif isinstance(value, list):
        for i, v in enumerate(value):
            yield from leaves(v, path + '[%d]' % i)
    elif isinstance(value, str) and len(value) >= 3:
        yield path, value


def build_graph(transactions):
    nodes, edges, received = [], [], defaultdict(list)
    by_id = {t['id']: t for t in transactions}
    for t in transactions:
        for direction in ('request', 'response'):
            m = t[direction]
            sender, receiver = ((t['client'], t['server']) if direction == 'request'
                                else (t['server'], t['client']))
            for path, value in leaves(m['json']):
                digest = hashlib.sha256(value.encode()).hexdigest()
                pair = []
                for side, service in [('send', sender), ('receive', receiver)]:
                    node = {'id': 'f%07d' % len(nodes), 'transaction': t['id'],
                            'direction': direction, 'side': side, 'service': service,
                            'path': path, 'value': value, 'value_sha256': digest,
                            'start_us': m['start_us'], 'end_us': m['end_us']}
                    nodes.append(node); pair.append(node['id'])
                    if side == 'receive':
                        received[(service, digest)].append(node)
                edges.append({'source': pair[0], 'target': pair[1],
                              'kind': 'wire_transfer', 'evidence': m['packet_ids'],
                              'meaning': 'one observed wire message; not proof of application consumption'})
    for target in nodes:
        service = target['service']
        if target['side'] != 'send' or service == 'external-client':
            continue
        outgoing = by_id[target['transaction']]
        if target['direction'] == 'response':
            contexts = [outgoing]
        else:
            contexts = [t for t in transactions if t['server'] == service
                and t['request']['start_us'] <= target['start_us'] <= t['response']['end_us']]
        for source in received[(service, target['value_sha256'])]:
            if source['value'] != target['value'] or source['end_us'] > target['start_us']:
                continue
            compatible = []
            for context in contexts:
                if source['direction'] == 'request':
                    fits = source['transaction'] == context['id']
                else:
                    upstream = by_id[source['transaction']]
                    fits = (upstream['client'] == service and
                        context['request']['start_us'] <= upstream['request']['start_us'] and
                        source['end_us'] <= context['response']['end_us'])
                if fits:
                    compatible.append(context['id'])
            if compatible:
                edges.append({'source': source['id'], 'target': target['id'],
                              'kind': 'candidate_exact_value',
                              'contexts': compatible,
                              'meaning': 'equal content plus possible inbound request interval; NOT proven dependency'})
    return {'nodes': nodes, 'edges': edges,
            'scope': 'JSON string leaves length >= 3; exact matching only',
            'field_lineage_ground_truth': False,
            'trace_headers_used': False}


def query_graph(graph, transactions, queries):
    reverse = defaultdict(list)
    for e in graph['edges']:
        reverse[e['target']].append(e)
    by_id = {n['id']: n for n in graph['nodes']}
    results = []
    for query in queries:
        roots = [t['id'] for t in transactions if t['server'] == 'front-end'
                 and t['method'] == 'POST' and t['target'].split('?')[0] == '/orders'
                 and isinstance(t['response']['json'], dict)
                 and t['response']['json'].get('id') == query['order_id']]
        for field in ('card.longNum', 'card.ccv', 'address.street', 'customer.firstName'):
            path = '$' + ''.join('[' + json.dumps(k) + ']' for k in field.split('.'))
            sinks = [n['id'] for n in graph['nodes'] if n['transaction'] in roots
                     and n['direction'] == 'response' and n['side'] == 'send' and n['path'] == path]
            visited, stack, selected = set(sinks), list(sinks), []
            while stack:
                for edge in reverse[stack.pop()]:
                    selected.append(edge)
                    if edge['source'] not in visited:
                        visited.add(edge['source']); stack.append(edge['source'])
            # Report a subgraph rather than choosing one arbitrary same-valued path.
            results.append({'order_id': query['order_id'], 'field': field,
                'status': 'candidate_subgraph' if sinks else 'sink_not_observed',
                'sink_nodes': sinks, 'nodes': [by_id[n] for n in sorted(visited)],
                'edges': selected, 'unique_origin_proven': False})
    return results


def analyze(capture, services, output, queries=()):
    output.mkdir(parents=True, exist_ok=True)
    transactions, issues = reconstruct(capture, services)
    save(output / 'transactions.json', transactions)
    graph = build_graph(transactions)
    save(output / 'field-graph.json', graph)
    query_results = query_graph(graph, transactions, queries)
    save(output / 'queries.json', query_results)
    summary = {'transactions': len(transactions), 'reconstruction_issues': issues,
        'wire_edges': sum(e['kind'] == 'wire_transfer' for e in graph['edges']),
        'candidate_edges': sum(e['kind'] == 'candidate_exact_value' for e in graph['edges']),
        'queries': len(query_results),
        'sinks_observed': sum(bool(q['sink_nodes']) for q in query_results),
        'field_lineage_accuracy': None,
        'status': 'needs_review' if issues else 'parsed',
        'limits': ['No runtime assignment/taint evidence', 'No transformation matching',
                   'Concurrent inbound requests can create multiple candidate contexts',
                   'No database or RabbitMQ body capture', 'No trace-header dependency',
                   'Capture gaps may be invisible if an entire connection is missing']}
    save(output / 'summary.json', summary)
    return summary


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('capture', type=Path)
    p.add_argument('--services', type=Path, required=True)
    p.add_argument('--queries', type=Path)
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args()
    queries = json.loads(args.queries.read_text()) if args.queries else []
    report = analyze(args.capture, json.loads(args.services.read_text())['ip_to_service'], args.out, queries)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return int(report['status'] != 'parsed')


if __name__ == '__main__':
    raise SystemExit(main())
