#!/usr/bin/env python3
"""Timing-only plumbing baseline. Reads algorithm-input only; no oracle imports."""
import argparse
import json
from pathlib import Path


def reconstruct(observations, queries, slack_us=5000):
    required = {'event_id', 'service', 'kind', 'method', 'path', 'peer_service',
                'start_us', 'duration_us', 'status_code'}
    if any(set(o) != required for o in observations):
        raise ValueError('Unexpected observation keys (possible oracle leakage)')
    obs = {o['event_id']: o for o in observations}
    if len(obs) != len(observations):
        raise ValueError('Duplicate event IDs')
    servers = [o for o in observations if o['kind'] == 'SERVER']
    clients = [o for o in observations if o['kind'] == 'CLIENT']
    edges, ties = [], 0
    def end(o): return o['start_us'] + o['duration_us']
    def contains(a, b):
        return a['start_us'] <= b['start_us'] + slack_us and end(a) + slack_us >= end(b)
    # Globally greedy, one-to-one transport pairing. Equal scores are abstentions.
    candidates = []
    for c in clients:
        for s in servers:
            if (c['peer_service'], c['method'], c['path']) != (s['service'], s['method'], s['path']):
                continue
            if contains(c, s):
                cost = abs(c['start_us'] - s['start_us']) + abs(end(c) - end(s))
                candidates.append((cost, c['event_id'], s['event_id']))
    used_clients, used_servers = set(), set()
    for cost in sorted({c[0] for c in candidates}):
        group = [c for c in candidates if c[0] == cost and c[1] not in used_clients and c[2] not in used_servers]
        for _, client, server in group:
            if sum(x[1] == client for x in group) > 1 or sum(x[2] == server for x in group) > 1:
                ties += 1
                # Do not break ties with random event IDs or select a worse match later.
                used_clients.add(client); used_servers.add(server)
                continue
            edges.append({'parent': client, 'child': server, 'relation': 'transport'})
            used_clients.add(client); used_servers.add(server)
    # Attribute an outbound call to the most recently started containing inbound call.
    # This simple heuristic is expected to make mistakes with overlapping requests.
    for c in clients:
        choices = [s for s in servers if s['service'] == c['service'] and contains(s, c)]
        if not choices:
            continue
        latest = max(s['start_us'] for s in choices)
        best = [s for s in choices if s['start_us'] == latest]
        if len(best) != 1:
            ties += 1
            continue
        edges.append({'parent': best[0]['event_id'], 'child': c['event_id'], 'relation': 'local'})
    predictions = []
    for q in queries:
        if set(q) != {'query_id', 'root_event_id'} or q['root_event_id'] not in obs:
            raise ValueError('Invalid query')
        reached, chosen = {q['root_event_id']}, []
        while True:
            new = [e for e in edges if e['parent'] in reached and e not in chosen]
            if not new: break
            chosen.extend(new); reached.update(e['child'] for e in new)
        predictions.append(dict(q, edges=sorted(chosen, key=lambda e: (e['parent'], e['child']))))
    return {'schema_version': 1, 'method': 'timing-greedy-baseline', 'slack_us': slack_us,
            'ambiguous_candidate_count': ties, 'queries': predictions}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('input', type=Path, help='algorithm-input directory only')
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--slack-us', type=int, default=5000)
    a = p.parse_args()
    if a.slack_us < 0: p.error('slack must be nonnegative')
    observations = json.loads((a.input / 'observations.json').read_text())
    queries = json.loads((a.input / 'queries.json').read_text())
    result = reconstruct(observations, queries, a.slack_us)
    with a.out.open('x') as f: json.dump(result, f, indent=2)
    print('Predictions: ' + str(a.out))


if __name__ == '__main__': main()
