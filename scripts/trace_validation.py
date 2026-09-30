"""Validate observed call graphs, without filling gaps with expected edges."""
import re
from urllib.parse import urlsplit

EXPECTED_EDGES = {('test-client', 'front-end'), ('front-end', 'user'),
                  ('front-end', 'orders'), ('orders', 'user'), ('orders', 'carts'),
                  ('orders', 'payment'), ('orders', 'shipping'), ('shipping', 'queue-master')}
HTTP_SERVICES = {'front-end', 'orders', 'user', 'carts', 'payment', 'shipping'}


def service(span):
    return span.get('localEndpoint', {}).get('serviceName', '')


def target(span):
    tags = span.get('tags', {})
    return urlsplit(tags.get('http.url', tags.get('url.full', tags.get('http.target', '')))).path


def select_http_scope(spans, trace_id, root_id):
    """Keep HTTP operations and their ancestors up to the client root.

    Message boundaries prune asynchronous descendants; unknown/missing parents
    remain visible to the structural validator rather than being repaired.
    """
    index = {s['id']: s for s in spans if s.get('traceId') == trace_id}
    keep = {root_id}
    for ident, s in index.items():
        tags = s.get('tags', {})
        if service(s) not in HTTP_SERVICES or s.get('kind') not in ('CLIENT', 'SERVER'):
            continue
        if not tags.get('http.method', tags.get('http.request.method')):
            continue
        trail, cursor, asynchronous = set(), ident, False
        while cursor in index and cursor not in trail:
            ancestor = index[cursor]
            if ancestor.get('kind') in ('PRODUCER', 'CONSUMER') or service(ancestor) == 'queue-master':
                asynchronous = True
                break
            trail.add(cursor)
            if cursor == root_id:
                break
            cursor = ancestor.get('parentId')
        if not asynchronous:
            keep.update(trail)
    return [s for s in spans if s.get('traceId') == trace_id and s.get('id') in keep]


def validate_trace(spans, request, forbidden_ids=(), scope='full'):
    if scope not in ('full', 'synchronous-http'):
        raise ValueError('Unknown evaluation scope')
    trace_id, root_id = request['trace_id'], request['span_id']
    selected = [s for s in spans if s.get('traceId') == trace_id]
    if scope == 'synchronous-http':
        selected = select_http_scope(spans, trace_id, root_id)
    errors, runtime_errors, index = [], [], {}
    for s in selected:
        ident = s.get('id', '')
        if not re.fullmatch('[0-9a-f]{16}', ident) or not int(ident, 16):
            errors.append('invalid span ID: ' + str(ident)); continue
        if ident in index and index[ident] != s:
            errors.append('conflicting duplicate span: ' + ident)
        index[ident] = s
        if not service(s):
            errors.append('missing service: ' + ident)
        if not isinstance(s.get('duration'), (int, float)) or s['duration'] < 0:
            errors.append('missing/invalid duration: ' + ident)
        tags = s.get('tags', {})
        reasons = []
        # Zipkin represents an error with an empty-valued tag as well.
        if 'error' in tags or tags.get('otel.status_code') == 'ERROR':
            reasons.append('error span')
        code = tags.get('http.status_code', tags.get('http.response.status_code', '200'))
        try:
            if int(code) >= 400:
                reasons.append('HTTP status ' + str(code))
        except (ValueError, TypeError):
            errors.append('invalid HTTP status: ' + ident)
        if reasons:
            runtime_errors.append({'span_id': ident, 'service': service(s),
                                   'name': s.get('name'), 'kind': s.get('kind'),
                                   'url': tags.get('http.url', tags.get('url.full')),
                                   'reasons': reasons})
        if any(other in target(s) for other in forbidden_ids):
            errors.append('other fixture ID inside this trace: ' + ident)
    root = index.get(root_id)
    if not root or root.get('parentId') or service(root) != 'test-client':
        errors.append('missing/invalid test-client root')
    edges = set()
    for ident, s in index.items():
        parent = s.get('parentId')
        if ident != root_id and not parent:
            errors.append('unexpected root: ' + ident)
        if parent and parent not in index:
            errors.append('missing parent: ' + ident + ' -> ' + parent)
        elif parent and service(index[parent]) != service(s):
            edges.add((service(index[parent]), service(s)))
        seen, cursor = set(), ident
        while cursor in index:
            if cursor in seen:
                errors.append('cycle: ' + ident); break
            seen.add(cursor)
            cursor = index[cursor].get('parentId')
    expected_edges = EXPECTED_EDGES - ({('shipping', 'queue-master')} if scope == 'synchronous-http' else set())
    missing = expected_edges - edges
    if missing:
        errors.append('missing service edges: ' + repr(sorted(missing)))
    # These endpoints distinguish independent user reads in the fan-out.
    required = {'front-end': {'/orders'}, 'orders': {'/orders'},
                'user': {'/customers/' + request['customer_id'],
                         '/addresses/' + request['address_id'], '/cards/' + request['card_id']},
                'carts': {'/carts/' + request['customer_id'] + '/items'}}
    for name, paths in required.items():
        actual = {target(s) for s in index.values() if service(s) == name and s.get('kind') == 'SERVER'}
        if paths - actual:
            errors.append('missing server endpoints for %s: %s' % (name, sorted(paths - actual)))
    consumers = [s for s in index.values() if service(s) == 'queue-master' and s.get('kind') == 'CONSUMER']
    producers = {s['id'] for s in index.values() if service(s) == 'shipping' and s.get('kind') == 'PRODUCER'}
    linked = False
    for consumer in consumers:
        cursor, seen = consumer.get('parentId'), set()
        while cursor in index and cursor not in seen:
            if cursor in producers:
                linked = True
            seen.add(cursor)
            cursor = index[cursor].get('parentId')
    if not linked and scope == 'full':
        errors.append('no queue consumer linked to a shipping producer')
    return {'trace_id': trace_id, 'status': 'passed' if not errors else 'incomplete',
            'execution_status': 'failed' if runtime_errors else 'no_recorded_errors',
            'runtime_errors': list({e['span_id']: e for e in runtime_errors}.values()),
            'span_count': len(index), 'errors': sorted(set(errors)),
            'service_edges': [list(e) for e in sorted(edges)],
            'span_edges': [{'parent': s['parentId'], 'child': s['id']} for s in index.values()
                           if s.get('parentId')],
            'spans': list(index.values())}


def validate_all(spans, requests, scope='full'):
    reports = []
    for request in requests:
        others = [r[k] for r in requests if r['trace_id'] != request['trace_id']
                  for k in ('customer_id', 'address_id', 'card_id')]
        reports.append(validate_trace(spans, request, others, scope=scope))
    unique = len({r['trace_id'] for r in requests}) == len(requests)
    passed = bool(reports) and unique and all(r['status'] == 'passed' for r in reports)
    intervals = []
    for request in requests:
        roots = [s for s in spans if s.get('traceId') == request['trace_id']
                 and s.get('id') == request['span_id']]
        if roots:
            s = roots[0]
            intervals.append((s.get('timestamp', 0), s.get('timestamp', 0) + s.get('duration', 0)))
    overlaps = sum(max(a[0], b[0]) < min(a[1], b[1])
                   for i, a in enumerate(intervals) for b in intervals[i + 1:])
    return {'status': 'passed' if passed else 'incomplete', 'unique_order_trace_ids': unique,
            'execution_status': ('failed' if any(r['runtime_errors'] for r in reports)
                                 else 'no_recorded_errors' if reports else 'unknown'),
            'overlapping_order_interval_pairs': overlaps,
            'scope': scope,
            'interpretation': 'collection consistency and expected-path coverage checks; not a proof of exhaustive instrumentation',
            'orders': reports}


def main():
    """Recheck an existing ZIP without changing its contents or rerunning Docker."""
    import argparse
    import json
    import zipfile
    parser = argparse.ArgumentParser(description=main.__doc__)
    parser.add_argument('bundle')
    parser.add_argument('--scope', choices=['full', 'synchronous-http'], default='full')
    args = parser.parse_args()
    with zipfile.ZipFile(args.bundle) as archive:
        requests = json.loads(archive.read('oracle/orders.json'))
        name = ('oracle/spans-final.json' if 'oracle/spans-final.json' in archive.namelist()
                else 'oracle/spans.json')
        report = validate_all(json.loads(archive.read(name)), requests, scope=args.scope)
    summary = {k: v for k, v in report.items() if k != 'orders'}
    summary['orders'] = [{k: v for k, v in r.items() if k not in ('spans', 'span_edges')}
                         for r in report['orders']]
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if report['status'] == 'passed' and report['execution_status'] == 'no_recorded_errors' else 1


if __name__ == '__main__':
    raise SystemExit(main())
