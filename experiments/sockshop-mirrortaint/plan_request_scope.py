"""Optional output scope, licensed only for a concrete mapped wrapper entry."""
import json
from pathlib import Path


def attach(plan,model):
    if not plan.get('map_wrapper_observation'):return plan
    method=model['methods'][plan['entry']];owner=model['classes'][method['owner']]
    if not any(a in owner.get('annotations',[])for a in('Lorg/springframework/web/bind/annotation/RestController;','Lorg/springframework/stereotype/Controller;')):return plan
    if not any(a.startswith('Lorg/springframework/web/bind/annotation/')and a.endswith('Mapping;')for a in method.get('annotations',[])):return plan
    contract=json.loads(Path(__file__).with_name('request-scope-contracts-20261104.json').read_text())
    controllers={n for n,c in model['classes'].items()if any(a in c.get('annotations',[])for a in('Lorg/springframework/web/bind/annotation/RestController;','Lorg/springframework/stereotype/Controller;'))}
    handlers={k:model['classes'][m['owner']]['sha256']for k,m in model['methods'].items()if m['owner']in controllers and any(a.startswith('Lorg/springframework/web/bind/annotation/')and a.endswith('Mapping;')for a in m.get('annotations',[]))}
    plan['query_request_scope']={'version':1,'entry':plan['entry'],'entry_class':method['owner'],'entry_class_sha256':owner['sha256'],'handlers':handlers,
        'framework':contract,'pending':'Actual framework class/loader, handler, request, response and message must be checked before any output traversal can be omitted.'}
    return plan
