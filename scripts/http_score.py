#!/usr/bin/env python3
"""Score query-specific HTTP edges and request membership against a private oracle."""
import argparse
import json
from pathlib import Path


def measures(tp, fp, fn):
    # Undefined precision/recall are null. F1=0 when truth is nonempty but predictions empty.
    p = tp / (tp + fp) if tp + fp else None
    r = tp / (tp + fn) if tp + fn else None
    f1 = 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None
    return {'tp': tp, 'fp': fp, 'fn': fn, 'precision': p, 'recall': r, 'f1': f1}


def score(reference, prediction):
    expected = {q['query_id']: q for q in reference['queries']}
    predicted = {}
    known = set(reference['observed_event_ids'])
    for q in prediction['queries']:
        ident = q['query_id']
        if ident not in expected or ident in predicted:
            raise ValueError('Unknown or duplicate predicted query')
        if q['root_event_id'] != expected[ident]['root_event_id']:
            raise ValueError('Predicted root differs from supplied query')
        edges = set()
        for e in q['edges']:
            if set(e) != {'parent', 'child', 'relation'} or e['relation'] not in ('local', 'transport'):
                raise ValueError('Invalid predicted edge')
            if e['parent'] not in known or e['child'] not in known:
                raise ValueError('Prediction uses an unknown event ID')
            edges.add((e['parent'], e['child'], e['relation']))
        predicted[ident] = edges
    rows, edge_total, member_total = [], [0, 0, 0], [0, 0, 0]
    for ident, q in expected.items():
        truth = {(e['parent'], e['child'], e['relation']) for e in q['edges']}
        actual = predicted.get(ident, set())
        counts = (len(actual & truth), len(actual - truth), len(truth - actual))
        members = {v for e in actual for v in e[:2]} - {q['root_event_id']}
        true_members = set(q['nodes']) - {q['root_event_id']}
        membership = (len(members & true_members), len(members - true_members), len(true_members - members))
        edge_total = [a + b for a, b in zip(edge_total, counts)]
        member_total = [a + b for a, b in zip(member_total, membership)]
        rows.append({'query_id': ident, 'exact_match': actual == truth,
                     'edges': measures(*counts), 'request_membership': measures(*membership)})
    return {'schema_version': 1, 'scope': reference['scope'], 'queries': len(rows),
            'edge_micro': measures(*edge_total), 'request_membership_micro': measures(*member_total),
            'exact_chain_match_rate': sum(r['exact_match'] for r in rows) / len(rows) if rows else None,
            'per_query': rows,
            'interpretation': 'small-sample call-chain baseline, not field provenance accuracy'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reference', type=Path, required=True)
    p.add_argument('--prediction', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    result = score(json.loads(a.reference.read_text()), json.loads(a.prediction.read_text()))
    with a.out.open('x') as f: json.dump(result, f, indent=2)
    print(json.dumps({k: v for k, v in result.items() if k != 'per_query'}, indent=2))


if __name__ == '__main__': main()
