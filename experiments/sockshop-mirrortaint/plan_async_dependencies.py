"""Enable a finite worker replay and task-private result transfer, not a business rule."""
import json
from pathlib import Path
from query_observation_planner import require

RESULT_CTOR = 'org/springframework/scheduling/annotation/AsyncResult.<init>(Ljava/lang/Object;)V'


def attach_async_dependencies(plan):
    cfg = plan.get('execution_kernel')
    require(cfg and cfg.get('version', 0) >= 2, 'Async dependencies require application Frame replay')
    plan['async_protocol'] = json.loads((Path(__file__).parent/'async-task-contracts-20261021.json').read_text())
    plan['async_dependencies'] = {'version': 1, 'mutable_argument_heap_inheritance': False,
                                'export': 'immutable scalar or private task allocation with scalar fields',
                                'nested_tasks': False}
    if RESULT_CTOR in cfg['constructors']:
        cfg['constructors'][RESULT_CTOR] = {'kind': 'async-result'}
    return plan
