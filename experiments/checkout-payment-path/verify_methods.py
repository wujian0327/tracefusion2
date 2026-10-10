#!/usr/bin/env python3
"""Read-only host archive validation; executes trusted local analysis, not uploads.

Rebuilds plans from the archived ELF with pinned Go, regenerates collectors,
re-infers every capture before opening its oracle, and recomputes summaries.
This neither loads BPF nor treats single-inference timing as performance.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path,PurePosixPath
import random
import shutil
import subprocess
import tempfile
from types import SimpleNamespace
import zipfile

import method_baselines as methods
from compare_methods import faults
from independent_machine import check

HERE=Path(__file__).resolve().parent; ROOT=HERE.parents[1]

def verify(archive,go):
    report=dict(archive=archive.name,archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
                verifier_bpf_executed=False,performance_protocol_executed=False,
                validation='Local trusted code replays all uploaded original event records and reconstructs plans/collectors; uploaded Python and ELF are not executed')
    with zipfile.ZipFile(archive) as z:
        names=z.namelist(); check(len(names)==len(set(names)),'Duplicate archive entries')
        for info in z.infolist():
            path=PurePosixPath(info.filename)
            check(not path.is_absolute() and '..' not in path.parts,'Unsafe archive path')
            check((info.external_attr>>16)&0o170000!=0o120000,'Archive symlink')
        tops={PurePosixPath(n).parts[0] for n in names}; check(len(tops)==1,'Multiple roots')
        prefix=next(iter(tops))+'/'
        def raw(n): return z.read(prefix+n)
        def read(n): return json.loads(raw(n))
        summary=read('summary.json'); env=read('environment.json'); common=read('plan.json'); cases=read('cases.json')
        check(summary['environment']==env and cases==json.loads((HERE/'cases.json').read_text()),'Manifest/environment mismatch')
        check(env['upstream_commit']=='474d0f2eb73d97525234995a40d7781b7923a07d' and env['snapshot_version']==2,'Wrong upstream/snapshot')
        commands=[json.loads(line) for line in raw('commands.jsonl').decode().splitlines()]
        native_commands=[r for r in commands if len(r['command'])==1 and r['command'][0].endswith('/checkout-identity')]
        check(len(native_commands)==len(cases) and all(r['returncode']==0 and 'PASS' in r['stdout'].splitlines() for r in native_commands),
              'Native fixture command failure/missing log')
        sources={}
        for name,expected in env['source_sha256'].items():
            check('/' not in name and name not in ('.','..'),'Unsafe source name')
            archived=hashlib.sha256(raw('method-sources/'+name)).hexdigest(); current=hashlib.sha256((HERE/name).read_bytes()).hexdigest()
            check(archived==current==expected,'Source mismatch: '+name); sources[name]=expected
        binary_bytes=raw('checkout-identity'); check(hashlib.sha256(binary_bytes).hexdigest()==env['binary_sha256'],'Wrong ELF hash')
        with tempfile.TemporaryDirectory(prefix='verify-payment-methods-',dir=ROOT/'artifacts') as temp:
            work=Path(temp); binary=work/'checkout-identity'; binary.write_bytes(binary_bytes)
            def command(argv):
                p=subprocess.run([go,*map(str,argv)],text=True,capture_output=True,check=True,timeout=120)
                return p.stdout
            check(command(['env','GOVERSION']).strip()=='go1.25.4','Verifier requires Go 1.25.4')
            rebuilt=methods.plan_binary(binary,command,HERE.parent/'checkout-origin-audit/inspect_layout.go',work)
            check(rebuilt==common,'Rebuilt ELF/DWARF plan differs')
        report.update(binary_sha256=env['binary_sha256'],source_sha256=sources,environment=env,
                      rebuilt_plan_matches=True,upstream_main_go_sha256=summary['main_go_sha256'])
        plans={s:methods.strategy_plan(common,s) for s in methods.STRATEGIES}
        for s,p in plans.items(): check(p==read('plan-'+s+'.json'),'Strategy plan mismatch: '+s)
        rng=random.Random(env['seed']); order=[]
        for case in cases:
            strategies=list(methods.STRATEGIES); rng.shuffle(strategies); order.append(dict(case=case['Name'],order=strategies))
        check(order==read('run-order.json'),'Run order/seed mismatch')
        rows=[]; negatives=[]; metrics={}; total_events=0; total_bytes=0
        for case in cases:
            native=read(case['Name']+'/native/truth.json')
            check(native['case']==case['Name'] and native['items']==case['Items'] and native['quantity']==case['Quantity'],
                  'Native fixture manifest differs')
            for strategy,p in plans.items():
                path=case['Name']+'/'+strategy; doc=read(path+'/capture/events.json'); events=doc['events']; stats=doc['stats']
                check(doc['backend']=='ebpf-bcc' and not doc.get('synthetic',False),'Not a kernel capture')
                check(events and doc['diagnostics']['physical_probes']==len(methods.physical_probes(p)),'Probe binding mismatch')
                check([e['sequence'] for e in events]==list(range(len(events))),'Record sequence mismatch')
                check(all(e['pid_tid']>>32==doc['diagnostics']['target_pid'] for e in events),'PID binding mismatch')
                sizes=doc['diagnostics']['sample_sizes']; check(sum(sizes.values())==len(events),'Sample count mismatch')
                byte_count=sum(int(n)*v for n,v in sizes.items()); check(set(sizes)=={'212'} and doc['diagnostics']['structure_size']==208,'Event ABI mismatch')
                ns=doc['diagnostics']['namespace']; context=SimpleNamespace(st_dev=ns['dev'],st_ino=ns['ino'])
                check(methods.source(p,doc['diagnostics']['target_pid'],context).encode()==raw(path+'/capture/collector.c'),'Collector source mismatch')
                answer=methods.infer(p,doc)
                check(answer==read(path+'/inference.json'),'Stored inference differs: '+path)
                truth=read(path+'/truth.json')
                check({k:v for k,v in truth.items() if k!='elapsed_ns'}=={k:v for k,v in native.items() if k!='elapsed_ns'},'Native/observed oracle differs')
                expected=methods.evaluate(p,answer,truth)
                check(expected['passed'],'Provenance/oracle mismatch: '+path)
                expected.update(events=len(events),perf_bytes=byte_count,stats=stats)
                logged=next(r for r in summary['cases'] if r['case']==case['Name'] and r['strategy']==strategy)
                check(expected==logged,'Stored per-case evaluation differs: '+path)
                sites={s['id']:s for s in p['sites']}; sink=next((i for i,e in enumerate(events) if e['kind']=='sink'),None)
                interval=events[:sink+1] if sink is not None else []
                caller=[e['registers']['SP'] for e in interval if not e['tag'] and sites[e['site']]['function']==methods.PLACE]
                wb=[e for e in interval if sites[e['site']].get('callee','').startswith(('runtime.gcWriteBarrier','runtime.wbMove')) and e['kind']=='call']
                row=dict(**expected,amount_interval_threads=len({e['pid_tid'] for e in interval}),
                         caller_stack_addresses=len(set(caller)),observed_WB_calls=len(wb),
                         sum_entries=sum(e['kind']=='sum_entry' for e in events),
                         sum_calls_replayed=sum(c.get('function')==methods.SUM or c.get('kind')=='Sum' for c in answer.get('calls',[])),
                         boundary_equivalence_checks=len(answer.get('barrier_equivalence_checks',[])))
                rows.append(row); total_events+=len(events); total_bytes+=byte_count
                if case['Name']=='one-repeated' and strategy in ('path_sensitive_slice','boundary_replay'):
                    negatives.extend(dict(strategy=strategy,**r) for r in faults(p,doc))
        check(all(r['passed'] for r in negatives) and sorted(negatives,key=lambda r:(r['strategy'],r['name']))==
              sorted(summary['negative_checks'],key=lambda r:(r['strategy'],r['name'])),'Fault injection mismatch')
        denominator=2*sum(not c.get('PreparationFailure',False) for c in cases)
        for s in methods.STRATEGIES:
            rr=[r for r in rows if r['strategy']==s]
            m={k:sum(r.get(k,0) for r in rr) for k in ('query_fields','exact_fields','definite_fields','wrong_definite_fields','tp','fp','fn','events','perf_bytes')}
            m.update(expected_query_fields=denominator,expected_runs=len(cases),attempted_runs=len(rr),unattempted_runs=0,
                     failed_runs=sum(not r['passed'] for r in rr),exact_set_rate=m['exact_fields']/denominator)
            check(m==summary['metrics'][s],'Summary metrics mismatch: '+s); metrics[s]=m
        check(summary['all_passed'] and summary['bpf_executed'] and not summary['performance_protocol_executed'],'Wrong summary status')
        report.update(all_passed=True,host_bpf_captures=len(rows),native_fixture_runs=len(cases),original_events_replayed=total_events,
                      verifier_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                      original_perf_sample_bytes=total_bytes,metrics=metrics,cases=rows,negative_checks=negatives,
                      capture_error_totals={k:sum(r['stats'][k] for r in rows) for k in ('lost','read_errors','submit_errors','namespace_errors')},
                      namespace_differences=sum(r['stats']['namespace_differences'] for r in rows),
                      observed_amount_interval_thread_migration=any(r['amount_interval_threads']>1 for r in rows),
                      observed_caller_stack_relocation=any(r['caller_stack_addresses']>1 for r in rows),
                      observed_runtime_WB_calls=sum(r['observed_WB_calls'] for r in rows),
                      contracts=summary['contracts'],strong_external_tool_executed=False,
                      interpretation='Boundary replay is sufficient on all nine sink-producing fixed immutable-source cases. Selected does not outperform this method control on event volume. No relative latency/CPU claim.')
        all_count=metrics['all_branches']['events']; selected=metrics['selected']['events']; path=metrics['path_sensitive_slice']['events']; boundary=metrics['boundary_replay']['events']
        report['event_reductions_percent']=dict(selected_vs_all=100*(all_count-selected)/all_count,
            path_vs_selected=100*(selected-path)/selected,boundary_vs_selected=100*(selected-boundary)/selected,
            boundary_vs_all=100*(all_count-boundary)/all_count)
    return report

def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--archive',type=Path,required=True)
    p.add_argument('--go',default=os.environ.get('TRACEFUSION_GO') or shutil.which('go')); p.add_argument('--output',type=Path,required=True)
    args=p.parse_args(); check(args.go,'Go 1.25.4 is required'); report=verify(args.archive,args.go)
    args.output.parent.mkdir(parents=True,exist_ok=True); args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ('all_passed','host_bpf_captures','original_events_replayed','metrics','event_reductions_percent')}))

if __name__=='__main__': main()
