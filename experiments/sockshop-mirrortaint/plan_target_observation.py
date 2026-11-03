"""Conservative value demands for boundary snapshots of the execution kernel.

Effects, references, membership, versions, source occurrences and finite-contract
proofs are separate obligations. This module never declares a call read-only.
"""
from plan_execution_closure import application_value_fields, SCALARS
from plan_service_observations import callee
from query_observation_planner import digest


def obligations(plan):
    cfg=plan['execution_kernel']
    required=set(application_value_fields(plan))
    reasons={field:{'target or interpreted read/accessor/constructor dependency'} for field in required}
    # Projected decoder state can feed a finite public transfer without a
    # GETFIELD in an interpreted Frame. Retain its entire specified projection.
    for spec in cfg.get('decoder_birth_sites',{}).values():
        for field in spec.get('written_fields',[]):
            required.add(field);reasons.setdefault(field,set()).add('public decoder transfer')
    # Existing source snapshots are intentionally restricted to their original
    # field universe. The closure cannot move or introduce a source boundary.
    original=set(plan['response_binding']['source_fields'])
    # Conversion consumes its independently observed input projection. Until
    # that public contract declares smaller input demands, retain the original
    # source-field universe, including fields declared by different DTO types.
    if cfg.get('conversion_contracts') or plan.get('json_conversion_methods'):
        for field in original:
            required.add(field);reasons.setdefault(field,set()).add('complete finite conversion input projection')
    properties={p['field']:p for props in plan['response_graph_schema'].values() for p in props}
    omit={field:properties[field]['descriptor'] for field in sorted(original-required)
          if field in properties and properties[field]['descriptor'] in SCALARS}
    maps={}
    target=plan['target'];binding=plan['response_binding'];prop=properties.get(target)
    body=cfg.get('body_observation')
    # Exact source-object forwarding rules out a later value-producing helper.
    # All observed writes/effects still execute, with their original barriers.
    # Any explicit map/list consumer conservatively disables member projection;
    # no argument-absence heuristic or object-value comparison is used.
    before_source=(body or {}).get('source',{})
    consumers=any(i['op'] in (182,183,184,185) and
                  i.get('owner') in ('java/util/Map','java/util/HashMap','java/util/LinkedHashMap')
                  and not (key==before_source.get('caller') and i['index']<before_source.get('pc',-1))
                  for key,m in cfg['methods'].items() for i in m['instructions'])
    if body and prop and prop['descriptor'] in ('Ljava/util/Map;','Ljava/lang/Object;') and not consumers:
        parts=binding['path'].split('/')[1:]
        if len(parts)==2 and parts[0]==prop['property'] and parts[1] and parts[1]!='*':
            # JSON pointer spelling stays escaped, exactly as in the snapshot.
            maps[target]={'relative_paths':['/'+parts[1]],'reason':'literal leaf of an exactly forwarded source map; no post-source planned map consumer',
                          'source':before_source,'earlier_operations':'Only earlier operations in the acyclic source-caller are excluded from future value demand. Their actual effects/source and selection evidence remain.'}
    policy={'version':1,'enabled':True,'required_fields':sorted(required),
            'omittable_scalar_fields':omit,'container_values':maps,
            'retained_reasons':{k:sorted(v) for k,v in sorted(reasons.items())},
            'source_calls':binding['source_calls'],
            'fallback':'Keep original observations before any omission whenever the current root/scope/type or demand qualification is unavailable.',
            'retains':'All reference traversal and collection epochs, calls/arguments/completion, reads/writes/versions, aliases/publication, branch/exception, sources, target and library certificates.'}
    policy['sha256']=digest(policy)
    return policy


def attach(plan):
    if plan.get('profile')=='execution-dependency':
        plan['target_observation_closure']=obligations(plan)
    return plan
