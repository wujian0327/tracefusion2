"""Optional allocation/nonpublication proof for a bounded default SELECT path.

This does not summarize a mapper's data flow, and never adds a source boundary.
"""
import json
from pathlib import Path


def attach(plan, model):
    contract = json.loads(Path(__file__).with_name('sql-result-locality-contracts-20261031.json').read_text())
    inventory = model.get('library_inventory', {}).get('classes', {})
    if any(inventory.get(k) != v for k, v in contract['class_sha256'].items()):
        return
    classes, methods = model['classes'], model['methods']
    proved = {}

    def plain(owner, visiting=frozenset()):
        if owner == 'java/lang/Object':
            return []
        if owner in proved:
            return proved[owner]
        if owner in visiting or owner not in classes:
            raise ValueError('Initializer hierarchy absent')
        cls = classes[owner]
        m = methods.get(owner + '.<init>()V')
        if not m or m.get('exception_handlers'):
            raise ValueError('Default constructor absent/exceptional')
        ins = m['instructions']
        parent = cls['super']
        if not (len(ins) >= 3 and ins[0]['op'] == 25 and ins[0]['var'] == 0
                and ins[1]['op'] == 183 and ins[1]['owner'] == parent
                and ins[1]['name'] == '<init>' and ins[1]['desc'] == '()V'
                and ins[-1]['op'] == 177):
            raise ValueError('Not a pure default initializer')
        rest = ins[2:-1]
        # A common active-record base stores only this.getClass(). It neither
        # calls a virtual application method nor publishes this.
        if rest and not (len(rest) == 4 and [i['op'] for i in rest] == [25,25,182,181]
                and rest[0]['var'] == rest[1]['var'] == 0
                and rest[2]['owner'] == 'java/lang/Object' and rest[2]['name'] == 'getClass'
                and rest[2]['desc'] == '()Ljava/lang/Class;'
                and rest[3]['owner'] == owner and rest[3]['desc'] == 'Ljava/lang/Class;'):
            raise ValueError('Initializer has effects/callbacks')
        fields = list(plain(parent, visiting | {owner}))
        allowed = {'Z','B','S','C','I','J','F','D','Ljava/lang/String;','Ljava/lang/Long;',
                   'Ljava/lang/Integer;','Ljava/lang/Boolean;','Ljava/lang/Double;',
                   'Ljava/lang/Float;','Ljava/lang/Short;','Ljava/lang/Byte;',
                   'Ljava/util/Date;','Ljava/util/List;','Ljava/lang/Class;'}
        for f in cls['fields']:
            if f['access'] & 8:
                continue
            if f['desc'] not in allowed:
                raise ValueError('Mutable field shape unproved')
            fields.append({'field':owner+'.'+f['name'], 'descriptor':f['desc']})
        proved[owner] = fields
        return fields

    beans = {}
    for owner in classes:
        try:
            fields = plain(owner)
        except (ValueError, KeyError):
            continue
        if fields:
            beans[owner] = {'fields':fields, 'class_sha256':classes[owner]['sha256']}
    accessors = {}
    for key, method in methods.items():
        ins = method['instructions']
        if method['access'] & (8 | 32 | 256 | 1024) or method.get('exception_handlers'):
            continue
        if len(ins) == 3 and ins[0]['op'] == 25 and ins[0]['var'] == 0 and ins[1]['op'] == 180 and ins[2]['op'] in range(172,177):
            accessors[key] = {'kind':'get', 'field':ins[1]['owner']+'.'+ins[1]['name']}
        if len(ins) == 4 and ins[0]['op'] == 25 and ins[0]['var'] == 0 and ins[1]['op'] in range(21,26) and ins[1]['var'] == 1 and ins[2]['op'] == 181 and ins[3]['op'] == 177:
            accessors[key] = {'kind':'set', 'field':ins[2]['owner']+'.'+ins[2]['name']}
    sources = [s for s in plan['response_binding']['source_calls'] if s.endswith(')Ljava/util/List;')]
    if sources and beans:
        plan['execution_kernel']['sql_result_locality'] = {**contract, 'sources':sources,
            'beans':beans, 'accessors':accessors,
            'bean_hierarchy_hashes':{o:classes[o]['sha256'] for o in proved}}
