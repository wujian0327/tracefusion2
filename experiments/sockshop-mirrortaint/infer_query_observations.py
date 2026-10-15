#!/usr/bin/env python3
"""One candidate-consistency reconstructor for full, selected and fixed evidence.

Only captured identities, versions, sites and branch choices select candidates.
Business values and request labels never select origins.
"""
from collections import defaultdict
import json
from pathlib import Path


def infer(plan,path):
    rows=[json.loads(line) for line in Path(path).read_text().splitlines()]
    if [r['seq'] for r in rows]!=list(range(1,len(rows)+1)):raise ValueError('Observation sequence gap')
    if any(r['kind'] in ('problem','abort') for r in rows):raise ValueError('Failed or incomplete capture')
    if len([r for r in rows if r['kind']=='metrics'])!=1:raise ValueError('Missing final capture metrics')
    mode=rows[0]['mode'];sites=set(plan['full_sites'] if mode=='full' else plan['mandatory_sites'] if mode=='fixed' else plan['selected_sites'])
    frames=defaultdict(list)
    for row in rows:
        if row.get('frame'):frames[row['frame']].append(row)
    answers=[]
    for frame,events in frames.items():
        if events[0]['kind']!='enter' or events[-1]['kind']!='exit':raise ValueError('Incomplete root frame')
        enter,exit=events[0],events[-1]
        arguments={a['argument']:a for a in enter['arguments']}
        endings={a['argument']:a for a in exit['arguments']}
        starts={}
        for arg in arguments.values():
            for field in arg.get('fields',[]):
                key=(arg['object'],field['field'])
                if key in starts and starts[key]!=field:raise ValueError('Aliased source snapshots differ')
                starts[key]=field
        actual=[r for r in events if r['kind'] in ('branch','read','write')]
        if any(r['site'] not in sites for r in actual):raise ValueError('Out-of-plan observation')
        candidates=[]
        for candidate in plan['path_candidates']:
            expected=[r for r in candidate['trace'] if r['site'] in sites]
            if len(expected)!=len(actual):continue
            allocations={};matches=True
            for predicted,observed in zip(expected,actual):
                if predicted['kind']!=observed['kind'] or predicted['site']!=observed['site']:
                    matches=False;break
                if predicted['kind']=='branch':
                    if predicted['taken']!=observed['taken']:matches=False;break
                    continue
                if predicted['ref'].startswith('arg:'):
                    owner=arguments[int(predicted['ref'].split(':')[1])]['object']
                else:
                    owner=allocations.setdefault(predicted['ref'],observed['owner'])
                if owner!=observed['owner'] or predicted['field']!=observed['field']:
                    matches=False;break
                base=starts.get((owner,predicted['field']),{}).get('version',0)
                if observed['version']!=base+predicted['version_offset']:
                    matches=False;break
            if matches:
                instantiated=[]
                for q in candidate['answer']:
                    index=int(q['target_ref'].split(':')[1]);start=arguments[index];end=endings[index]
                    if start['object']!=end['object']:raise ValueError('Root argument identity changed')
                    field=next(f for f in end.get('fields',[]) if f['field']==q['field'])
                    base=starts[(start['object'],q['field'])]['version']
                    if field['version']!=base+q['version_offset']:matches=False;break
                    origins=[];known=not q['unknown']
                    for ref,name in q['sources']:
                        source_arg=arguments[int(ref.split(':')[1])]
                        if name=='@argument':version=0
                        else:
                            source_field=starts.get((source_arg['object'],name))
                            if source_field is None:known=False;continue
                            version=source_field['version']
                        origin=[frame,source_arg['object'],name,version]
                        if origin not in origins:origins.append(origin)
                    instantiated.append({'field':q['field'],'owner':end['object'],'version':field['version'],
                                         'known':known,'sources':sorted(origins)})
                if matches:candidates.append(instantiated)
        if not candidates:raise ValueError('No modeled execution matches the captured evidence')
        for index,first in enumerate(candidates[0]):
            possible=[c[index] for c in candidates]
            known=all(p['known'] for p in possible) and all(p==first for p in possible)
            answers.append(dict(first,known=known,sources=first['sources'] if known else None,
                                frame=frame,request_id=enter['request_id'],consistent_paths=len(candidates),
                                reason=None if known else 'Insufficient observations or opaque target expression'))
    return {'mode':mode,'answers':answers,'frames':len(frames),'event_count':len(rows),
            'data_event_count':sum(r['kind'] in ('enter','exit','branch','read','write') for r in rows),
            'field_events':sum(r['kind'] in ('read','write') for r in rows),
            'branch_events':sum(r['kind']=='branch' for r in rows),'log_bytes':Path(path).stat().st_size,
            'hook_metrics':next(r for r in rows if r['kind']=='metrics'),
            'oracle_consumed':False,'matching_uses_values':False,'matching_uses_request_labels':False}
