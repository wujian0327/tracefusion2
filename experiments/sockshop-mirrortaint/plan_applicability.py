"""Answer-independent candidate obligations, checked before a JVM is launched.

This is an applicability gate, not an effect or serializer contract. Actual
implementation/configuration, source occurrence and wire proofs remain required
by the recorder and offline verifier. Missing deployment evidence is conditional,
never an assertion that the plan can produce an answer.
"""
from plan_service_observations import callee


def declared_sources(query):
    calls = query.get('source_calls', [])
    if not isinstance(calls, (list, tuple)) or any(not isinstance(c, str) or '(' not in c for c in calls):
        raise ValueError('source_calls must contain explicit JVM method descriptors')
    return sorted(set(calls))


def check(plan, model, query, deployment=None):
    declared = declared_sources(query)
    if not set(declared) <= set(plan.get('response_binding', {}).get('source_calls', [])):
        raise ValueError('Candidate dropped declared source boundaries')
    issues, pending, checks = [], [], []
    cfg = plan.get('execution_kernel', {})
    requirements = []
    if plan.get('read_forward_contracts'):
        requirements.append(('read-forward', plan['read_forward_contracts']['runtime_profiles']))
    if cfg:
        requirements.append(('execution', cfg['runtime_profiles']))
        if cfg.get('foundation_values'):
            requirements.append(('foundation', cfg['foundation_values']['jdk_profiles']))
    runtime = (deployment or {}).get('runtime')
    for name, profiles in requirements:
        if runtime is None:
            pending.append('Missing actual runtime witness for ' + name)
            continue
        match = next((p for p in profiles if runtime.get('java_runtime_version') == p['java_runtime_version']
                      and all(runtime.get('class_sha256', {}).get(k) == v for k, v in p['class_sha256'].items())), None)
        checks.append({'contract': name, 'matched': match is not None})
        if match is None:
            issues.append('Actual runtime version/class hashes fail ' + name + ' contract')
    observed_methods = set(cfg.get('methods', {}))
    if plan.get('read_forward_contracts'):
        observed_methods.update(plan['read_forward_contracts']['composed_methods'])
    observed_methods.update(plan.get('frame_methods', []))
    # Read-effect methods have their own call instrumentation; application
    # Frames use binding_callsites. Do not count a declaration as an event.
    binding_sites = set(plan.get('binding_callsites', []))
    coverage = []
    for source in declared:
        sites = []
        for key, m in model['methods'].items():
            for ins in m['instructions']:
                if ins['op'] not in (182, 183, 184, 185) or callee(ins) != source:
                    continue
                site = key + '@' + str(ins['index'])
                interpreted = key in observed_methods
                observation = site in plan.get('source_observation',{}).get('sites',{})
                covered = interpreted and (not cfg or site in binding_sites) or observation
                sites.append({'site': site, 'caller_planned': interpreted, 'observation_only':observation, 'call_instrumented': covered})
        coverage.append({'callee': source, 'sites': sites,
                         'has_observable_callsite': any(s['call_instrumented'] for s in sites),
                         'runtime_obligation': 'Match actual caller Frame, call-id, receiver/implementation, completion, and source field/object/version; declaration alone is not evidence.'})
        if not any(s['call_instrumented'] for s in sites):
            pending.append('Declared source has no covered callsite: ' + source)
    converter = (deployment or {}).get('response_converter')
    for obligation in cfg.get('unavailable_library_contracts', []):
        pending.append('Necessary library effect lacks applicable contract: ' + str(obligation))
    if converter is None:
        pending.append('Response converter/configuration not supplied; runtime wire proof required')
    elif converter.get('class') != 'org.springframework.http.converter.json.MappingJackson2HttpMessageConverter':
        issues.append('No existing communication binding for actual response converter: ' + str(converter.get('class')))
    else:
        pending.append('Jackson implementation, configuration and actual target field projection require existing runtime serialization proofs')
    return {'version': 1, 'status': 'rejected' if issues else 'conditional' if pending else 'applicable',
            'rejections': issues, 'conditions': pending, 'runtime_checks': checks,
            'declared_sources': declared, 'source_coverage': coverage,
            'answer_certified': False, 'library_checks': 'Existing inventory-selected contracts and all runtime implementation/configuration checks remain mandatory.'}
