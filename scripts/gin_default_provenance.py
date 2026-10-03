#!/usr/bin/env python3
"""Same Gin business fixture under the Go runtime's default scheduling."""
from functools import partial
import json
from pathlib import Path
import sys

import gin_migration_provenance as migration
import gin_default_boundaries as boundary
from hybrid_model import require

common=migration.common
SCENARIO=common.ROOT/'scenarios/gin-default-provenance'
client=migration.client


def bpf_source(plans,config):
    require(config['gin_api'].get('scheduling')=='runtime-default' and
            config['gin_api'].get('phase_barriers') is False,'Expected default-scheduler fixture')
    return migration.bpf_source(plans,config)


def build(scenario,out):
    result=migration.serial.build(scenario,out,source_generator=bpf_source)
    metadata=json.loads((out/'adapter.json').read_text())
    metadata.update(context_policy=boundary.migration.POLICY.name,
        execution_identity='host TGID filter + actual R14 + request generation',
        observed_thread_identity='raw pid_tid retained; never rewritten',
        scheduling_fixture='none: no pinning, GOMAXPROCS setter, phase barrier, yield, or artificial delay')
    common.save(out/'adapter.json',metadata)
    return result


record=partial(migration.serial.record,source_generator=bpf_source,client_script=__file__)


def oracle(out):
    requests=migration.oracle(out)
    stdout=[json.loads(line) for line in (out/'program.stdout.jsonl').read_text().splitlines()]
    require(len(stdout)==2,'Missing scheduler observation')
    return dict(requests=requests,scheduler_initial=stdout[0]['scheduler'],scheduler_final=stdout[1]['scheduler_final'])


if __name__=='__main__':
    if len(sys.argv)==3 and sys.argv[1]=='client':client(Path(sys.argv[2]))
    else:
        raise SystemExit(common.main(default_scenario=SCENARIO,prefix='gin-default-provenance',build_fn=build,
            record_fn=record,infer_fn=boundary.bind,evaluate_fn=boundary.evaluate,oracle_loader=oracle,
            required_tools=('go','objdump')))
