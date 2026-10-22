"""Finite UUID leaf projection; copying uses normal object/field/version rules."""
import json
from pathlib import Path

def attach_uuid_projection(plan,model):
    if plan.get('target'):
        owner,name=plan['target'].rsplit('.',1)
        if next(f for f in model['classes'][owner]['fields']if f['name']==name)['desc']=='Ljava/util/UUID;':
            plan['uuid_projection']=json.loads(Path(__file__).with_name('uuid-projection-contracts-20261022.json').read_text())
            plan['contracts'].append('UUID leaf forwarding requires exact immutable UUID identity, pinned JDK bytes and actual default textual serializer; no UUID constructor or value-based source matching.')
    return plan
