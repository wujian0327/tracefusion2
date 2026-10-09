"""Controlled observation-density comparison, not a competitor taint benchmark."""
import ctypes as ct
import json
import os
import platform
import random
import statistics
import sys
from pathlib import Path
from time import perf_counter_ns

import observer
from hybrid_model import require
from string_capture import collect

STRATEGIES=('native','boundaries','current','dense_stores')


def save(path,doc):path.write_text(json.dumps(doc,indent=2)+'\n')


def schedule(repeats,warmups,seed):
    rng=random.Random(seed);result=[]
    for phase,count in (('warmup',warmups),('measure',repeats)):
        for round_id in range(count):
            order=list(STRATEGIES);rng.shuffle(order)
            result.extend(dict(phase=phase,round=round_id,strategy=s) for s in order)
    return result


def summarize(rows):
    measured=[r for r in rows if r['phase']=='measure']
    require(measured,'No measured trials')
    native={r['round']:r for r in measured if r['strategy']=='native'}
    require(len(native)>=3,'Too few native rounds')
    result={}
    for strategy in STRATEGIES:
        trials=[r for r in measured if r['strategy']==strategy]
        require(len(trials)==len(native) and {r['round'] for r in trials}==set(native), 'Unpaired/duplicate trials')
        require(all(r['call_elapsed_ns']>0 for r in trials),'Invalid duration')
        ns=[r['call_elapsed_ns'] for r in trials]
        ratios=[r['call_elapsed_ns']/native[r['round']]['call_elapsed_ns'] for r in trials]
        result[strategy]=dict(trials=len(trials),call_ns_median=statistics.median(ns),
            call_ns_min=min(ns),call_ns_max=max(ns),paired_native_ratios=ratios,
            median_paired_native_ratio=statistics.median(ratios),
            median_paired_overhead_percent=100*(statistics.median(ratios)-1),
            events_median=statistics.median(r['events'] for r in trials),
            perf_payload_bytes_median=statistics.median(r['perf_payload_bytes'] for r in trials),
            probe_sites=trials[0]['probe_sites'],
            inference_ns_median=None if strategy=='native' else statistics.median(r['inference_ns'] for r in trials))
    current=result['current']['events_median']
    require(current>0,'No current-strategy events')
    for strategy in STRATEGIES[1:]:
        result[strategy]['event_reduction_vs_current_percent']=100*(1-result[strategy]['events_median']/current)
    return result


def sample(strategy,case,folder,binary,plan,command):
    folder.mkdir(parents=True)
    truth_path=folder/'truth.json'
    extra=dict(TRACEFUSION_IDENTITY_CASE=case,TRACEFUSION_IDENTITY_TRUTH=str(truth_path))
    if strategy=='native':
        command([binary],extra=extra,input='x')
        # Go assertions validate native fixture behavior, but there is no
        # observer inference and hence no native "provenance accuracy".
        row=dict(strategy=strategy,case=case,events=0,perf_payload_bytes=0,
                 probe_sites=0,inference_ns=None,validation='native fixture assertions only')
    else:
        selected=observer.strategy_plan(plan,strategy)
        previous={k:os.environ.get(k) for k in extra}
        os.environ.update(extra)
        try:captured=collect(binary,selected,b'x',folder/'capture',transport=observer,timeout_seconds=60)
        finally:
            for k,v in previous.items():
                if v is None:os.environ.pop(k,None)
                else:os.environ[k]=v
        started=perf_counter_ns()
        inference=observer.infer(selected,captured)
        inference_ns=perf_counter_ns()-started
        save(folder/'inference.json',inference)
        truth=json.loads(truth_path.read_text())
        validation=observer.evaluate(inference,truth)
        row=dict(strategy=strategy,case=case,events=len(captured['events']),
                 perf_payload_bytes=sum(int(size)*count for size,count in captured['diagnostics']['sample_sizes'].items()),
                 logical_event_bytes=ct.sizeof(observer.Raw)*len(captured['events']),
                 probe_sites=len(selected['sites']),inference_ns=inference_ns,validation=validation,
                 capture_stats=captured['stats'])
    truth=json.loads(truth_path.read_text())
    require(truth['call_elapsed_ns']>0,'Fixture missing elapsed time')
    row.update(call_elapsed_ns=truth['call_elapsed_ns'],timing_scope=truth['timing_scope'])
    save(folder/'sample.json',row)
    return row


def compare(args,out,binary,plan,command,cases):
    save(out/'environment.json',dict(platform=platform.platform(),python=sys.version,
        cpu_count=os.cpu_count(),go=plan['go'],gomaxprocs=os.environ.get('GOMAXPROCS'),
        gogc=os.environ.get('GOGC'),godebug=os.environ.get('GODEBUG'),seed=args.seed,
        binary_sha256=plan['binary_sha256']))
    correctness=[]
    # Fail fast rather than reporting performance for an inaccurate/lossy plan.
    for case in cases:
        for strategy in STRATEGIES[1:]:
            print(f'Correctness: {case} / {strategy}',flush=True)
            correctness.append(sample(strategy,case,out/'correctness'/case/strategy,binary,plan,command))
    save(out/'correctness.json',correctness)
    order=schedule(args.repeats,args.warmups,args.seed)
    save(out/'schedule.json',order)
    rows=[]
    for trial in order:
        phase,round_id,strategy=trial['phase'],trial['round'],trial['strategy']
        print(f'{phase} round {round_id+1}: equal-thirty-two / {strategy}',flush=True)
        folder=out/'performance'/phase/f'{round_id:03d}-{strategy}'
        row=sample(strategy,'equal-thirty-two',folder,binary,plan,command)
        row.update(trial);rows.append(row)
        with (out/'trials.jsonl').open('a') as f:f.write(json.dumps(row)+'\n')
    report=dict(mode='compare',all_passed=True,bpf_executed=True,
        correctness_runs=len(correctness),correctness_cases=len(cases),
        correctness_by_strategy={s:dict(cases_passed=sum(r['strategy']==s for r in correctness),
            reference_relations_matched=sum(2*r['validation']['outputs'] for r in correctness if r['strategy']==s),
            ambiguous_item_outputs=sum(r['validation']['ambiguous'] for r in correctness if r['strategy']==s))
            for s in STRATEGIES[1:]},
        binary_sha256=plan['binary_sha256'],repeats=args.repeats,warmups=args.warmups,
        strategies=summarize(rows),
        scope='Same Item/Cost reference query in one function; three probe policies, no whole-program taint comparison',
        timing='Single function wall time including local RPCs/truth interception; transport preconnected; BPF compilation, attachment and truth-file serialization excluded',
        limitations=['Manual query-specific boundary policy, not proven minimal or a new automatic selection algorithm',
                     'Dense control includes reachable MOVQ register-to-memory stores only, not all instructions/writes/callees',
                     'All policies use the same fixed-size event record; payload bytes exclude perf headers and other kernel/collector costs',
                     'Fresh process per sample, single request, local mock peers; no throughput/concurrent-service claim',
                     'Small sample medians/ranges are exploratory, not significance or universal overhead claims'])
    save(out/'comparison.json',report)
    save(out/'summary.json',report)
    print(json.dumps(report),flush=True)
