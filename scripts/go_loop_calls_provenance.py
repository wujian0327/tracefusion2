#!/usr/bin/env python3
"""Go boundary for the shared C/Go executed-call-and-loop engine."""
from functools import partial
import go_provenance as go
from go_interproc_provenance import decode_go
import loop_calls_provenance as core
from language_adapters import GO_CALLS, get_adapter, require


def plan_program(assembly,symbols,config):
    require(get_adapter(config)==GO_CALLS,'Go looped calls require the calls adapter')
    return core.plan_program(assembly,symbols,config,decoder=decode_go)


build=partial(go.build,planner=plan_program)

if __name__=='__main__':
    raise SystemExit(go.common.main(default_scenario=go.common.ROOT/'scenarios/go-loop-calls-provenance',
        prefix='go-loop-calls-provenance',build_fn=build,record_fn=go.collector.record,
        infer_fn=core.infer,evaluate_fn=core.evaluate,required_tools=('go','objdump')))
