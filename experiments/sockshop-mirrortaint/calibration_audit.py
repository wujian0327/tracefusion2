#!/usr/bin/env python3
"""Audit fixed public-agent output coverage; never infer missing provenance or score accuracy."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re


def audit(run):
    result = json.loads((run / 'result.json').read_text())
    if result['mode'] != 'mirrortaint' or result['status'] != 'business-preflight-passed':
        raise ValueError('Requires a completed MirrorTaint business preflight')
    services = {}
    records_by_service = {}
    hashes = {}
    for name in ('orders', 'carts', 'shipping'):
        base = run / 'agent-logs' / name / 'AgentLogs/ShadowTaint/tf2-preflight'
        log = base / 'sink.log'
        records = [json.loads(line) for line in log.read_text().splitlines() if line.strip()]
        records_by_service[name] = records
        paths = sorted((base / 'sink').rglob('*.log'))
        timestamps = Counter((r['F'], r['E'], r['B'], r['D']) for r in records)
        services[name] = {
            'json_records': len(records),
            'json_fields': sum(len(r['A']) for r in records),
            'json_fields_with_sources': sum(bool(v['A']) for r in records for v in r['A'].values()),
            'text_files': len(paths),
            'collisions': [dict(group=k[0], timestamp=k[1], owner=k[2], method=k[3], records=n)
                           for k, n in timestamps.items() if n > 1],
        }
        for f in [log, base / 'runtime-info.log', *paths]:
            hashes[str(f.relative_to(run))] = hashlib.sha256(f.read_bytes()).hexdigest()

    # Match target records only by unique fixture/customer record IDs, never by content values or time.
    customer_cases = {}
    cases = []
    for business in result['cases']:
        folder = run / business['case']
        contract = json.loads((folder / 'query-contract.json').read_text())
        fixture = json.loads((folder / 'fixture.json').read_text())
        cid = fixture['customer_id']
        if cid in customer_cases:
            raise ValueError('Fixture customer identity is not unique')
        customer_cases[cid] = contract['case']
        case = {'case': contract['case'], 'customer_id': cid,
                'expected_target': contract['expected_target'], 'queries': []}
        if contract['expected_target']:
            for query in contract['queries']:
                target = query['target']
                if target == 'total':
                    field = 'arg#total'
                elif target.startswith('items['):
                    match = re.fullmatch(r'items\[itemId=(.*)\]\.(.*)', target)
                    # Index is resolved by item identity in the actual target response.
                    response = json.loads((folder / 'order-response.json').read_text())
                    index = next(i for i, item in enumerate(response['items']) if item['itemId'] == match[1])
                    field = f'arg#items[{index}]#{match[2]}'
                else:
                    field = 'arg#' + target.replace('.', '#')
                case['queries'].append({'target': target, 'agent_field': field,
                                        'expected_source_count': len(query['sources']),
                                        'text_status': 'missing', 'json_status': 'missing'})
        cases.append(case)

    def identify(fields):
        ids = [f.split(':', 1)[1] for f in fields if f.startswith('arg#customerId:')]
        if len(ids) != 1 or ids[0] not in customer_cases:
            raise ValueError('Cannot associate agent target record with a unique fixture identity')
        return customer_cases[ids[0]]

    case_map = {c['case']: c for c in cases}
    json_cases = []
    for record in records_by_service['orders']:
        if record['D'] != 'newOrder':
            continue
        case_id = identify(record['A'])
        json_cases.append(case_id)
        for q in case_map[case_id]['queries']:
            matches = [v for k, v in record['A'].items() if k == q['agent_field'] or k.startswith(q['agent_field'] + ':')]
            if len(matches) > 1:
                raise ValueError('Ambiguous JSON field')
            if matches:
                q['json_status'] = 'sources-present' if matches[0]['A'] else 'empty-sources'
    if len(json_cases) != len(set(json_cases)):
        raise ValueError('Duplicate order/customer target records')

    base = run / 'agent-logs/orders/AgentLogs/ShadowTaint/tf2-preflight/sink'
    text_cases = []
    for file in sorted(base.rglob('*OrdersController.newOrder.log')):
        content = file.read_text()
        fields = re.findall(r'^arg#[^\n]*', content, re.M)
        case_id = identify(fields)
        text_cases.append(case_id)
        for q in case_map[case_id]['queries']:
            for block in content.split('----------------\n'):
                field = block.splitlines()[0] if block.splitlines() else ''
                if field == q['agent_field'] or field.startswith(q['agent_field'] + ':'):
                    q['text_status'] = 'empty-sources' if '\n    no sources\n' in block else 'sources-present'
        case_map[case_id]['text_log'] = str(file.relative_to(run))
    if len(text_cases) != len(set(text_cases)):
        raise ValueError('Duplicate text target identities')
    queries = [q for c in cases for q in c['queries']]
    return {
        'schema_version': 1, 'run': str(run.resolve()), 'services': services,
        'target_queries': len(queries),
        'no_target_checks': sum(len(json.loads((run / b['case'] / 'query-contract.json').read_text())['queries'])
                                for b in result['cases'] if not b['expected_target']),
        'text_query_status': dict(Counter(q['text_status'] for q in queries)),
        'json_query_status': dict(Counter(q['json_status'] for q in queries)),
        'successful_cases_missing_text': [c['case'] for c in cases if c['expected_target'] and c['case'] not in text_cases],
        'successful_cases_missing_json': [c['case'] for c in cases if c['expected_target'] and c['case'] not in json_cases],
        'target_matching_basis': 'unique customer record identity; no source/RPC join inferred',
        'accuracy_eligible': False, 'cross_service_join_validated': False,
        'limitations': ['Public obfuscated JSON keys A/B/C/D/E/F interpreted from matching text/bytecode; no source schema guarantee.',
                        'No runtime upstream response oracle; this is output coverage, not accuracy scoring.',
                        'Empty source sets and missing fields are reported separately.',
                        'ThreadLocal/async cause requires in-application confirmation; independent probe alone is insufficient.'],
        'cases': cases, 'raw_log_sha256': hashes,
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    report = audit(args.run)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k not in ('cases', 'raw_log_sha256', 'services')}, indent=2))
