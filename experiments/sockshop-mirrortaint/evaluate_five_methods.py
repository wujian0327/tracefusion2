#!/usr/bin/env python3
"""Normalize independently produced claims and evaluate frozen field queries.

No normalized answers enter either tracking engine. Missing/unknown answers count
as missed relations and failed exact queries, and remain in the denominator.
"""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import re
import resource
import statistics
import time
from urllib.parse import urlsplit
from five_methods import METHODS
from infer_boundary_sources import infer as infer_boundary
from infer_service_sources import infer as infer_orders
from service_model import derive


def rows(file):
    return [json.loads(l) for l in file.read_bytes().splitlines() if l.strip()]


def orders_claims(run, mode):
    claims, coords, requests = {}, {}, {}
    if mode == 'tracefusion':
        capture = run / 'tracefusion-events'
        model, _ = derive(capture)
        inferred = infer_orders(capture, model)
        (run / 'service-model.json').write_text(json.dumps(model, indent=2) + '\n')
        (run / 'inference.json').write_text(json.dumps(inferred, indent=2) + '\n')
        events = rows(capture / 'events.jsonl')
        entries = {r['frame']: r for r in events if r['kind'] == 'enter'}
        requests = {r['rpc']: r for r in events if r['kind'] == 'rpc-enter'}
        responses = [r for r in events if r['kind'] == 'rpc-exit']
        for r in responses:
            request = requests[r['rpc']]
            url = urlsplit(request['uri'])
            fields = {f['path']: f['observed'].get('value') for f in r['fields']}
            for f in r['fields']:
                path = f['path']
                match = re.fullmatch(r'result#body\[(\d+)\]#([^#]+)', path)
                if match:
                    record = fields.get('result#body[' + match[1] + ']#id'); field = match[2]
                elif path.startswith('result#body#content#') and '#' not in path.removeprefix('result#body#content#'):
                    field = path.removeprefix('result#body#content#')
                    record = fields.get('result#body#content#id')
                    if record is None:
                        links = [v for k,v in fields.items() if k.endswith('#href') and k.startswith('result#body#links[')]
                        if request['uri'] not in links:
                            continue
                        record = url.path.rsplit('/', 1)[-1]
                else:
                    continue
                coords[(r['rpc'], path)] = (request['trace_id'], url.hostname, url.path, record, field)
        for target in inferred['answers']:
            entry = entries[target['root_frame']]
            claims[entry['trace_id']] = {f['path']: {'value': f['observed'].get('value'),
                'known': f['status'] == 'resolved',
                'sources': {coords.get(tuple(c), ('unknown-coordinate', *c)) for c in f['sources']}}
                for f in target['fields']}
    else:
        events = rows(next(run.glob('agent-logs/orders/**/adapted-events.jsonl')))
        by_id = {r['event_id']: r for r in events}
        if len(by_id) != len(events):
            raise ValueError('Duplicate MirrorTaint event')
        token_index = defaultdict(set)
        for response in events:
            if response['phase'] != 'rpc-response':
                continue
            request = by_id[response['rpc_request_event']]
            if any(response[k] != request[k] for k in ('trace_id', 'span_id', 'thread_id', 'method')):
                raise ValueError('RPC context mismatch')
            url = urlsplit(request['fields']['arg1#url']['value'])
            for path, field in response['fields'].items():
                match = re.fullmatch(r'result#body\[(\d+)\]#([^#]+)', path)
                if match:
                    record = response['fields'].get('result#body[' + match[1] + ']#id', {}).get('value'); name = match[2]
                elif path.startswith('result#body#content#') and '#' not in path.removeprefix('result#body#content#'):
                    name = path.removeprefix('result#body#content#')
                    record = response['fields'].get('result#body#content#id', {}).get('value')
                    if record is None:
                        links = [v.get('value') for k,v in response['fields'].items() if k.endswith('#href') and k.startswith('result#body#links[')]
                        if url.geturl() not in links:
                            continue
                        record = url.path.rsplit('/', 1)[-1]
                else:
                    continue
                coordinate = (request['trace_id'], url.hostname, url.path, record, name)
                for tag in (field.get('tag') or {}).get('A', []):
                    token_index[tag['A']].add(coordinate)
        for target in events:
            if target['phase'] != 'sink' or target['method'] != 'newOrder':
                continue
            trace = target['trace_id']
            if trace in claims:
                raise ValueError('Duplicate target trace')
            claims[trace] = {}
            for path, field in target['fields'].items():
                actual = set()
                for tag in (field.get('tag') or {}).get('A', []):
                    token = tag['A']
                    decoded = token_index.get(token, set())
                    actual.update(decoded if len(decoded) == 1 else {('unknown-token', token)})
                claims[trace][path] = {'value': field.get('value'), 'sources': actual,
                    'known': target['capture_complete'] and target['available'] and field.get('tag') is not None}
    return claims


def boundary_claims(run, service, mode):
    capture = run / 'boundary-events' / service
    events = rows(capture / 'events.jsonl')
    if any(r['kind'] == 'problem' for r in events):
        raise ValueError('Boundary collection error')
    entries = {r['frame']: r for r in events if r['kind'] == 'enter'}
    roots = {}
    for r in entries.values():
        roots[r['frame']] = roots[r['parent']] if r['parent'] else r['frame']
    coords, token_index = {}, defaultdict(set)
    for r in events:
        if r['kind'] != 'source':
            continue
        trace = entries[roots[r['frame']]]['trace_id']
        for f in r['fields']:
            coord = (trace, f['record_id'], f['field'])
            coords[(r['instance'], f['path'])] = coord
            if 'token' in f:
                token_index[f['token']].add(coord)
            # The native facade tagger may retain its existing source tag instead
            # of replacing it with the custom boundary token. Decode that exact
            # observed source token, never its value or timestamp components.
            native_prefix = 'works.weave.socks.shipping.controllers.ShippingController#postShipping#arg1#' + f['field'] + ':'
            for token in f.get('tags', []):
                if service == 'shipping' and token.startswith(native_prefix):
                    token_index[token].add(coord)
    if mode == 'tracefusion':
        inferred = infer_boundary(capture)
        (run / ('boundary-inference-' + service + '.json')).write_text(json.dumps(inferred, indent=2) + '\n')
        targets = inferred['answers']
    else:
        completed = {r['frame'] for r in events if r['kind'] == 'exit'}
        targets = [dict(r, root=roots[r['frame']], trace_id=entries[roots[r['frame']]]['trace_id'],
                        sink=r.get('boundary', 'return'))
                   for r in events if r['kind'] in ('exit', 'sink') and roots[r['frame']] in completed and r.get('fields')]
    claims = defaultdict(list)
    for target in targets:
        fields = {}
        for f in target['fields']:
            if f['observed'].get('value') is None:
                continue
            if mode == 'tracefusion':
                actual = {coords.get(tuple(c), ('unknown-coordinate', *c)) for c in f.get('sources') or []}
                known = f['status'] == 'resolved'
            else:
                # Only the explicitly configured field-source profile participates.
                # Preserve unknown tokens in that profile as false-positive claims.
                actual = set()
                for t in f.get('tags', []):
                    if t.startswith('tf2boundary:') or t.startswith('works.weave.socks.shipping.controllers.ShippingController#postShipping#arg1#'):
                        decoded = token_index.get(t, set())
                        actual.update(decoded if len(decoded) == 1 else {('unknown-token',t)})
                known = bool(actual)
            key = (f['record_id'], f['field'])
            if key in fields:
                raise ValueError('Ambiguous target field identity')
            fields[key] = {'value': f['observed']['value'], 'sources': actual, 'known': known}
        claims[target['trace_id']].append({'sink': target['sink'], 'fields': fields,
                                         'seq': target['seq'], 'frame': target['frame'], 'root': target['root']})
    return claims


def score(actual, expected, value_ok=True):
    sources = actual['sources'] if actual else set()
    tp, fp, fn = len(sources & expected), len(sources - expected), len(expected - sources)
    exact = bool(actual and actual['known'] and value_ok and sources == expected)
    return {'tp': tp, 'fp': fp, 'fn': fn, 'exact': exact,
            'unknown': not actual or not actual['known'],
            'expected': sorted(expected), 'actual': sorted(sources)}


def summarize(queries):
    tp = sum(q['tp'] for q in queries); fp = sum(q['fp'] for q in queries); fn = sum(q['fn'] for q in queries)
    return {'queries': len(queries), 'exact': sum(q['exact'] for q in queries),
            'exact_rate': sum(q['exact'] for q in queries) / len(queries) if queries else None,
            'tp': tp, 'fp': fp, 'fn': fn, 'unknown': sum(q['unknown'] for q in queries),
            'precision': tp / (tp + fp) if tp + fp else None,
            'recall': tp / (tp + fn) if tp + fn else None}


def costs(run, business):
    measured = [b for b in business if b['phase'] == 'measurement']
    data = {}
    for method, prefix in METHODS.items():
        service = 'orders' if method == 'newOrder' else 'shipping' if method == 'postShipping' else 'carts'
        events = rows(run / 'cost-events' / service / 'events.jsonl')
        if [r['seq'] for r in events] != list(range(1,len(events)+1)) or any(r['kind']=='problem' for r in events):
            raise ValueError('Cost collection failure or sequence gap')
        samples = []
        for case in [b for b in measured if b['method'] == method]:
            found = [r for r in events if r['kind'] == 'exit' and r['parent'] == 0
                     and r['method'].startswith(prefix + '(') and r['trace_id'] == case['trace_id']]
            if len(found) != 1:
                raise ValueError('Missing/duplicate cost sample: ' + case['case'])
            r = found[0]
            if r['process_allocated_bytes'] < 0 or r['thread_allocated_bytes'] < 0:
                raise ValueError('Invalid allocation counter delta')
            samples.append(dict(r, case=case['case'], http_runtime_ns=case.get('http_runtime_ns', case.get('end_monotonic_ns', 0)-case.get('start_monotonic_ns', 0))))
        def stats(key, scale):
            values = sorted(r[key] / scale for r in samples)
            return {'mean': statistics.mean(values), 'median': statistics.median(values),
                    'p95': values[max(0, int(len(values) * .95 + .999999) - 1)],
                    'min': min(values), 'max': max(values)}
        data[method] = {'n': len(samples), 'controller_ms': stats('runtime_ns', 1e6),
                        'http_ms': stats('http_runtime_ns', 1e6),
                        'allocated_kB': stats('process_allocated_bytes', 1024),
                        'thread_allocated_kB': stats('thread_allocated_bytes', 1024),
                        'resident_kB': stats('rss_kb', 1), 'samples': samples}
    return data


def evaluate(run):
    result = json.loads((run / 'result.json').read_text())
    if result['status'] != 'business-passed' or result['frontend_errors']:
        raise ValueError('Requires complete clean business run')
    business, mode = result['cases'], result['mode']
    protocol = json.loads((run/'protocol.json').read_text())
    manifest = json.loads((run/'cases.json').read_text())
    expected = {c['id']:('newOrder','accuracy') for c in manifest['cases']}
    expected.update({'parallel-'+str(i):('newOrder','accuracy') for i in range(manifest['concurrent']['count'])})
    for method in ('get','delete','mergeCarts','postShipping'):
        variants = ('single','multi','empty') if method!='postShipping' else ('single','same-value')
        expected.update({method+'-'+v:(method,'accuracy') for v in variants})
    for phase,count in [('warmup',protocol['warmup']),('measurement',protocol['repetitions'])]:
        expected.update({phase+'-'+method+'-'+str(i):(method,phase) for i in range(count) for method in METHODS})
    if len(business)!=len(expected) or {b['case'] for b in business}!=set(expected):
        raise ValueError('Missing/duplicate/extra workload case')
    if any((b['method'],b['phase'])!=expected[b['case']] or not b['business_passed'] for b in business):
        raise ValueError('Incorrect workload identity/phase or failed business case')
    if len({b['trace_id'] for b in business})!=len(business):
        raise ValueError('Duplicate workload invocation trace')
    report = {'mode': mode, 'run': str(run.resolve()), 'configuration': result['configuration'],
              'cost': costs(run, business), 'accuracy_eligible': False,
              'performance_eligible': False, 'paper_numeric_reproduction': False,
              'qualification': 'single deployment per configuration; fixed source-boundary calibration; independent review and DB wire/source-image qualification pending'}
    if mode == 'plain':
        return report
    begin = time.perf_counter_ns()
    order = orders_claims(run, mode)
    cart = boundary_claims(run, 'carts', mode); shipping = boundary_claims(run, 'shipping', mode)
    report['offline_evaluation_and_reconstruction_ms'] = (time.perf_counter_ns() - begin) / 1e6
    queries, negatives = defaultdict(list), []
    for case in [b for b in business if b['phase'] == 'accuracy']:
        contract = json.loads((run / case['case'] / 'query-contract.json').read_text())
        method = case['method']; trace = case['trace_id']
        if method == 'newOrder':
            fields = order.get(trace)
            if not contract['expected_target']:
                negatives.append({'case': case['case'], 'checks': len(contract['queries']), 'passed': fields is None}); continue
            for q in contract['queries']:
                target = 'arg#' + q['target'].replace('.', '#')
                match = re.fullmatch(r'items\[itemId=(.*)\]\.(.*)', q['target'])
                if match:
                    indices = [m[1] for p,f in (fields or {}).items() if (m:=re.fullmatch(r'arg#items\[(\d+)\]#itemId',p)) and f['value']==match[1]]
                    target = 'arg#items[' + indices[0] + ']#' + match[2] if len(indices)==1 else '<missing-item>'
                expected = {(trace, s['service'], s['route'], s['record_id'], s['field']) for s in q['sources']}
                queries[method].append(dict(score((fields or {}).get(target), expected), case=case['case'], target=q['target']))
        else:
            targets = (shipping if method == 'postShipping' else cart).get(trace, [])
            sink = contract['sink']
            if sink == 'return':
                targets = [t for t in targets if t['sink']=='return' and t['frame']==t['root']]
            elif sink == 'delete':
                targets = [t for t in targets if '.delete(' in t['sink']]
            else:
                targets = [t for t in targets if '.save(' in t['sink']]
                targets = sorted(targets, key=lambda t:t['seq'])[-1:]
            if sink == 'no-save':
                negatives.append({'case':case['case'], 'checks':1, 'passed':not targets}); continue
            target = targets[0] if len(targets)==1 else None
            for q in contract['queries']:
                actual = target['fields'].get((q['record_id'],q['field'])) if target else None
                expected = {(trace,q['record_id'],q['field'])}
                value_ok = bool(actual and actual['value']==q['value'])
                queries[method].append(dict(score(actual,expected,value_ok),case=case['case'],target=q))
    report.update(accuracy={m:summarize(q) for m,q in queries.items()}, queries=dict(queries),
                  no_target=negatives, all_no_target_passed=all(n['passed'] for n in negatives),
                  offline_process_peak_rss_kB=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    report['observation_hashes'] = {str(p.relative_to(run)):hashlib.sha256(p.read_bytes()).hexdigest()
        for parent in ('tracefusion-events','boundary-events','cost-events') for p in (run/parent).glob('**/events.jsonl')}
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run', type=Path, required=True); p.add_argument('--out',type=Path,required=True)
    args = p.parse_args(); report = evaluate(args.run)
    args.out.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ('cost','queries')},indent=2))
