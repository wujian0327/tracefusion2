#!/usr/bin/env python3
"""Score source-derived field relations in an already independently verified ZIP.

No target execution, re-collection, or taint propagation. Raw byte labels are
projected to field identities using all source value spans, never output values.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import zipfile

from cases import CASES, tokens
from field_truth import manifest

HERE = Path(__file__).resolve().parent
METHODS = ('ours', 'libdft64_original', 'libdft64_extracted')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def project(case, offsets):
    spans = tokens(case['text'])
    fields = set()
    for offset in offsets:
        require(type(offset) is int and 0 <= offset < len(case['text'].encode())+1, 'invalid source offset')
        matches = [p for p,s in spans.items() if s['begin'] <= offset < s['end']]
        require(len(matches) <= 1, 'overlapping value spans')
        # Unexpected syntax/key/NUL origins must become extra relations, not be dropped.
        identity = 'input:v0:' + matches[0] if matches else f'input:v0:$nonvalue-byte:{offset}'
        fields.add(case['name'] + '#' + identity)
    return sorted(fields)


def score(expected, predicted):
    wanted = set(expected)
    if predicted is None:
        return dict(status='unknown', tp=0, fp=0, fn=len(wanted), exact=False)
    got = set(predicted)
    return dict(status='answered', tp=len(wanted & got), fp=len(got - wanted),
                fn=len(wanted - got), exact=(wanted == got))


def summarize(rows):
    counts = Counter()
    for row in rows:
        counts.update({k:row[k] for k in ('tp','fp','fn')})
    tp, fp, fn = (counts[k] for k in ('tp','fp','fn'))
    return dict(scored_queries=len(rows), answered=sum(r['status']=='answered' for r in rows),
                unknown=sum(r['status']=='unknown' for r in rows),
                exact_queries=sum(r['exact'] for r in rows),
                exact_query_rate=sum(r['exact'] for r in rows)/len(rows) if rows else None,
                tp=tp, fp=fp, fn=fn,
                precision=tp/(tp+fp) if tp+fp else None,
                recall=tp/(tp+fn) if tp+fn else None,
                f1=2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else None)


def check_scoring():
    # Hand-computable mistakes ensure disagreement cannot silently score as success.
    require(score(['a','b'],['a','c']) == dict(status='answered',tp=1,fp=1,fn=1,exact=False), 'wrong-field check')
    require(score([],None) == dict(status='unknown',tp=0,fp=0,fn=0,exact=False), 'unknown != empty')
    require(score(['a'],None)['fn'] == 1, 'unknown positive remains missed')
    require(score([],[])['exact'] and score([],['a'])['fp'] == 1, 'empty-source checks')
    a = CASES[0]; spans = tokens(a['text'])
    require(project(a,[spans['/recipient']['begin']]) == ['equal_fields#input:v0:/recipient'], 'same-value identity')
    require(project(a,[0]) == ['equal_fields#input:v0:$nonvalue-byte:0'], 'unexpected syntax retained')
    total = summarize([score(['a','b'],['a','c']),score(['d'],None)])
    require(total['precision'] == .5 and total['recall'] == 1/3 and total['unknown'] == 1,
            'aggregate denominator check')
    return 'passed: wrong field, empty, unknown, same-value identity, unexpected syntax and aggregate denominators'


def evaluate(archive, verification, out):
    require(not out.exists(), 'output exists')
    certified = json.loads(verification.read_text())
    require(certified['status'] == 'verified_bounded_native_parser_calibration', 'uncalibrated evidence')
    require(digest(archive) == certified['archive']['sha256'] and
            archive.stat().st_size == certified['archive']['size_bytes'], 'archive differs from verified evidence')
    truth = manifest()
    require(truth['cjson_sha256'] == certified['cjson_source_sha256']['cJSON.c'], 'truth source version')
    prior = {(q['case'],q['path']):q for q in certified['queries']}
    cases = {c['name']:(i,c) for i,c in enumerate(CASES,1)}
    results = []
    with zipfile.ZipFile(archive) as z:
        names = z.namelist()
        require(len(names) == len(set(names)), 'duplicate archive member')
        roots = {Path(n).parts[0] for n in names}
        require(len(roots) == 1, 'archive root')
        root = roots.pop()
        def data(name):
            return z.read(root + '/' + name)
        def read(name):
            return json.loads(data(name))
        require(hashlib.sha256(data('source/cJSON.c')).hexdigest() == truth['cjson_sha256'], 'archived cJSON')
        require(data('adapter-source/cases.py') == (HERE/'cases.py').read_bytes(), 'case definitions changed')
        for annotation in truth['queries']:
            q = dict(annotation)
            ci, case = cases[q['case']]; qi = case['paths'].index(q['path'])
            checked = prior[q['case'],q['path']]
            q['expected_sources'] = None if q['expected_sources'] is None else sorted(
                q['case'] + '#' + s for s in q['expected_sources'])
            q['target_identity'] = dict(case=q['case'], requested_path=q['path'],
                                        binding='native node + output allocation; see calibrated evidence')
            if q['status'] == 'no_sink':
                require(checked['status'] == 'native_no_sink', 'no-sink evidence')
                q['scoring_note'] = 'Shared native binding check; no per-engine decoder query exists'
            elif q['status'] == 'out_of_scope':
                require(checked['status'] == 'not_in_parser_scope', 'scope differs from predeclared decoder scope')
                q['scoring_note'] = 'Expected replacement source retained, not scored as a successful decoder answer'
            else:
                require(checked['status'] == 'native_calibrated', 'uncalibrated query')
                prefix = f'case-{ci:02d}-query-{qi:02d}/'
                ours = read(prefix+'ours.json'); lib = read(prefix+'libdft-offline.json')
                raw = [json.loads(s) for s in data(prefix+'observations.jsonl').decode().splitlines() if s.strip()]
                sink, = [r for r in raw if r['kind']=='sink']
                length = len(bytes.fromhex(sink['data']))
                require(lib['allocation_labels'] == sink['allocation_tags'], 'original/extracted tags')
                extracted = sorted({x-1 for b in lib['byte_labels'] for x in b})
                original = sorted({x-1 for b in sink['allocation_tags'][:length] for x in b})
                own = sorted({x for b in ours['byte_source_offsets'] for x in b})
                require(own == ours['source_offsets'] == checked['ours_source_offsets'] and
                        extracted == checked['libdft_source_offsets'], 'certified result differs')
                q['methods'] = {}
                for method, offsets in zip(METHODS, (own,original,extracted)):
                    fields = project(case,offsets)
                    q['methods'][method] = dict(predicted_sources=fields, **score(q['expected_sources'], fields))
            results.append(q)
    included = [q for q in results if q['status']=='scored']
    report = dict(status='scored_verified_native_field_relations', semantics=truth['semantics'],
                  annotation_review=truth['annotation_review'], total_requests=len(results),
                  existing_string_targets=sum(q['status']!='no_sink' for q in results),
                  scored_targets=len(included), out_of_scope_targets=sum(q['status']=='out_of_scope' for q in results),
                  native_no_sink_checks=sum(q['status']=='no_sink' for q in results),
                  scored_target_coverage=len(included)/sum(q['status']!='no_sink' for q in results),
                  expected_relations=sum(len(q['expected_sources']) for q in included),
                  empty_source_queries=sum(not q['expected_sources'] for q in included),
                  methods={m:summarize([q['methods'][m] for q in included]) for m in METHODS},
                  queries=results, scoring_checks=check_scoring(), archive=certified['archive'],
                  verification_sha256=digest(verification),
                  scorer_sha256=digest(Path(__file__)),truth_source_sha256=digest(HERE/'field_truth.py'),
                  performance_eligible=False, independent_per_byte_accuracy=None,
                  limitations=['All metrics conditional on 18 predeclared decoder targets; 2 replacement targets remain excluded',
                               'No independent human second review or blinded annotation',
                               'Field projection cannot expose missing/extra bytes within the same source field',
                               'Positive targets each depend on one source field; no multi-source aggregation evidence',
                               'Original and extracted libdft are one algorithm, not two independent baselines'])
    out.mkdir(parents=True)
    for name, obj in [('field-truth.json',truth),('field-results.json',report)]:
        (out/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n')
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--archive', type=Path, required=True)
    p.add_argument('--verification', type=Path, default=HERE/'parser-host-validation-20261012.json')
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    r = evaluate(a.archive, a.verification, a.output)
    print(json.dumps({k:r[k] for k in ('status','total_requests','scored_targets','expected_relations','methods')}))
