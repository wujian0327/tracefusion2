"""Checkout adapter: explicit identity-query evidence contract, not source inference."""
import copy
from observation_selection import select_observations,verify_selection,require

DEFAULT_QUERIES=('identity.Item','identity.Cost')
CHECKS='diagnostic.operand_consistency'
RULES={
    'execution.scope':['scope.entry','scope.exit'],
    'conversion.instances':['conversion.entry','conversion.return','execution.scope'],
    'identity.Item':['input.Item','published.Item','final.Item','execution.scope'],
    'identity.Cost':['conversion.instances','published.Cost','final.Cost','execution.scope'],
    CHECKS:['operand.Item','operand.Cost','published.Item','published.Cost','execution.scope'],
}
FACTS={
    'entry':['scope.entry','input.Item'],
    'exit':['scope.exit','final.Item','final.Cost'],
    'publication':['published.Item','published.Cost'],
    'conversion_enter':['conversion.entry'],
    'conversion_return':['conversion.return'],
    'store_operand':['diagnostic.store_operand'],
}
ASSUMPTIONS=[
    'The binary adapter correctly identifies all scoped entries, publications, conversion boundaries and return alternatives.',
    'One invocation/process; PID/goroutine tags and event timestamps are valid; observed objects remain live with stable addresses.',
    'Every retained probe is attached; submitted/read/lost counters and boundary pairing checks pass at runtime.',
    'Query means reference identity at observed boundaries, not field contents, complete writes, implicit flow or remote computation.',
    'All producers of a required fact are retained. Probe record fields are bundled; there is no byte-level payload minimization.',
]


def model(plan,sites):
    observations=[]
    for site in sites:
        kind=site['kind']
        if kind=='field_operand':
            require(site.get('field','Item') in ('Item','Cost'),'Unknown field observation')
            facts=['operand.'+site.get('field','Item')]
        else:
            require(kind in FACTS,'Undeclared observation kind: '+kind)
            facts=FACTS[kind]
        observations.append(dict(site_id=site['id'],facts=facts))
    context=dict(adapter='checkout-reference-evidence-v1',binary_sha256=plan['binary_sha256'],
                 function=plan.get('function'),abi=plan.get('abi'),item_offset=plan['item_offset'],
                 cost_offset=plan['cost_offset'],schema_version=plan['schema_version'],
                 go=plan.get('go'),max_items=plan.get('max_items'),scope=plan.get('scope'),
                 catalog_sites=sites,assumptions=list(ASSUMPTIONS))
    return observations,context


def automatic_plan(plan,queries=DEFAULT_QUERIES):
    require(plan.get('schema_version')==2,'Selection requires Item/Cost v2 inventory')
    sites=copy.deepcopy(plan['sites'])
    observations,context=model(plan,sites)
    certificate=select_observations(observations,RULES,queries,context)
    wanted=set(certificate['selected_site_ids'])
    result=copy.deepcopy(plan)
    result.update(sites=[s for s in sites if s['id'] in wanted],
                  event_order=[s['id'] for s in sites if s['id'] in wanted],
                  operand_witnesses=CHECKS in queries,
                  strategy='boundaries' if set(queries)==set(DEFAULT_QUERIES) else 'query_selected')
    result['selection']=dict(contract='checkout-reference-evidence-v1',queries=sorted(set(queries)),
                             catalog_sites=sites,certificate=certificate,assumptions=list(ASSUMPTIONS))
    return result


def validate_plan(plan,executable=True):
    selection=plan['selection']
    require(selection['contract']=='checkout-reference-evidence-v1','Unknown selection contract')
    queries=selection['queries']
    observations,context=model(plan,selection['catalog_sites'])
    certificate=verify_selection(observations,RULES,queries,context,selection['certificate'])
    wanted=set(certificate['selected_site_ids'])
    expected=[s for s in selection['catalog_sites'] if s['id'] in wanted]
    require(plan['sites']==expected and plan['event_order']==[s['id'] for s in expected],
            'Selected sites/order do not match the certificate')
    require(plan['operand_witnesses']==(CHECKS in queries),'Operand check policy differs from query')
    require(selection['assumptions']==ASSUMPTIONS,'Selection assumptions changed')
    if executable:
        require(set(queries) in (set(DEFAULT_QUERIES),set(DEFAULT_QUERIES)|{CHECKS}),
                'This executor implements the combined Item/Cost query only; other queries are planning-only')
    return certificate
