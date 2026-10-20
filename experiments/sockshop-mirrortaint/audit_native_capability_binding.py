#!/usr/bin/env python3
"""Fault actual native captures without altering raw evidence or source truth."""
import argparse
import copy
import json
from pathlib import Path
from run_planned_service import load,save,sha
from run_mirror_capability_probe import read_events,native_answer


def audit(root,out):
    out.mkdir(parents=True,exist_ok=False)
    captures=[(root/'cart-create-calibrated07/capture','/customerId'),
              (root/'matched-cart08-final/sockshop-carts-getItems-each-quantity/native/capture','/0/quantity')]
    checks={};hashes={}
    for number,(capture,path) in enumerate(captures):
        events=capture/'carts/native-capability.jsonl';hashes[str(events)]=sha(events)
        rows=read_events(capture,'carts');case=next(c for c in load(capture/'run.json')['cases'] if c['response'] and c['case']=='group-0') if number else load(capture/'run.json')['cases'][0]
        message=case['message'];a=native_answer(rows,message,path);assert a['state']=='known'
        checks[str(number)+'-positive']=True
        for kind in ('target-owner','target-version','source-missing','source-ambiguous','message-ambiguous','native-observation-version','native-observation-value'):
            changed=copy.deepcopy(rows);t=next(r for r in changed if r['kind']=='target' and r['context'].get('message')==message)
            sf=next(f for f in t['wire_fields'] if f['path']==path)
            tf=next(f for f in t['fields'] if all(f.get(k)==sf.get(k) for k in ('owner','field','version')))
            if kind=='target-owner':tf['owner']='same-value-other-object'
            elif kind=='target-version':tf['version']+=1
            elif kind=='source-missing':changed=[r for r in changed if not (r['kind']=='source' and r['root']==a['root'])]
            elif kind=='source-ambiguous':
                provider=a['sources'][0]
                s=next(r for r in changed if r['kind']=='source' and r['root']==a['root'] and r['call']==provider[0] and r['ordinal']==provider[1])
                d=copy.deepcopy(s);d['ordinal']+=100;changed.append(d)
            elif kind=='message-ambiguous':changed.append(copy.deepcopy(t))
            else:
                os=[f for r in changed if r['kind']=='native-observation' and r['root']==a['root'] for f in r['fields'] if all(f.get(k)==sf.get(k) for k in ('owner','field','version'))]
                if not os:continue
                for f in os:
                    if kind.endswith('version'):f['version']+=1
                    else:f['value']='same-tags-different-observed-value'
            checks[str(number)+'-'+kind]=native_answer(changed,message,path)['state']!='known'
    assert all(sha(Path(p))==h for p,h in hashes.items())
    result={'all_passed':all(checks.values()),'checks':checks,'raw_sha256_unchanged':hashes,
            'scope':'Actual original Cart capture; covers configured target identity/version, absent/ambiguous source, ambiguous request and native collector cache. Does not claim arbitrary reflective writes or general concurrency.'}
    save(out/'audit.json',result);print(json.dumps(result,indent=2))
    assert result['all_passed']


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();audit(a.root.resolve(),a.out.resolve())
