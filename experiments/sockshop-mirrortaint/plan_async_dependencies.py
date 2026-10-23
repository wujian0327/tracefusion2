"""Enable a finite worker replay and task-private result transfer, not a business rule."""
import json
from pathlib import Path
from query_observation_planner import require

RESULT_CTOR = 'org/springframework/scheduling/annotation/AsyncResult.<init>(Ljava/lang/Object;)V'


def attach_async_dependencies(plan, features=None, inventory=None):
    cfg = plan.get('execution_kernel')
    require(cfg and cfg.get('version', 0) >= 2, 'Async dependencies require application Frame replay')
    # Explicit legacy callers retain their declared bundle. Automatic routing
    # supplies only actual API obligations; save alone cannot enable HTTP/tasks.
    explicit_legacy=features is None
    features={'async','request','save'} if explicit_legacy else set(features)
    from contract_applicability import select
    unavailable=[]
    def contract(name,feature):
        c=json.loads((Path(__file__).parent/name).read_text())
        if feature=='save':c['additional_profiles']=[json.loads((Path(__file__).parent/'save-provided-id-contracts-20261023.json').read_text())]
        if explicit_legacy:return c
        picked=select(c,inventory)
        if picked is None:unavailable.append({'feature':feature,'reason':'No reviewed full library hash profile for actual input JAR'})
        return picked
    if 'async' in features:
        chosen=contract('async-task-contracts-20261021.json','async')
        if chosen:plan['async_protocol']=chosen;plan['async_dependencies'] = {'version': 1, 'mutable_argument_heap_inheritance': False,
                                'export': 'immutable scalar or private task allocation with scalar fields',
                                'nested_tasks': False}
    if 'request' in features:
        chosen=contract('request-entity-contracts-20261021.json','request')
        if chosen:cfg['request_entity_contracts']=chosen
    model_births = cfg.get('decoder_birth_sites', {})
    cfg['decoder_birth_sites'] = model_births
    if 'save' in features:
        chosen=contract('save-effect-contracts-20261021.json','save')
        if chosen:cfg['save_effect_contracts']=chosen
    cfg['unavailable_library_contracts']=unavailable
    if plan.get('async_protocol') and RESULT_CTOR in cfg['constructors']:
        cfg['constructors'][RESULT_CTOR] = {'kind': 'async-result'}
    return plan
