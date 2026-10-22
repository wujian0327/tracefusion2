"""Verify UUID value projection evidence before normal field graph binding."""
import re
from query_observation_planner import require

def validate_uuid_projection(plan,rows):
    config=plan.get('uuid_projection')
    if not config:return
    runtime=[r for r in rows if r['kind']=='uuid-runtime'];require(len(runtime)==1,'UUID runtime missing/ambiguous')
    require(any(all(runtime[0].get(k)==p[k]for k in ('java_runtime_version','class_sha256'))for p in config['profiles']),'UUID JDK definition differs')
    wires=[r for r in rows if r['kind']=='uuid-wire'];pin=config['serializer_class_sha256']['com/fasterxml/jackson/databind/ser/std/UUIDSerializer']
    for r in wires:require(r['serializer_class_sha256']==pin,'UUID serializer definition differs')
    def scan(value):
        if isinstance(value,dict):
            if value.get('uuid_type'):
                require(value['uuid_type']=='java.util.UUID' and value.get('object') is not None and re.fullmatch('[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}',value.get('value','')),'UUID projection malformed')
            for v in value.values():scan(v)
        elif isinstance(value,list):
            for v in value:scan(v)
    for r in rows:
        scan(r)
        if r['kind']=='http-json' and r.get('direction')=='response' and r.get('phase')=='write':
            for f in r['fields']:
                if f['observed'].get('uuid_type'):
                    expected=plan['response_binding']['path'].split('/');actual=f['path'].split('/')
                    if len(expected)==len(actual) and all(x==y or x=='*'and y.isdecimal()for x,y in zip(expected,actual)):
                        require(any(w['observed']==f['observed'] and w.get('message')==r.get('message') and w['seq']<r['seq']for w in wires),'UUID field lacks actual textual serializer evidence')
