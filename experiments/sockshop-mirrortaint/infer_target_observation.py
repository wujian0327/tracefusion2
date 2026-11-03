"""Authenticate value projection against a recomputed conservative plan.

This validates absence permissions, not value equality, and creates no origins.
"""
from query_observation_planner import require
from plan_target_observation import obligations


def validate(plan,rows):
    policy=plan.get('target_observation_closure')
    if not policy:
        require(not any('target_observation' in row for row in rows),'Snapshot projection without a plan')
        return {'omitted_values':0}
    require(policy==obligations(plan),'Target value closure/demand proof differs')
    starts=[r for r in rows if r['kind']=='start']
    require(len(starts)==1,'Snapshot projection mode absent/ambiguous')
    footers=[r for r in rows if r['kind']=='metrics']
    require(len(footers)==1 and not footers[0].get('capture_invalid') and
            not any(r['kind']=='problem'for r in rows),
            'Snapshot projection requires complete, non-damaged capture')
    mode=starts[0]['mode'];counts=0
    for row in rows:
        if row['kind'] not in ('binding-source','binding-input','binding-opaque-touch','binding-opaque-result'):
            require('target_observation' not in row,'Projection annotation outside a boundary snapshot')
            continue
        proof=row.get('target_observation')
        # Unsupported opaque snapshots have a separate explicit identity fact;
        # they were not projected and retain their original conservative effect.
        if row.get('snapshot_unsupported'):
            require(proof is None,'Unsupported snapshot claims a projection')
            continue
        require(proof and proof['version']==1 and proof['policy_sha256']==policy['sha256'],
                'Snapshot value projection proof missing/different')
        require(type(proof['selected'])is bool and
                (not proof['selected'] or mode=='selective' and policy['enabled']),
                'Snapshot cut in full/disabled mode')
        for key,allowed in [('scalar_fields',policy['omittable_scalar_fields']),('container_values',policy['container_values'])]:
            require(isinstance(proof[key],dict),'Snapshot omission counters absent')
            for field,count in proof[key].items():
                require(proof['selected'] and field in allowed and type(count)is int and count>0,
                        'Snapshot omitted a necessary value')
                counts+=count
        if proof['selected']:
            require(all(f['field']not in policy['omittable_scalar_fields']for f in row['fields']),
                    'Projected snapshot retained a declared scalar omission')
    return {'omitted_values':counts}
