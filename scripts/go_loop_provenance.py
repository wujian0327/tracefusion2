#!/usr/bin/env python3
"""Ordinary Go leaf loops using the shared executed-instruction provenance core."""
from functools import partial

import go_provenance as go
from language_adapters import GO, get_adapter, require


def has_reachable_cycle(plan):
    instructions = {n['offset']:n for n in plan['instructions']}
    active,done = set(),set()
    def visit(off):
        if off in active:return True
        if off in done:return False
        active.add(off);n=instructions[off]
        successors = [] if n['op']=='ret' else [n['target']] if n['op']=='jmp' else [n['next'],n['target']] if n['op'] in go.core.BRANCHES else [n['next']]
        if any(visit(nxt) for nxt in successors):return True
        active.remove(off);done.add(off);return False
    return visit(0)


def plan_program(assembly,symbols,config):
    require(get_adapter(config)==GO,'Go leaf loops require the leaf adapter')
    plans=go.core.plan_program(assembly,symbols,config)
    require(all(has_reachable_cycle(p) for p in plans),'Compiled fixture must retain a reachable loop in every root')
    return plans


def evaluate(inferred,oracle,stats,plans):
    # Optimized Go may hoist or merge loads: do not turn source iterations
    # into a supposedly compiler-independent machine-load ordinal oracle.
    result=go.evaluate(inferred,oracle,stats,plans)
    rows={r['call_id']:r for r in inferred['results']}
    for truth,check in zip(oracle,result['checks']):
        row=rows.get(truth['sequence'],{})
        observed=row.get('summary',{}).get('backward_edges',0)
        check.update(count=truth['count'],observed_backward_edges=observed,
                     repeated_execution_verified=truth['count']<2 or observed>0)
        check['passed']=check['passed'] and check['repeated_execution_verified']
    result['passed']=result['passed'] and all(c['passed'] for c in result['checks'])
    result['scope']='Go leaf-loop fixture field/value accuracy and repeated-execution evidence; load ordinals are reported but not scored against source iterations'
    return result


build=partial(go.build,planner=plan_program)

if __name__=='__main__':
    raise SystemExit(go.common.main(default_scenario=go.common.ROOT/'scenarios/go-loop-provenance',
        prefix='go-loop-provenance',build_fn=build,record_fn=go.collector.record,
        infer_fn=go.core.infer,evaluate_fn=evaluate,required_tools=('go','objdump')))
