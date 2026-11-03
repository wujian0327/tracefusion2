"""Byte-exact record inventory of complete prior captures; no inference/trimming.

Categories describe necessary proof roles, not a deletion recommendation.
Every record is counted once. Nested payload estimates are deliberately not
summed into exact protocol bytes.
"""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path


def role(kind):
    if kind in ('read','execution-static-read'):
        return 'data', 'Read operand, concrete owner/field/version and consistency; may feed later effects or selection.'
    if kind in ('branch','execution-type-test','execution-handler','execution-throw'):
        return 'selection_exception', 'Actual control/member/exception path; absence of a target data edge does not remove this obligation.'
    if kind.startswith(('locality-','sql-locality-')) or kind in ('write','write-version','execution-array','execution-lambda','execution-defaults','execution-allocation'):
        return 'alias_effect_contract', 'Birth/ownership, reference closure, publication, actual writes/versions and finite implementation proof.'
    if kind.startswith(('binding-','transport-','http-','json-','communication-')):
        return 'boundary_binding_integrity', 'Declared read occurrence, actual wire/object projection, target and message identities/completion.'
    if kind.startswith(('collection-','execution-','request-entity-','source-')) or kind in ('enter','exit','abort'):
        return 'execution_effect', 'Actual implementation/arguments/return, container effects, callback scope and ordinary/exceptional completion.'
    if kind in ('start','metrics','class','class-verified','runtime','problem') or 'class' in kind:
        return 'metadata_integrity', 'Frozen plan/runtime/class evidence, batch closure and sticky failure; keep necessary evidence in every mode.'
    return 'unclassified_keep', 'Not yet assigned a proof role; retain. No current-consumer argument licenses omission.'


def inventory(path):
    counts=defaultdict(lambda:dict(events=0,bytes=0))
    categories=defaultdict(lambda:dict(events=0,bytes=0))
    keys=defaultdict(int); total=0; selected=0; digest=hashlib.sha256()
    with path.open('rb') as stream:
        for raw in stream:
            digest.update(raw); row=json.loads(raw);kind=row['kind'];category,reason=role(kind)
            total+=len(raw);counts[kind]['events']+=1;counts[kind]['bytes']+=len(raw)
            counts[kind].update(category=category,retention_reason=reason)
            categories[category]['events']+=1;categories[category]['bytes']+=len(raw)
            for key,value in row.items():
                # A comparable payload-size estimate only: original separators,
                # escaping and key bytes are part of exact whole-record counts.
                keys[key]+=len(json.dumps(value,separators=(',',':'),ensure_ascii=False).encode())
            selected+=int(bool(row.get('body_observation',{}).get('selected')))
    assert total==path.stat().st_size
    for count in counts.values():count['byte_share']=count['bytes']/total
    return dict(path=str(path),sha256=digest.hexdigest(),complete_file_bytes=total,
                total_events=sum(v['events']for v in counts.values()),selected_body_calls=selected,
                categories=dict(categories),record_types=dict(sorted(counts.items(),key=lambda item:-item[1]['bytes'])),
                payload_value_bytes_estimate=dict(sorted(keys.items(),key=lambda item:-item[1])),
                filtered=False,performance_measurement=False)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('captures',type=Path,nargs='+');args=parser.parse_args()
    args.out.mkdir(parents=True,exist_ok=False)
    result=[inventory(path)for path in args.captures]
    (args.out/'inventory.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    for item in result:print(item['path'],item['complete_file_bytes'],list(item['record_types'].items())[:5])
