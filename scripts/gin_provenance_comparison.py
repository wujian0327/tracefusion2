#!/usr/bin/env python3
"""Compare bounded origin-set/path-sensitive controls with the frozen policy.

All methods share binaries, input fixtures, upstream boundary probes, downstream
collector and final-origin validator. Full records every supported downstream
instruction. This pilot measures equal-query observation choices, not novelty
or production overhead, and is not a reproduction of a published system.
"""
import argparse
from datetime import datetime,timezone
import hashlib
import json
import math
import os
from pathlib import Path
import random
import shutil
import statistics
import tempfile
from time import perf_counter_ns
import traceback
from types import SimpleNamespace
import zipfile

from hybrid_model import require
from hybrid_provenance import ROOT,save
from gin_choice_provenance import stage,build_role,analyze,COMPARISON_VARIANTS
from gin_byte_adapter import select_observation
from gin_cross_provenance import run as run_pair
from gin_otel_provenance import build_client
from observation_policy import choose_observation
from provenance_baselines import baseline_decision
import gin_byte_capture

METHODS=('full','origin_sets','path_sensitive','auto')


def probe_signature(plan):
    # Do not include the method name or static proof in collector equivalence.
    return [dict(address=s['address'],file_offset=s['file_offset'],op=s['op'],phase=s['phase'],
                 pair=s['pair'],snapshots=s['snapshots']) for s in plan['sites']]


def prepare_methods(plan):
    result={};decisions={}
    for method in METHODS:
        started=perf_counter_ns()
        if method=='full':decision=dict(status='selected',mode='full',reason='Complete supported downstream instruction trace')
        elif method=='auto':decision=choose_observation(plan)
        else:decision=baseline_decision(plan,method)
        decision_ns=perf_counter_ns()-started
        require(decision['status']=='selected',method+' refused: '+decision.get('reason',''))
        selected=select_observation(plan,decision['mode'])
        # Shared validation must not silently turn a baseline proposal into a
        # production-policy proposal. Refuse disagreement before collecting.
        if method in ('origin_sets','path_sensitive') and decision['mode']=='output':
            expected=[['byte',*s[0]] for s in decision['output_origin_sets']]
            require(expected==selected['output_projection']['projection'],'Baseline/projection verifier disagree')
        selected['comparison_method']=method
        result[method]=selected
        decisions[method]=dict(decision=decision,decision_ns=decision_ns,
            planning_with_shared_validation_ns=perf_counter_ns()-started,
            selected_instruction_sites=selected.get('selected_instruction_sites',[]),
            probe_signature_sha256=hashlib.sha256(json.dumps(probe_signature(selected),sort_keys=True).encode()).hexdigest())
    return result,decisions


def metrics(pair,report):
    captures={r:pair/r/'capture' for r in ('upstream','downstream')}
    responses=json.loads((captures['downstream']/'client-responses.json').read_text())
    samples=sorted(r['elapsed_ns'] for r in responses)
    require(len(samples)==8 and all(type(n) is int and n>0 for n in samples),'Missing latency evidence')
    recorded={}
    for role,cap in captures.items():
        doc=json.loads((cap/'events.json').read_text())
        require(not doc['capture_errors'] and doc['returncode']==0,'Incomplete collector output')
        recorded[role]=dict(**report['capture_counts'][role],kernel_stats=doc['stats'],
            serialized_events_bytes=len(json.dumps(doc['events'],separators=(',',':')).encode()))
    require(report['passed'] and len(report['signature'])==8,'Incomplete origin evaluation')
    return dict(requests=len(samples),resolved_requests=len(report['signature']),
        quality=dict(exact_origin_requests=8,evaluated_requests=8,exact_origin_bytes=32,evaluated_bytes=32,
                     unknown_requests=0,wrong_confident_requests=0,
                     evidence='analyze() checked each byte against independent fixture expectations before metrics'),
        elapsed_ns=samples,median_elapsed_ns=statistics.median(samples),p95_elapsed_ns=samples[math.ceil(.95*len(samples))-1],
        capture=recorded,
        timing_scope='Eight-request concurrent fixture, includes application delays; not a production overhead benchmark',
        byte_scope='Compact JSON event encoding size, not kernel perf-buffer or network byte count')


def summarize(decisions,records):
    rows=[]
    for variant,by_method in decisions.items():
        trials=records.get(variant,{})
        repeats=sorted({int(r) for entries in trials.values() for r in entries})
        for repeat in repeats:
            reports={m:trials[m][str(repeat)] for m in METHODS}
            reference=reports['full']['signature']
            for method,row in reports.items():
                require(row['signature']==reference,'Final-origin mismatch: '+variant+'/'+method)
            current=reports['auto']['metrics']['capture']['downstream']['events']
            enhanced=reports['path_sensitive']['metrics']['capture']['downstream']['events']
            rows.append(dict(variant=variant,repeat=repeat,final_origins_equal=True,
                current_events=current,path_sensitive_events=enhanced,
                current_events_saved_against_path_sensitive=enhanced-current))
    equal_plans=all(d['auto']['probe_signature_sha256']==d['path_sensitive']['probe_signature_sha256'] for d in decisions.values())
    return dict(all_passed=True,host_capture_complete=bool(rows),probe_plans_equal_to_path_sensitive=equal_plans,
        observations=rows,
        conclusion=('No additional observation-selection benefit over this path-sensitive control on these fixtures'
                    if equal_plans else 'Probe plans differ; inspect equal-origin results and costs before drawing a conclusion'),
        scope='Bounded four-byte copy scenarios; this result neither proves nor disproves novelty outside the tested model')


def archive(out):
    destination=out.with_suffix('.zip');aliases={};seen={}
    with zipfile.ZipFile(destination,'w',zipfile.ZIP_DEFLATED) as z:
        for p in sorted(out.rglob('*')):
            if not p.is_file():continue
            name=str(p.relative_to(out.parent))
            if p.name in ('gin-byte-target','otel-client'):
                digest=hashlib.sha256(p.read_bytes()).hexdigest()
                if digest in seen:aliases[name]=dict(path=seen[digest],sha256=digest);continue
                seen[digest]=name
            z.write(p,name)
        z.writestr(out.name+'/binary-aliases.json',json.dumps(aliases,indent=2)+'\n')
    if os.geteuid()==0 and os.environ.get('SUDO_UID','').isdigit():
        os.chown(destination,int(os.environ['SUDO_UID']),int(os.environ['SUDO_GID']))
    print('Return this archive: '+str(destination),flush=True)


def run(out,build_only=False,variants=COMPARISON_VARIANTS,repeats=1,seed=20261008):
    decisions={};records={};passed=False
    try:
        with tempfile.TemporaryDirectory() as tmp:
            src=Path(tmp);stage(src);client=build_client(out/'build/client',scenario=src)
        upstream=build_role(out/'build/upstream','upstream')
        upstream=select_observation(upstream,'boundary')
        save(out/'build/upstream/shared-plan.json',upstream)
        save(out/'experiment.json',dict(methods=METHODS,variants=variants,repeats=repeats,seed=seed,
            upstream_observation='boundary for every method',query='final byte source identity and offset',
            target_known_before_execution=True,source_contents='SAME for every source',
            original_paper_systems_reproduced=False))
        plans={}
        for variant in variants:
            print('Planning '+variant,flush=True)
            full=build_role(out/'build'/variant,'downstream',variant)
            plans[variant],decisions[variant]=prepare_methods(full)
            for method,p in plans[variant].items():
                save(out/'build'/variant/(method+'-plan.json'),p)
                (out/'build'/variant/(method+'-collector.c')).write_text(gin_byte_capture.source(p,1,SimpleNamespace(st_dev=0,st_ino=0)))
            save(out/'decisions.json',decisions)
        save(out/'static-comparison.json',summarize(decisions,{}))
        if not build_only:
            rng=random.Random(seed);schedule=[]
            for repeat in range(repeats):
                cases=list(variants);rng.shuffle(cases)
                for variant in cases:
                    methods=list(METHODS);rng.shuffle(methods)
                    schedule.extend(dict(repeat=repeat,variant=variant,method=m) for m in methods)
            save(out/'schedule.json',schedule)
            for task in schedule:
                variant=task['variant'];method=task['method'];repeat=task['repeat']
                print(f'Collecting {variant}/{method}/repeat-{repeat}',flush=True)
                trial=out/'runs'/str(repeat)/variant/method;trial.mkdir(parents=True)
                def builder(directory,role,unused_variant):
                    source=out/'build'/('upstream' if role=='upstream' else variant)
                    shutil.copytree(source,directory)
                    p=json.loads(json.dumps(upstream if role=='upstream' else plans[variant][method]))
                    p['binary']=str(directory/'gin-byte-target')
                    require(hashlib.sha256(Path(p['binary']).read_bytes()).hexdigest()==p['binary_sha256'],'Binary identity changed')
                    save(directory/'plan.json',p)
                    (directory/'collector.preview.c').write_text(gin_byte_capture.source(p,1,SimpleNamespace(st_dev=0,st_ino=0)))
                    return p
                rc=run_pair(trial,build_fn=builder,worker_script=ROOT/'scripts/gin_otel_provenance.py',
                    analyze_fn=analyze,variants=(variant,),archive_output=False,
                    startup_fn=lambda role,pair,caps:dict(Service=role,TraceFile=str(caps[role]/'spans.jsonl'),ClientBinary=str(client)))
                require(rc==0,'Failed trial; inspect '+str(trial/'runner-error.txt'))
                pair=trial/variant;report=json.loads((pair/'evaluation.json').read_text())
                entry=dict(signature=report['signature'],metrics=metrics(pair,report))
                records.setdefault(variant,{}).setdefault(method,{})[str(repeat)]=entry
                save(out/'measurements.json',records)
            result=summarize(decisions,records)
            require(len(result['observations'])==len(variants)*repeats,'Incomplete trial matrix')
            save(out/'comparison.json',result)
            print(json.dumps(result),flush=True)
        passed=True
    except Exception:
        error=traceback.format_exc();(out/'runner-error.txt').write_text(error);print(error,flush=True)
    finally:
        save(out/'run-status.json',dict(completed=passed,build_only=build_only))
        if not build_only:archive(out)
    return int(not passed)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=('build','run'));parser.add_argument('--output',type=Path)
    parser.add_argument('--variant',choices=COMPARISON_VARIANTS,action='append')
    parser.add_argument('--repeats',type=int,default=1);parser.add_argument('--seed',type=int,default=20261008)
    args=parser.parse_args();require(1<=args.repeats<=20,'Use 1..20 repetitions')
    out=(args.output or ROOT/'artifacts'/('gin-provenance-comparison-'+datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f'))).resolve()
    out.mkdir(parents=True,exist_ok=False)
    return run(out,args.command=='build',tuple(dict.fromkeys(args.variant or COMPARISON_VARIANTS)),args.repeats,args.seed)


if __name__=='__main__':raise SystemExit(main())
