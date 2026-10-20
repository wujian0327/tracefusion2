"""Bounded, compositional read-effect checks, not a helper-name whitelist.

Only effects are summarized here. Origins still need an independently observed
input/repository/RPC provider with the same object, field and version. Every
executed child call needs a runtime check; an unresolved child poisons its parent.
Lambda creation is allowed only in these effect checks, not general replay.
"""
from plan_response_binding import pure_constructor
from plan_service_observations import callee
import json
from pathlib import Path


def read_effects(model):
    constructors={k for k,m in model['methods'].items() if pure_constructor(m)}
    constructors.update(('java/lang/Object.<init>()V','java/util/ArrayList.<init>()V','java/lang/StringBuilder.<init>()V'))
    result=[]
    allowed=set(range(0,26))|set(range(54,59))|set(range(87,168))|set(range(172,177))|{177,178,180,182,183,184,185,186,187,192,193,198,199}
    for key,m in model['methods'].items():
        if m['name'].startswith('<') or m['access']&(0x100|0x400|0x20) or m['exception_handlers']:continue
        code=m['instructions'];ok=bool(code)
        for i in code:
            op=i['op']
            if op not in allowed or op in (132,168):ok=False
            if 'target' in i and (i['target'] is None or i['target']<=i['index']):ok=False
            # This method's declaring class is already initialized at entry.
            # Loading another class's static field could execute its initializer.
            if op==178 and i['owner']!=m['owner']:ok=False
            if op==187:
                c=i['type']
                if c not in ('java/util/ArrayList','java/lang/StringBuilder') and (c not in model['classes'] or c+'.<clinit>()V' in model['methods']):ok=False
            if op in (182,183,184,185) and i['name']=='<init>' and callee(i) not in constructors:ok=False
            if op==186:
                # Metafactory allocates a closure; it does not execute the body.
                # Calling that closure remains opaque unless separately checked.
                args=i.get('bootstrap_args',[])
                if i.get('bootstrap')!='java/lang/invoke/LambdaMetafactory.metafactory' or not i['desc'].endswith(')Ljava/util/function/Supplier;') or len(args)!=3 or not isinstance(args[1],dict) or args[1].get('handle') not in model['methods']:ok=False
        if ok:result.append(key)
    return {'version':1,'composed_methods':sorted(result),
            'runtime_profiles':json.loads(Path(__file__).with_name('read-forward-runtimes-20261020.json').read_text())['profiles'],
            'contracts':['Exact checked application implementation, bounded acyclic read effects; all executed child calls checked separately.',
                         'JDK 8 exact ArrayList/Arrays/Collections list -> fresh sequential stream -> findFirst -> present Optional.orElseGet, checked by object identity.',
                         'Empty Optional fallback, arbitrary stream pipelines, saves, async execution and reflective/native effects remain opaque.'],
            'unresolved_calls':'Planning acceptance does not certify all calls. Unchecked effects, failed pairing or child calls retain unknown; root return is never a source.'}
