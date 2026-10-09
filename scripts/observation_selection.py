"""Query-relative observation closure over an explicitly declared evidence model.

This core knows neither Go nor eBPF. It does not discover the model from code,
prove its semantic soundness, or optimize a minimum-cost observation set.
"""
import hashlib
import json


def require(condition,message):
    if not condition:raise ValueError(message)


def select_observations(observations,rules,targets,context):
    """Keep ALL producers of every needed observed fact, including alternatives.

    Each derived fact has one conjunctive dependency rule. Multiple observation
    sites for a leaf are possible execution alternatives, NOT interchangeable
    set-cover choices. Fail closed on absent facts and cyclic/ambiguous models.
    """
    targets=sorted(set(targets))
    require(targets,'Empty query')
    ids=[o['site_id'] for o in observations]
    require(len(ids)==len(set(ids)),'Duplicate observation ID')
    producers={}
    for observation in observations:
        require(observation['facts'],'Observation has no declared facts')
        for fact in set(observation['facts']):
            producers.setdefault(fact,[]).append(observation['site_id'])
    require(not set(producers).intersection(rules),'A fact cannot be both observed and derived')
    for dependencies in rules.values():
        require(isinstance(dependencies,list) and dependencies and len(dependencies)==len(set(dependencies)),
                'Derived facts require nonempty conjunctive dependencies')
    visited=set();active=set();steps={};selected=set()
    def visit(fact):
        if fact in visited:return
        require(fact not in active,'Cyclic evidence dependency: '+fact)
        active.add(fact)
        if fact in rules:
            for dependency in rules[fact]:visit(dependency)
            steps[fact]=dict(kind='derived',dependencies=sorted(rules[fact]))
        else:
            require(fact in producers,'No evidence rule or observation for: '+fact)
            sites=sorted(producers[fact]);selected.update(sites)
            steps[fact]=dict(kind='observed',sites=sites)
        active.remove(fact);visited.add(fact)
    for target in targets:visit(target)
    decisions=[]
    for observation in sorted(observations,key=lambda o:o['site_id']):
        relevant=sorted(set(observation['facts']).intersection(visited))
        decisions.append(dict(site_id=observation['site_id'],action='keep' if relevant else 'drop',
            relevant_facts=relevant,reason='Producer of required observed facts' if relevant else
            'Declared facts are outside this query dependency closure'))
    model=dict(observations=observations,rules=rules,context=context)
    digest=hashlib.sha256(json.dumps(model,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    return dict(algorithm='all-producers-backward-closure-v1',model_sha256=digest,
                targets=targets,required_facts=sorted(visited),selected_site_ids=sorted(selected),
                derivation={fact:steps[fact] for fact in sorted(steps)},decisions=decisions,
                scope='Sufficiency relative to the declared evidence model; no global minimality or semantic proof')


def verify_selection(observations,rules,targets,context,certificate):
    expected=select_observations(observations,rules,targets,context)
    require(certificate==expected,'Selection certificate differs from recomputed dependency closure')
    return expected
