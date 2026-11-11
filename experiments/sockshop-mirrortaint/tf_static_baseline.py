"""A configuration baseline, not a reproduction of SelectiveTaint.

Static permissions are the existing conservative planner's fixed field/site
sets. Runtime checks still establish that the actual execution satisfies those
permissions. The only additional per-occurrence cut currently implemented is
the effect-body cut, whose disjointness needs a live locality certificate.
No propagation, required-field set, framework contract or event format changes.
"""
import copy


def configure(plan, baseline):
    if baseline not in ('full', 'static', 'selective'):
        raise ValueError('Unknown TF baseline: ' + baseline)
    closure = plan.get('target_observation_closure', {})
    writes = plan.get('execution_observation_closure', {})
    body = plan.get('execution_kernel', {}).get('body_observation', {})
    # Do not edit the plan or erase certificates/required fields. Disabled body
    # collection enters the existing pre-omission full path, not offline repair.
    options = ['-Dservice.mode=' + ('full' if baseline == 'full' else 'selective'),
               '-Dservice.target.observation=true',
               '-Dservice.write.observation=true',
               '-Dservice.body.observation=' + str(baseline == 'selective').lower()]
    return {'baseline': baseline, 'jvm_options': options,
            'collector_mode_alias_disclosed': baseline == 'static',
            'fixed_permissions': {
                'read_sites': copy.deepcopy(plan.get('selected_read_sites', [])),
                'boundary_fields': copy.deepcopy(closure.get('omittable_scalar_fields', {})),
                'boundary_members': copy.deepcopy(closure.get('container_values', {})),
                'constructor_writes': copy.deepcopy(writes.get('candidate_write_sites', {})),
                'ordinary_writes': copy.deepcopy(writes.get('application_write_values', {}).get('sites', {}))},
            'runtime_extra_candidates': copy.deepcopy(body.get('candidates', {})),
            'runtime_extra_enabled': baseline == 'selective',
            'validity_guards_retained': [
                'loaded implementation/hash/runtime and actual type',
                'root, active call/Frame and snapshot position',
                'source pairing, write clocks, completion and exception',
                'alias/publication/effect certificates and sticky failure'],
            'definition': 'Fixed conservative static permissions plus validity guards; '
                          'selective additionally permits the existing live-locality effect-body cut. '
                          'Static may use the same scalar/member permissions under their original guards. '
                          'No claim of a separate static pointer analysis or new pruning algorithm.'}
