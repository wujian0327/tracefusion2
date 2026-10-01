#!/usr/bin/env python3
"""Pure Go ABI pilot using the same machine replay and dependency engine."""
import hashlib
import json
import os
import re
import shutil
import subprocess

import hybrid_provenance as common
import loop_provenance as core
import interproc_provenance as collector
from language_adapters import GO, GO_CALLS, get_adapter, require


def parse_nm(text):
    symbols = {}
    for line in text.splitlines():
        words = line.split()
        if len(words) == 4 and words[2] in ('t','T'):
            # go tool nm -size prints addresses in hex and sizes in decimal.
            symbols[words[3]] = (int(words[0],16),int(words[1],10))
    return symbols


def layout_assertions(config):
    lines = ['package main', 'import "unsafe"']
    for region in ('input','output'):
        layout = get_adapter(config).layout(config,region)
        checks = [(f'int(unsafe.Sizeof({region}{{}}))',layout.size)]
        for field in layout.fields:
            checks += [(f'int(unsafe.Offsetof({region}{{}}.{field.name}))',field.offset),
                       (f'int(unsafe.Sizeof({region}{{}}.{field.name}))',field.width)]
        for expr,expected in checks:
            # Both directions make a mismatch a negative array length.
            lines += [f'var _ [{expr} - {expected}]byte',f'var _ [{expected} - {expr}]byte']
    return '\n'.join(lines)+'\n'


def build(scenario, out, planner=None):
    config = json.loads((scenario/'config.json').read_text())
    adapter = get_adapter(config)
    require(adapter in (GO, GO_CALLS), 'Go builder requires the Go adapter')
    require(adapter == GO or planner is not None, 'Go calls require the explicit cross-function planner')
    require(shutil.which('go') is not None, 'Install Go and make it visible to the user running this command')
    copied = out/'sources'; copied.mkdir()
    for name in ('config.json','main.go','operations.go'): shutil.copyfile(scenario/name,copied/name)
    (copied/'layout_check.go').write_text(layout_assertions(config))
    env = dict(os.environ,GOOS='linux',GOARCH='amd64',CGO_ENABLED='0',GO111MODULE='off',
               GOTOOLCHAIN='local',GOFLAGS='',GOEXPERIMENT='',GOCACHE=str(out/'go-cache'))
    version = subprocess.check_output(['go','version'],env=env,text=True).strip()
    match = re.search(r'\bgo1\.(\d+)(?:\.|\s)',version)
    require(match is not None and 22 <= int(match[1]) <= 26,
            'Pilot requires a Go 1.22-1.26 toolchain; actual version is recorded, not assumed validated')
    common.save(out/'adapter.json',dict(adapter.describe(config),compiler=version,
                                      capture_status='requires host validation for this build'))
    binary = out/'hybrid-demo'
    command = ['go','build','-buildmode=pie','-gcflags=-l','-o',str(binary),
               str(copied/'main.go'),str(copied/'operations.go'),str(copied/'layout_check.go')]
    try:
        result = subprocess.run(command,env=env,capture_output=True,text=True,timeout=180)
        common.save(out/'build.json',dict(command=command,returncode=result.returncode,stdout=result.stdout,stderr=result.stderr,compiler=version))
        result.check_returncode()
        # `go tool nm` may itself build a tool and repopulate GOCACHE. Keep
        # the cache through symbol extraction, then clean on success/failure.
        nm = subprocess.check_output(['go','tool','nm','-size',str(binary)],env=env,text=True)
        (out/'symbols.txt').write_text(nm)
    finally:
        # Cache is reproducible and must not bloat the diagnostic result bundle.
        shutil.rmtree(out/'go-cache',ignore_errors=True)
    assembly = subprocess.check_output(['objdump','-d','-M','intel','--no-show-raw-insn',str(binary)],text=True)
    (out/'disassembly.txt').write_text(assembly)
    common.save(out/'build-identity.json',dict(binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
        go=version,sources={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in copied.iterdir()}))
    plans = (planner or core.plan_program)(assembly,parse_nm(nm),config)
    # The default planner rejects calls. The explicit calls planner observes
    # stack checks and rejects executed slow paths; neither inserts nosplit.
    common.save(out/'probe-plan.json',plans); common.save(out/'config.json',config)
    (out/'collector.bpf.c').write_text(collector.bpf_source(plans,config))
    return binary,plans,config


def evaluate(inferred, oracle, stats, plans):
    result = common.evaluate(inferred,oracle,stats,plans)
    result.pop('static_source_relations')
    result['scope'] = 'Go leaf fixture field accuracy; executed loads may be optimized; no database or scheduler coverage'
    return result


if __name__ == '__main__':
    raise SystemExit(common.main(default_scenario=common.ROOT/'scenarios/go-provenance',
        prefix='go-provenance',build_fn=build,record_fn=collector.record,infer_fn=core.infer,
        evaluate_fn=evaluate,required_tools=('go','objdump')))
