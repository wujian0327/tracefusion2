#!/usr/bin/env python3
"""Export a blinded HTTP observation view and a separate span-based oracle.

The views share instrumentation: this is NOT an independent packet capture.
Only the exporter/scorer may access oracle identifiers. Never group algorithm
observations by trace, successful fixture, or known request membership.
"""
import argparse
import json
from pathlib import Path
import secrets
from urllib.parse import urlsplit
import zipfile

from sockshop import save
from trace_validation import select_http_scope, validate_all

SERVICES = {'front-end', 'orders', 'user', 'carts', 'payment', 'shipping'}
OBS_KEYS = {'event_id', 'service', 'kind', 'method', 'path', 'peer_service',
            'start_us', 'duration_us', 'status_code'}
SCOPE = 'synchronous HTTP order calls; queue consumers, messaging and database spans excluded'


def project(span):
    """Whitelist projection: does not read trace ID, span ID or parent ID."""
    service = span.get('localEndpoint', {}).get('serviceName')
    kind, tags = span.get('kind'), span.get('tags', {})
    method = tags.get('http.method', tags.get('http.request.method'))
    if service not in SERVICES or kind not in ('CLIENT', 'SERVER') or not method:
        return None
    address = tags.get('http.url', tags.get('url.full', tags.get('http.target', '')))
    parsed = urlsplit(address)
    if parsed.scheme and parsed.scheme not in ('http', 'https'):
        return None
    if not parsed.path.startswith('/'):
        raise ValueError('HTTP observation has no concrete request path')
    start, duration = span.get('timestamp'), span.get('duration')
    if not isinstance(start, (int, float)) or not isinstance(duration, (int, float)) or duration < 0:
        raise ValueError('HTTP observation has invalid timing')
    status = tags.get('http.status_code', tags.get('http.response.status_code'))
    peer = parsed.hostname if kind == 'CLIENT' else None
    # DNS service names are directly observable; do not use trace edges to fill them.
    return {'service': service, 'kind': kind, 'method': method.upper(),
            'path': parsed.path, 'peer_service': peer,
            'start_us': int(start), 'duration_us': int(duration),
            'status_code': int(status) if status is not None else None}


def read_bundle(source):
    source = Path(source)
    if source.is_dir():
        name = 'spans-final.json' if (source / 'oracle/spans-final.json').exists() else 'spans.json'
        return json.loads((source / 'oracle' / name).read_text()), json.loads((source / 'oracle/orders.json').read_text())
    with zipfile.ZipFile(source) as archive:
        name = 'oracle/spans-final.json' if 'oracle/spans-final.json' in archive.namelist() else 'oracle/spans.json'
        return json.loads(archive.read(name)), json.loads(archive.read('oracle/orders.json'))


def build(spans, orders):
    validation = validate_all(spans, orders, scope='synchronous-http')
    if validation['status'] != 'passed':
        raise ValueError('HTTP oracle failed structure/coverage validation: ' +
                         repr([r['errors'] for r in validation['orders']]))
    index = {}
    for span in spans:
        key = (span['traceId'], span['id'])
        if key in index and index[key] != span:
            raise ValueError('Conflicting duplicate span: ' + repr(key))
        index[key] = span
    observations, ids, bindings = [], {}, []
    for key, span in index.items():
        observation = project(span)
        if observation is None:
            continue
        event_id = secrets.token_hex(16)
        ids[key] = event_id
        observation['event_id'] = event_id
        observations.append(observation)
        bindings.append({'event_id': event_id, 'trace_id': key[0], 'span_id': key[1]})
    obs_index = {o['event_id']: o for o in observations}
    # Queries are chosen using observable entrypoint metadata, never oracle membership.
    queries = [{'query_id': secrets.token_hex(16), 'root_event_id': o['event_id']}
               for o in observations if (o['service'], o['kind'], o['method'], o['path']) ==
               ('front-end', 'SERVER', 'POST', '/orders')]
    if not queries:
        raise ValueError('No observable POST /orders query')
    reverse = {v: k for k, v in ids.items()}
    order_traces = {o['trace_id']: o for o in orders}
    if len(order_traces) != len(orders) or len(queries) != len(orders):
        raise ValueError('Oracle manifest does not cover exactly the observed order queries')
    reference_queries = []
    for query in queries:
        root_key = reverse[query['root_event_id']]
        if root_key[0] not in order_traces:
            raise ValueError('Missing order oracle for observed query')
        order = order_traces[root_key[0]]
        root_parent = index[root_key].get('parentId')
        if root_parent != order['span_id']:
            raise ValueError('Order entry span does not reference the actual test-client span')
        client_root = index.get((root_key[0], order['span_id']))
        if not client_root or client_root.get('localEndpoint', {}).get('serviceName') != 'test-client':
            raise ValueError('Missing test-client root oracle')
        selected = {(s['traceId'], s['id']) for s in
                    select_http_scope(spans, root_key[0], order['span_id'])}
        nodes = {key: value for key, value in ids.items() if key in selected}
        edges = []
        for key, event_id in nodes.items():
            if key == root_key:
                continue
            cursor, seen = index[key].get('parentId'), {key[1]}
            while cursor:
                if cursor in seen:
                    raise ValueError('Cycle in order oracle')
                seen.add(cursor)
                parent_key = (key[0], cursor)
                parent = index.get(parent_key)
                if parent is None:
                    raise ValueError('Missing parent in order oracle')
                if parent_key in nodes:
                    a, b = obs_index[nodes[parent_key]], obs_index[event_id]
                    if a['kind'] == 'SERVER' and b['kind'] == 'CLIENT' and a['service'] == b['service']:
                        relation = 'local'
                    elif a['kind'] == 'CLIENT' and b['kind'] == 'SERVER':
                        relation = 'transport'
                        if a['peer_service'] != b['service'] or (a['method'], a['path']) != (b['method'], b['path']):
                            raise ValueError('Oracle transport endpoints disagree with observations')
                    else:
                        raise ValueError('Unexpected HTTP parent relation in oracle')
                    edges.append({'parent': nodes[parent_key], 'child': event_id, 'relation': relation})
                    break
                cursor = parent.get('parentId')
            else:
                raise ValueError('HTTP node is disconnected from order root')
        reachable = {query['root_event_id']}
        while True:
            added = {e['child'] for e in edges if e['parent'] in reachable} - reachable
            if not added:
                break
            reachable.update(added)
        if reachable != set(nodes.values()) or len(edges) != len(nodes) - 1:
            raise ValueError('Order HTTP oracle is not a rooted tree')
        reference_queries.append(dict(query, nodes=sorted(reachable), edges=sorted(edges, key=lambda e: e['child'])))
    # Random opaque IDs and ID ordering remove exporter batch / per-trace grouping.
    observations.sort(key=lambda o: o['event_id'])
    queries.sort(key=lambda q: q['query_id'])
    public_text = json.dumps([observations, queries])
    private_ids = {part for key in index for part in key}
    if any(ident and ident in public_text for ident in private_ids):
        raise ValueError('Instrumentation identifier leaked into public view')
    if any(set(o) != OBS_KEYS for o in observations):
        raise ValueError('Observation schema drift')
    return observations, queries, {'schema_version': 1, 'scope': SCOPE,
        'queries': reference_queries, 'private_bindings': bindings,
        'source_validation': validation,
        'observed_event_ids': sorted(obs_index)}


def export_dataset(source, destination):
    observations, queries, reference = build(*read_bundle(source))
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    (destination / 'algorithm-input').mkdir()
    (destination / 'oracle').mkdir()
    save(destination / 'algorithm-input/observations.json', observations)
    save(destination / 'algorithm-input/queries.json', queries)
    save(destination / 'oracle/reference.json', reference)
    manifest = {'schema_version': 1, 'scope': SCOPE, 'observations': len(observations),
                'queries': len(queries), 'reference_http_nodes': [len(q['nodes']) for q in reference['queries']],
                'reference_http_edges': [len(q['edges']) for q in reference['queries']],
                'source': 'whitelist projection of instrumented HTTP span measurements; not independent packet capture',
                'background': 'all observed in-scope HTTP calls, including setup and health checks',
                'excluded_from_input': ['trace/span/parent IDs', 'thread IDs', 'batches', 'headers',
                                        'bodies', 'query strings', 'fixtures', 'logs', 'oracle membership'],
                'business_ids_in_paths': True, 'clock_assumption': 'shared-host clocks; configurable timing tolerance'}
    save(destination / 'manifest.json', manifest)
    return manifest


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('source', type=Path, help='result ZIP or unpacked run directory')
    p.add_argument('--out', type=Path, required=True, help='new dataset directory')
    a = p.parse_args()
    print(json.dumps(export_dataset(a.source, a.out), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
