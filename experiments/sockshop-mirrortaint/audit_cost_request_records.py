#!/usr/bin/env python3
"""Attribute final complete records to measured requests, without propagation.

Buffered file visibility is not an emission timestamp. The online prefix-window
meter is retained; this additional meter uses raw message/call/frame identities
after capture closure. Global setup records remain in whole-batch totals.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
from run_planned_service import load, save, sha


def cohort(paths, messages):
    records=[];parent={};labels={}
    def find(k):
        parent.setdefault(k,k)
        if parent[k]!=k:parent[k]=find(parent[k])
        return parent[k]
    def union(a,b):
        a,b=find(a),find(b)
        if a!=b:parent[b]=a
    for role,path in paths.items():
        for line in path.read_bytes().splitlines(keepends=True):
            assert line.endswith(b'\n'), ('Unclosed partial record',path)
            r=json.loads(line);records.append((role,r,len(line)))
            f=r.get('frame')
            if f:
                k=('frame',role,f);find(k)
                if r.get('parent') and r['kind']=='enter':union(k,('frame',role,r['parent']))
                if r.get('message'):union(k,('message',r['message']))
            if r.get('message') and r.get('parent_message'):
                union(('message',r['message']),('message',r['parent_message']))
    for message in messages:
        k=find(('message',message));labels.setdefault(k,set()).add(message)
    assert all(len(v)==1 for v in labels.values()), 'Two client requests merged by raw identity'
    totals={r:{'events':0,'bytes':0,'kinds':Counter()} for r in paths}
    unassigned={r:{'events':0,'bytes':0} for r in paths}
    for role,r,size in records:
        keys=[]
        if r.get('frame'):keys.append(('frame',role,r['frame']))
        for key in ('message','parent_message'):
            if r.get(key):keys.append(('message',r[key]))
        selected={m for k in keys for m in labels.get(find(k),set())}
        assert len(selected)<=1
        if selected:
            d=totals[role];d['events']+=1;d['bytes']+=size;d['kinds'][r['kind']]+=1
        else:
            unassigned[role]['events']+=1;unassigned[role]['bytes']+=size
    return {'request_records':totals,'outside_cohort_or_global':unassigned,
            'total_events':len(records),'raw_sha256':{r:sha(p) for r,p in paths.items()}}


def audit(root):
    results={}
    for kind,home in load(root/'formal-run-map.json').items():
        cfg=load(root/home/'config.json')
        for name,mode in cfg['order']:
            if mode=='original':continue
            trial=root/home/name;dest=trial/('trainticket' if kind=='price' else 'capture')
            paths={p.parent.name:p for p in dest.glob('*/events.jsonl')}
            # Cart's reused Compose helper creates empty unused role folders;
            # only files belonging to actually deployed services are present.
            measured=load(trial/'steady.json')['requests']
            result=cohort(paths,{r['message'] for r in measured})
            result.update(kind=kind,trial=name,mode=mode,measured_requests=len(measured))
            save(trial/'measured-request-records.json',result);results[kind+'/'+name]=result
    save(root/'request-record-audit.json',{'all_passed':True,'measurements':results,
        'scope':'Final records attributable by raw message/frame/parent identities; startup/global records excluded here and retained in whole batch. No source propagation or value matching.'})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',required=True,type=Path);audit(p.parse_args().root.resolve())
