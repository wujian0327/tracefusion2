"""Finite target-observation permission; never a propagation/effect summary."""
import json
from pathlib import Path


def attach(plan,model):
    contract=json.loads(Path(__file__).with_name('map-wrapper-contracts-20261103.json').read_text())
    classes=model['classes'];candidates={}
    for name in classes:
        chain=[];owner=name;seen=set()
        while owner in classes and owner not in seen:
            seen.add(owner);c=classes[owner]
            if c.get('annotations')or c.get('interfaces')or any(not f['access']&8 or f.get('annotations')for f in c['fields']):break
            if any(m['owner']==owner and(m['name']in contract['read_methods']or m.get('annotations'))for m in model['methods'].values()):break
            chain.append({'class':owner,'class_sha256':c['sha256'],'super':c['super']})
            owner=c['super']
            if owner=='java/util/HashMap':candidates[name]=chain;break
    desc=model['methods'][plan['entry']]['desc'].split(')')[1]
    if desc[1:-1]in candidates:plan['map_wrapper_observation']={'version':2,'target_only':True,'candidates':candidates,'contract':contract,
        'declared_return_descriptor':desc}
    return plan
